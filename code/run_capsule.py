"""top level run script"""

import json
import logging
import re
import tempfile
from datetime import datetime as dt
from pathlib import Path
from typing import List

import numpy as np
import pytz
from aind_data_schema.core.quality_control import (Modality, QCEvaluation,
                                                   QCMetric, QCStatus, Stage,
                                                   Status)
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


def add_border_and_label(img: Image.Image, label: str, border: int = 5) -> Image.Image:
    """
    Add a border and a text label to an image (bottom-center).

    Parameters
    ----------
    img : Image.Image
        Input PIL image.
    label : str
        Text label to add at the bottom center.
    border : int, optional
        Border size in pixels (default is 5).

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

    draw = ImageDraw.Draw(bordered)

    # Try to load a truetype font, fall back to default
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    # --- Measure text size (compatibility across Pillow versions) ---
    try:
        # Preferred in modern Pillow
        bbox = draw.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for older Pillow
        text_w, text_h = font.getsize(label)

    # Position: bottom center
    x = (bordered.width - text_w) // 2
    y = bordered.height - text_h - border - 5

    # Draw background rectangle for readability
    draw.rectangle([x - 4, y - 2, x + text_w + 4, y + text_h + 2], fill="white")
    draw.text((x, y), label, fill="red", font=font)

    return bordered


def pair_exp_ids_with_avg_depth_pngs(
    exp_ids: List[str],
    session_json_path: Path,
    pophys_dir: Path,
    avg_png_dir: Path,
    output_dir: Path,
) -> None:
    """
    For each experiment ID, find the closest matching averaged-depth PNG
    based on z-value, merge side-by-side with borders and labels, and
    save the result. Also create a QC evaluation JSON.

    Parameters
    ----------
    exp_ids : List[str]
        List of experiment IDs to process.
    session_json_path : Path
        Path to the session.json file containing FOV info.
    pophys_dir : Path
        Directory containing raw TIFF files named <exp_id>_depth.tif.
    avg_png_dir : Path
        Directory containing averaged-depth PNG files named by z-value.
    output_dir : Path
        Directory to save merged PNGs and QC evaluation JSON.

    Returns
    -------
    None
    """
    output_dir.mkdir(exist_ok=True, parents=True)

    # --- Load session JSON and FOVs ---
    with open(session_json_path, "r") as f:
        sj = json.load(f)

    fovs = []
    for ds in sj.get("data_streams", []):
        fovs.extend(ds.get("ophys_fovs", []))
    if not fovs:
        raise ValueError("No ophys_fovs found in session.json")

    # --- Collect z-values of PNG slices ---
    png_paths = list(avg_png_dir.glob("*.png"))
    z_to_png = {abs(float(p.stem)): p for p in png_paths}

    metrics = []

    for i, exp_id in enumerate(sorted(exp_ids, key=int)):
        if i >= len(fovs):
            print(f"Skipping exp_id {exp_id}: no matching FOV")
            continue

        fov = fovs[i]
        fov_z = abs(fov["scanfield_z"])  # absolute value for matching

        # Find closest PNG slice
        closest_z = min(z_to_png.keys(), key=lambda z: abs(z - fov_z))
        png_path = z_to_png[closest_z]

        # Load raw plane TIFF for this exp_id
        raw_tif_path = pophys_dir / f"{exp_id}_depth.tif"
        if not raw_tif_path.exists():
            print(f"Skipping exp_id {exp_id}: " f"raw TIFF not found at {raw_tif_path}")
            continue
        raw_img = Image.open(raw_tif_path)
        avg_img = Image.open(png_path)

        # Add borders + bottom-center labels
        raw_img = add_border_and_label(raw_img, "Child")
        avg_img = add_border_and_label(avg_img, "Parent")

        # Merge side-by-side
        total_width = raw_img.width + avg_img.width
        max_height = max(raw_img.height, avg_img.height)
        merged = Image.new("RGB", (total_width, max_height), color="black")
        merged.paste(raw_img, (0, 0))
        merged.paste(avg_img, (raw_img.width, 0))

        # Save merged PNG
        merged_path = output_dir / f"{exp_id}_merged.png"
        merged.save(merged_path)
        print(f"Saved merged image for exp_id {exp_id} -> {merged_path}")

        # --- Delete the original averaged PNG ---
        try:
            png_path.unlink()
            print(f"Deleted original averaged PNG -> {png_path}")
        except Exception as e:
            print(f"Failed to delete {png_path}: {e}")

        # --- Add QC Metric ---
        metric = QCMetric(
            name=f"ExpID {exp_id} merged view",
            description=(
                f"ExpID {exp_id} (FOV {fov.get('targeted_structure')}, "
                f"depth {fov_z}) paired with averaged PNG at depth {closest_z}"
            ),
            status_history=[PendingStatus()],
            reference=str(merged_path),
            value=str(closest_z),
        )
        metrics.append(metric)

    if metrics:
        evaluation = QCEvaluation(
            name="Merged Raw vs Averaged Depth PNGs",
            description="QC evaluation of merged raw TIFFs and "
            "closest averaged depth PNG slices",
            metrics=metrics,
            modality=Modality.POPHYS,
            stage=Stage.RAW,
        )
        eval_out_path = output_dir / "merged_planes_evaluation.json"
        with open(eval_out_path, "w") as f:
            json.dump(json.loads(evaluation.model_dump_json()), f, indent=4)
        print(f"Saved evaluation JSON -> {eval_out_path}")


def write_avg_depth_slices(splitter, output_dir: Path):
    output_dir.mkdir(exist_ok=True, parents=True)

    for roi_idx, z_int in splitter.roi_z_int_manifest:
        z_value = splitter._z_from_int(z_int)
        png_path = output_dir / f"{z_value:.1f}.png"

        with tempfile.NamedTemporaryFile(suffix=".tif") as tmp_tif:
            tmp_path = Path(tmp_tif.name)
            splitter.write_output_file(i_roi=roi_idx, z_value=z_value, output_path=tmp_path)
            img_array = np.array(Image.open(tmp_path))

        # Normalize and save PNG
        img_min, img_max = img_array.min(), img_array.max()
        if img_max > img_min:
            img_scaled = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
        else:
            img_scaled = np.zeros_like(img_array, dtype=np.uint8)

        Image.fromarray(img_scaled).save(png_path)
        print(f"Saved PNG: {png_path}")


def get_exp_ids_from_pophys(pophys_dir: Path) -> List[str]:
    """
    Grab all experiment IDs from files like
    <exp_id>_depth.tif in a pophys directory.
    Returns a sorted list of IDs as strings.

    Parameters
    ----------
    pophys_dir : Path
        Directory containing raw TIFF files named <exp_id>_depth.tif.

    Returns
    -------
    List[str]
        Sorted list of experiment IDs as strings.
    """
    tif_pattern = re.compile(r"(\d+)_depth\.tif$", re.IGNORECASE)
    exp_ids = []

    for p in pophys_dir.glob("*_depth.tif"):
        m = tif_pattern.search(p.name)
        if m:
            exp_ids.append(m.group(1))

    if not exp_ids:
        logging.info("No depth tiffs, likely a parent session")
        return None

    return sorted(exp_ids, key=int)


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
    vasculature_output_dir = output_dir / "valsulature"
    vasculature_output_dir.mkdir()
    vasculature_output_fp = vasculature_output_dir /  "vasculature.png"
    with Image.open(vasculature_fp) as im:
        im.save(vasculature_output_fp)

    logging.info(f"Saved vasculature image -> {vasculature_output_fp}")
    metric = QCMetric(
        name="Vasculature_image",
        description="Vasculature image to assess brain health and window clarity",
        status_history=[PendingStatus()],
        reference=str(vasculature_output_fp),
        value=None
    )
    evaluation = QCEvaluation(
        name="Window Health and Brain Clarity",
        description="QC evaluation of vasculature image",
        metrics=[metric],
        modality=Modality.POPHYS,
        stage=Stage.RAW,
    )
    eval_out_path = vasculature_output_dir / "vasculature_evaluation.json"
    with open(eval_out_path, "w") as f:
        json.dump(json.loads(evaluation.model_dump_json()), f, indent=4)
    logging.info(f"Saved evaluation JSON -> {eval_out_path}")


def run():
    """basic run function"""
    job_settings = JobSettings()
    input_dir = Path(job_settings.input_dir)
    output_dir = Path(job_settings.output_dir)
    session_fp = next(input_dir.rglob("session.json"))
    data_description_fp = next(input_dir.rglob("data_description.json"))

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
            runner.run_job()
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

            exp_ids = get_exp_ids_from_pophys(pophys_dir)
            if exp_ids is not None:

                splitter = AvgImageTiffSplitter(avg_depth_path)
                write_avg_depth_slices(splitter, output_dir)
                pair_exp_ids_with_avg_depth_pngs(
                    exp_ids,
                    session_fp,
                    pophys_dir,
                    output_dir,
                    Path("/results/matched_tiff_vals"),
                )
                create_vasculature(pophys_dir, output_dir)


if __name__ == "__main__":
    run()
