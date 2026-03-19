"""top level run script"""

import json
import logging
import tempfile
from datetime import datetime as dt
from pathlib import Path

import numpy as np
import pytz
import tifffile
from aind_data_schema.core.quality_control import (Modality, QCEvaluation,
                                                   QCMetric, QCStatus, Stage,
                                                   Status)
from aind_qcportal_schema.metric_value import DropdownMetric
from aind_pophys_converter.bergamo_stitcher import (BergamoSettings,
                                                    BergamoTiffStitcher)
from aind_pophys_converter.mesoscope_splitter import (AvgImageTiffSplitter,
                                                      TiffSplitterCLI,
                                                      find_split_directories)
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic_settings import BaseSettings


def PendingStatus():
    seattle_tz = pytz.timezone("America/Los_Angeles")
    return QCStatus(
        evaluator="Automated",
        status=Status.PENDING,
        timestamp=dt.now(seattle_tz).isoformat(),
    )


class JobSettings(BaseSettings, cli_parse_args=True):
    """
    Settings for the job.
    """

    input_dir: str
    temp_dir: str = None
    output_dir: str = None
    debug: bool = False


def add_border_and_label(img: Image.Image, label: str, border: int = 5, font_size: int = 40) -> Image.Image:
    """
    Add a border and a text label to an image (top-center, above the image).

    Parameters
    ----------
    img : Image.Image
        Input PIL image.
    label : str
        Text label to add at the bottom center.
    border : int, optional
        Border size in pixels (default is 5).
    font_size : int, optional
        Font size for the label text (default is 40).

    Returns
    -------
    Image.Image
        New image with border and label added.
    """
    # Add border
    bordered = ImageOps.expand(img, border=border, fill="white")

    # Convert to RGB for drawing text
    if bordered.mode != "RGB":
        bordered = bordered.convert("RGB")

    font = ImageFont.load_default(size=font_size)

    # Measure text size using a temporary draw surface
    tmp_draw = ImageDraw.Draw(bordered)
    bbox = tmp_draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    label_area_h = text_h + 24  # padding above and below text

    # Create a new canvas with extra space at the top for the label
    canvas = Image.new("RGB", (bordered.width, bordered.height + label_area_h), color="white")
    canvas.paste(bordered, (0, label_area_h))

    draw = ImageDraw.Draw(canvas)
    x = (canvas.width - text_w) // 2
    y = (label_area_h - text_h) // 2
    draw.text((x, y), label, fill="black", font=font)

    return canvas


def pair_depth_tifs_with_avg_depth_pngs(
    pophys_dir: Path,
    avg_slice_dir: Path,
    platform_fp: Path,
    output_dir: Path,
) -> None:
    """
    For each imaging plane defined in platform.json, locate the parent depth
    TIFF by intended_depth and targeted_structure_id, find the closest child
    averaged-depth TIF by abs(scanimage_scanfield_z), merge them side-by-side
    with borders and labels, and save the result. Also creates a QC evaluation
    JSON.

    Each image is independently normalized to uint8 using its own 5th/95th
    percentiles. Parent depth TIFs (dedicated snapshots, uint16 raw counts ~600–1400)
    and child averaged-depth TIFs (temporal mean of timeseries, values ~4–32) are
    on fundamentally different intensity scales, so shared normalization is not meaningful.

    Parent TIFs are named <timestamp>_<intended_depth>_<targeted_structure_id>_depth.tif
    and come from the parent session. Child TIFs are written by write_avg_depth_slices
    as float32 from the current (child) session's averaged depth TIFF.

    Parameters
    ----------
    pophys_dir : Path
        Directory containing parent depth TIFFs named
        <timestamp>_<intended_depth>_<targeted_structure_id>_depth.tif.
    avg_slice_dir : Path
        Directory containing child averaged-depth float32 TIF files named by
        z-value (e.g. -276.0.tif), written by write_avg_depth_slices.
    platform_fp : Path
        Path to the session platform.json, which provides intended_depth,
        targeted_structure_id, and scanimage_scanfield_z for each imaging plane.
    output_dir : Path
        Directory to save merged PNGs and QC evaluation JSON.

    Returns
    -------
    None
    """
    output_dir.mkdir(exist_ok=True, parents=True)

    # --- Load imaging planes from platform.json ---
    with open(platform_fp) as f:
        platform_json = json.load(f)

    imaging_planes = [
        plane
        for group in platform_json.get("imaging_plane_groups", [])
        for plane in group.get("imaging_planes", [])
    ]

    if not imaging_planes:
        print("No imaging planes found in platform.json; skipping depth pairing.")
        return

    # --- Collect child TIFs keyed by abs z-value ---
    child_tifs = list(avg_slice_dir.glob("*.tif"))
    z_to_tif = {abs(float(p.stem)): p for p in child_tifs}

    if not z_to_tif:
        print("No averaged-depth TIFs found; skipping depth pairing.")
        return

    metrics = []

    for plane in imaging_planes:
        intended_depth = plane["intended_depth"]
        targeted_structure_id = plane["targeted_structure_id"]
        scanfield_z = plane["scanimage_scanfield_z"]

        # --- Locate parent TIF by intended_depth + targeted_structure_id ---
        parent_tifs = list(
            pophys_dir.glob(f"*_{intended_depth}_{targeted_structure_id}_depth.tif")
        )
        if len(parent_tifs) == 0:
            print(
                f"WARNING: No parent TIF found for intended_depth={intended_depth}, "
                f"targeted_structure_id={targeted_structure_id}; skipping."
            )
            continue
        if len(parent_tifs) > 1:
            print(
                f"WARNING: Multiple parent TIFs found for intended_depth={intended_depth}, "
                f"targeted_structure_id={targeted_structure_id}; "
                f"using first: {parent_tifs[0].name}"
            )
        raw_tif_path = parent_tifs[0]

        # --- Find closest child TIF by abs(scanimage_scanfield_z) ---
        closest_z = min(z_to_tif.keys(), key=lambda z: abs(z - abs(scanfield_z)))
        child_tif_path = z_to_tif[closest_z]

        # Read both as float64 arrays
        with tifffile.TiffFile(raw_tif_path) as tif:
            parent_array = tif.asarray().astype(np.float64)
        with tifffile.TiffFile(child_tif_path) as tif:
            child_array = tif.asarray().astype(np.float64)

        # Normalize each image independently to its own 5th/95th percentiles
        # (parent and child are on fundamentally different intensity scales)
        def _to_uint8(arr: np.ndarray) -> np.ndarray:
            lo, hi = np.percentile(arr, 5), np.percentile(arr, 95)
            if hi > lo:
                return np.clip((arr - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)
            return np.zeros_like(arr, dtype=np.uint8)

        p_lo, p_hi = np.percentile(parent_array, 5), np.percentile(parent_array, 95)
        c_lo, c_hi = np.percentile(child_array, 5), np.percentile(child_array, 95)
        print(f"  Parent normalization: p5={p_lo:.1f}, p95={p_hi:.1f} (dtype={parent_array.dtype})")
        print(f"  Child  normalization: p5={c_lo:.1f}, p95={c_hi:.1f} (dtype={child_array.dtype})")

        raw_img = Image.fromarray(_to_uint8(parent_array))
        avg_img = Image.fromarray(_to_uint8(child_array))

        # Add borders + bottom-center labels
        raw_img = add_border_and_label(raw_img, "Parent")
        avg_img = add_border_and_label(avg_img, "Child")

        # Merge side-by-side
        total_width = raw_img.width + avg_img.width
        max_height = max(raw_img.height, avg_img.height)
        merged = Image.new("RGB", (total_width, max_height), color="white")
        merged.paste(raw_img, (0, 0))
        merged.paste(avg_img, (raw_img.width, 0))

        # Save merged PNG
        merged_path = output_dir / f"{raw_tif_path.stem}_merged.png"
        merged.save(merged_path)
        print(f"Saved merged image for {raw_tif_path.name} -> {merged_path}")

        # --- Delete the original averaged TIF ---
        try:
            child_tif_path.unlink()
            print(f"Deleted original averaged TIF -> {child_tif_path}")
        except Exception as e:
            print(f"Failed to delete {child_tif_path}: {e}")

        unique_id = f"{targeted_structure_id}_{intended_depth}um"

        # --- Add QC Metric ---
        metric = QCMetric(
            name=f"{unique_id} Parent-Child FOV",
            description=(
                f"{raw_tif_path.stem} (intended_depth={intended_depth}, "
                f"structure={targeted_structure_id}, scanfield_z={scanfield_z}) "
                f"paired with averaged PNG at z: {closest_z}"
            ),
            status_history=[PendingStatus()],
            reference=str(merged_path),
            value=DropdownMetric(
                value="",
                options=[
                    "FOV Matches parent FOV",
                    "FOV does not match parent FOV.",
                ],
                status=[Status.PASS, Status.FAIL],
            ),
        )
        metrics.append(metric)

    if metrics:
        evaluation = QCEvaluation(
            name="Op. QC: Field-of-view Matching",
            description="QC evaluation of merged raw TIFFs and "
            "closest averaged depth PNG slices",
            metrics=metrics,
            modality=Modality.POPHYS,
            stage=Stage.RAW,
            tags=["Operational QC"],
        )
        eval_out_path = output_dir / "merged_planes_evaluation.json"
        with open(eval_out_path, "w") as f:
            json.dump(json.loads(evaluation.model_dump_json()), f, indent=4)
        print(f"Saved evaluation JSON -> {eval_out_path}")


def write_avg_depth_slices(splitter, output_dir: Path):
    output_dir.mkdir(exist_ok=True, parents=True)

    for roi_idx, z_int in splitter.roi_z_int_manifest:
        z_value = splitter._z_from_int(z_int)
        tif_path = output_dir / f"{z_value:.1f}.tif"

        with tempfile.NamedTemporaryFile(suffix=".tif") as tmp_tif:
            tmp_path = Path(tmp_tif.name)
            splitter.write_output_file(i_roi=roi_idx, z_value=z_value, output_path=tmp_path)
            img_array = tifffile.imread(tmp_path)

        # Save as float32 TIF to preserve raw values for downstream normalization
        tifffile.imwrite(tif_path, img_array.astype(np.float32))
        print(f"Saved TIF: {tif_path}")



def create_vasculature(pophys_dir: Path, output_dir: Path) -> None:
    """
    Create a vasculature image from the averaged depth TIFF file.

    Parameters
    ----------
    pophys_dir : Path
        Directory containing the averaged depth TIFF file.
    output_dir : Patch
        Save path for vasculuture image

    Returns
    -------
    None
    """
    vasculature_fp = next(pophys_dir.glob("*_vasculature.tif"), None)
    if not vasculature_fp:
        logging.info("No averaged depth TIFF files found for vasculature creation.")
        return
    vasculature_output_dir = output_dir / "vasculature"
    vasculature_output_dir.mkdir(exist_ok=True, parents=True)
    vasculature_output_fp = vasculature_output_dir /  "vasculature.png"
    with Image.open(vasculature_fp) as im:
        im.save(vasculature_output_fp)

    logging.info(f"Saved vasculature image -> {vasculature_output_fp}")
    metric = QCMetric(
        name="Vasculature_image",
        description="Vasculature image to assess brain health and window clarity",
        status_history=[PendingStatus()],
        reference=str(vasculature_output_fp),
        value=DropdownMetric(
            value="",
            options=[
                "Quality is sufficient",
                "Poor vasculature image quality",
                "Light bruising on surface of brain",
                "Severe bruising on surface of brain",
                "Vascularization of brain surface",
                "Discoloration of brain surface (white)",
                "Bubbles in objective immersion present, but do NOT impact imaging quality",
                "Bubbles in objective immersion impact imaging quality"
            ],
            status=[Status.PASS, Status.PASS, Status.PASS, Status.FAIL, Status.PASS, Status.PASS, Status.PASS, Status.FAIL],
        )
    )
    
    evaluation = QCEvaluation(
        name="Op. QC: Window Clarity",
        description="QC evaluation of vasculature image",
        metrics=[metric],
        modality=Modality.POPHYS,
        stage=Stage.RAW,
        tags=["Operational QC"]
    )
    eval_out_path = vasculature_output_dir / "vasculature_evaluation.json"
    with open(eval_out_path, "w") as f:
        json.dump(json.loads(evaluation.model_dump_json()), f, indent=4)
    logging.info(f"Saved evaluation JSON -> {eval_out_path}")

def is_child_session_via_platform_json(platform_fp: Path) -> bool:
    print("checking is_child_session_via_platform_json", platform_fp)
    with open(platform_fp) as f:
        platform_json = json.load(f)
        parent_session = platform_json.get("parent_session", None)

    print("returning", parent_session is not None)
    return parent_session is not None
def run():
    """basic run function"""
    job_settings = JobSettings()
    input_dir = Path(job_settings.input_dir)
    output_dir = Path(job_settings.output_dir)
    session_fp = next(input_dir.rglob("session.json"))
    data_description_fp = next(input_dir.rglob("data_description.json"))
    
    # TODO: dependency on platform.json is temporary, 
    # until intended depth and parent info are in schema metadata
    platform_fp = next(input_dir.rglob("*platform.json"), None)
    if platform_fp is None:
        raise FileNotFoundError(f"No platform.json file found in {input_dir}")

    with open(session_fp) as f:
        session = json.load(f)
    with open(data_description_fp) as f:
        data_description = json.load(f)
    pophys_dir = next(input_dir.rglob("pophys/"))
    if "Bergamo" in session.get("rig_id", ""):
        unique_id = "MOp2_3_0"  # TODO: read from CCF when available
        output_dir = output_dir / unique_id
        output_dir.mkdir(exist_ok=True)
        bergamo_settings = BergamoSettings(
            input_dir=pophys_dir,
            output_dir=output_dir,
            unique_id=unique_id,
            session_fp=session_fp,
        )
        bergamo_stitcher = BergamoTiffStitcher(bergamo_settings)
        bergamo_stitcher.run_converter()
    elif "multiplane" in data_description["name"]:
        # # --- normal multiplane splitting ---
        job_settings.input_dir = pophys_dir
        split_directories = find_split_directories(pophys_dir)
        if len(split_directories) == 0:
            runner = TiffSplitterCLI(job_settings)
            # runner.run_job()
        else:
            output_dir = Path(output_dir)
            for split_dir in split_directories:
                new_directory = output_dir / split_dir
                new_directory.mkdir(parents=True, exist_ok=True)
                with open(new_directory / f"{split_dir}.txt", "w") as f:
                    f.write(f"{split_dir}.h5")
        # --- averaged depth handling ---
        avg_depth_files = list(pophys_dir.glob("*_averaged_depth.tiff"))
        if avg_depth_files:
            avg_depth_path = avg_depth_files[0]
            avg_output_dir = output_dir / "averaged_depths"
            print(
                f"Processing averaged depth TIFF: \
                {avg_depth_path} -> {output_dir}"
            )

            if is_child_session_via_platform_json(platform_fp):

                splitter = AvgImageTiffSplitter(avg_depth_path)
                write_avg_depth_slices(splitter, output_dir)
                pair_depth_tifs_with_avg_depth_pngs(
                    pophys_dir,
                    output_dir,
                    platform_fp,
                    Path("/results/matched_tiff_vals"),
                )
        create_vasculature(pophys_dir, output_dir)


if __name__ == "__main__":
    run()
