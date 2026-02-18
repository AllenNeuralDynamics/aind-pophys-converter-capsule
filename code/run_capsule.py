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
from aind_qcportal_schema.metric_value import DropdownMetric
from aind_pophys_converter.bergamo_stitcher import (BergamoSettings,
                                                    BergamoTiffStitcher)
from aind_pophys_converter.mesoscope_splitter import (AvgImageTiffSplitter,
                                                      TiffSplitterCLI,
                                                      find_split_directories)
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pydantic_settings import BaseSettings

# Setup debug logging with timestamps
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


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
    logger.debug(f"[PAIR_EXP_IDS] Starting pair_exp_ids_with_avg_depth_pngs")
    logger.debug(f"[PAIR_EXP_IDS] exp_ids: {exp_ids}")
    logger.debug(f"[PAIR_EXP_IDS] session_json_path: {session_json_path}")
    logger.debug(f"[PAIR_EXP_IDS] pophys_dir: {pophys_dir}")
    logger.debug(f"[PAIR_EXP_IDS] avg_png_dir: {avg_png_dir}")
    logger.debug(f"[PAIR_EXP_IDS] output_dir: {output_dir}")

    output_dir.mkdir(exist_ok=True, parents=True)
    logger.debug(f"[PAIR_EXP_IDS] Created output_dir: {output_dir}")

    # --- Load session JSON and FOVs ---
    logger.debug(f"[PAIR_EXP_IDS] Loading session.json from {session_json_path}")
    with open(session_json_path, "r") as f:
        sj = json.load(f)
    logger.debug(f"[PAIR_EXP_IDS] Loaded session.json successfully")

    fovs = []
    for ds in sj.get("data_streams", []):
        fovs.extend(ds.get("ophys_fovs", []))
    logger.debug(f"[PAIR_EXP_IDS] Found {len(fovs)} FOVs in session.json")
    if not fovs:
        logger.error("No ophys_fovs found in session.json")
        raise ValueError("No ophys_fovs found in session.json")

    # --- Collect z-values of PNG slices ---
    logger.debug(f"[PAIR_EXP_IDS] Searching for PNG files in {avg_png_dir}")
    png_paths = list(avg_png_dir.glob("*.png"))
    logger.debug(f"[PAIR_EXP_IDS] Found {len(png_paths)} PNG files")
    for p in png_paths:
        logger.debug(f"[PAIR_EXP_IDS]   - {p.name}")
    z_to_png = {abs(float(p.stem)): p for p in png_paths}
    logger.debug(f"[PAIR_EXP_IDS] z_to_png mapping: {list(z_to_png.keys())}")

    metrics = []

    for i, exp_id in enumerate(sorted(exp_ids, key=int)):
        logger.debug(f"[PAIR_EXP_IDS] Processing exp_id {exp_id} (index {i})")
        if i >= len(fovs):
            logger.warning(f"Skipping exp_id {exp_id}: no matching FOV (index {i} >= {len(fovs)})")
            continue

        fov = fovs[i]
        scanfield_z = abs(fov["scanfield_z"]) # value for matching to png
        fov_z = abs(fov["imaging_depth"]) # actual imaging depth
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: scanfield_z={scanfield_z}, fov_z={fov_z}")

        # Find closest PNG slice
        closest_z = min(z_to_png.keys(), key=lambda z: abs(z - scanfield_z))
        png_path = z_to_png[closest_z]
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: closest_z={closest_z}, png_path={png_path}")

        # Load raw plane TIFF for this exp_id
        raw_tif_path = pophys_dir / f"{exp_id}_depth.tif"
        logger.debug(f"[PAIR_EXP_IDS] Looking for raw TIFF at {raw_tif_path}")
        if not raw_tif_path.exists():
            logger.warning(f"Skipping exp_id {exp_id}: raw TIFF not found at {raw_tif_path}")
            continue
        logger.debug(f"[PAIR_EXP_IDS] Found raw TIFF, opening image files")
        raw_img = Image.open(raw_tif_path)
        avg_img = Image.open(png_path)
        logger.debug(f"[PAIR_EXP_IDS] Opened images: raw={raw_tif_path.name}, avg={png_path.name}")

        # Add borders + bottom-center labels
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: Adding borders and labels")
        raw_img = add_border_and_label(raw_img, "Child")
        avg_img = add_border_and_label(avg_img, "Parent")
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: Borders added")

        # Merge side-by-side
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: Merging images")
        total_width = raw_img.width + avg_img.width
        max_height = max(raw_img.height, avg_img.height)
        merged = Image.new("RGB", (total_width, max_height), color="black")
        merged.paste(raw_img, (0, 0))
        merged.paste(avg_img, (raw_img.width, 0))
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: Merged image size {total_width}x{max_height}")

        # Save merged PNG
        merged_path = output_dir / f"{exp_id}_merged.png"
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: Saving merged PNG to {merged_path}")
        merged.save(merged_path)
        logger.info(f"Saved merged image for exp_id {exp_id} -> {merged_path}")

        # --- Delete the original averaged PNG ---
        logger.debug(f"[PAIR_EXP_IDS] exp_id {exp_id}: Deleting original PNG {png_path}")
        try:
            png_path.unlink()
            logger.debug(f"Deleted original averaged PNG -> {png_path}")
        except Exception as e:
            logger.error(f"Failed to delete {png_path}: {e}")

        unique_id = f"{fov.get('targeted_structure')}_{fov.get('index')}"

        # --- Add QC Metric ---
        metric = QCMetric(
            name=f"{unique_id} Parent-Child FOV ",
            description=(
                f"{unique_id}, with actual imaging-depth: {fov_z} "
                f"paired with averaged PNG at scanfield_z: {closest_z}"
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
            )
        )
        metrics.append(metric)

    logger.debug(f"[PAIR_EXP_IDS] Finished processing all exp_ids. Total metrics: {len(metrics)}")
    if metrics:
        logger.debug(f"[PAIR_EXP_IDS] Creating QC evaluation with {len(metrics)} metrics")
        evaluation = QCEvaluation(
            name="Op. QC: Field-of-view Matching",
            description="QC evaluation of merged raw TIFFs and "
            "closest averaged depth PNG slices",
            metrics=metrics,
            modality=Modality.POPHYS,
            stage=Stage.RAW,
            tags=["Operational QC"]
        )
        eval_out_path = output_dir / "merged_planes_evaluation.json"
        logger.debug(f"[PAIR_EXP_IDS] Writing evaluation JSON to {eval_out_path}")
        with open(eval_out_path, "w") as f:
            json.dump(json.loads(evaluation.model_dump_json()), f, indent=4)
        logger.info(f"Saved evaluation JSON -> {eval_out_path}")
    else:
        logger.warning(f"[PAIR_EXP_IDS] No metrics generated, skipping QC evaluation JSON")


def write_avg_depth_slices(splitter, output_dir: Path):
    logger.debug(f"[WRITE_AVG_DEPTH] Starting write_avg_depth_slices")
    logger.debug(f"[WRITE_AVG_DEPTH] output_dir: {output_dir}")
    output_dir.mkdir(exist_ok=True, parents=True)
    logger.debug(f"[WRITE_AVG_DEPTH] Created output directory")

    roi_count = len(splitter.roi_z_int_manifest)
    logger.debug(f"[WRITE_AVG_DEPTH] Processing {roi_count} ROIs")

    for idx, (roi_idx, z_int) in enumerate(splitter.roi_z_int_manifest):
        z_value = splitter._z_from_int(z_int)
        png_path = output_dir / f"{z_value:.1f}.png"
        logger.debug(f"[WRITE_AVG_DEPTH] ROI {idx}/{roi_count}: roi_idx={roi_idx}, z_value={z_value:.1f}")

        with tempfile.NamedTemporaryFile(suffix=".tif") as tmp_tif:
            tmp_path = Path(tmp_tif.name)
            logger.debug(f"[WRITE_AVG_DEPTH] Writing temp file: {tmp_path}")
            splitter.write_output_file(i_roi=roi_idx, z_value=z_value, output_path=tmp_path)
            img_array = np.array(Image.open(tmp_path))
            logger.debug(f"[WRITE_AVG_DEPTH] Loaded image: shape={img_array.shape}")

        # Normalize and save PNG
        img_min, img_max = img_array.min(), img_array.max()
        logger.debug(f"[WRITE_AVG_DEPTH] Image range: [{img_min}, {img_max}]")
        if img_max > img_min:
            img_scaled = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
        else:
            img_scaled = np.zeros_like(img_array, dtype=np.uint8)

        Image.fromarray(img_scaled).save(png_path)
        logger.info(f"Saved PNG: {png_path}")


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
    logger.debug(f"[CREATE_VASC] Starting create_vasculature")
    logger.debug(f"[CREATE_VASC] pophys_dir: {pophys_dir}, output_dir: {output_dir}")
    vasculature_fp = next(pophys_dir.glob("*_vasculature.tif"), None)
    logger.debug(f"[CREATE_VASC] vasculature_fp: {vasculature_fp}")
    if not vasculature_fp:
        logger.info("No vasculature TIFF files found for vasculature creation.")
        return
    vasculature_output_dir = output_dir / "vasculature"
    logger.debug(f"[CREATE_VASC] Creating vasculature output dir: {vasculature_output_dir}")
    vasculature_output_dir.mkdir(exist_ok=True)
    vasculature_output_fp = vasculature_output_dir /  "vasculature.png"
    logger.debug(f"[CREATE_VASC] Opening {vasculature_fp} and saving to {vasculature_output_fp}")
    with Image.open(vasculature_fp) as im:
        im.save(vasculature_output_fp)

    logger.info(f"Saved vasculature image -> {vasculature_output_fp}")
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


def run():
    """basic run function"""
    logger.info("=" * 80)
    logger.info("START OF RUN")
    logger.info("=" * 80)

    job_settings = JobSettings()
    input_dir = Path(job_settings.input_dir)
    output_dir = Path(job_settings.output_dir)
    logger.info(f"[RUN] input_dir: {input_dir}")
    logger.info(f"[RUN] output_dir: {output_dir}")
    logger.debug(f"[RUN] debug flag: {job_settings.debug}")

    logger.debug(f"[RUN] Searching for session.json")
    session_fp = next(input_dir.rglob("session.json"))
    logger.debug(f"[RUN] Found session.json: {session_fp}")

    logger.debug(f"[RUN] Searching for data_description.json")
    data_description_fp = next(input_dir.rglob("data_description.json"))
    logger.debug(f"[RUN] Found data_description.json: {data_description_fp}")

    logger.debug(f"[RUN] Loading session.json")
    with open(session_fp) as f:
        session = json.load(f)
    logger.debug(f"[RUN] Loaded session.json, rig_id: {session.get('rig_id', 'N/A')}")

    logger.debug(f"[RUN] Loading data_description.json")
    with open(data_description_fp) as f:
        data_description = json.load(f)
    logger.debug(f"[RUN] Loaded data_description.json, name: {data_description.get('name', 'N/A')}")

    logger.debug(f"[RUN] Searching for pophys directory")
    pophys_dir = next(input_dir.rglob("pophys/"))
    logger.debug(f"[RUN] Found pophys_dir: {pophys_dir}")
    if "Bergamo" in session.get("rig_id", ""):
        logger.info(f"[RUN] Detected Bergamo rig")
        unique_id = "MOp2_3_0"  # TODO: read from CCF when available
        output_dir = output_dir / unique_id
        output_dir.mkdir(exist_ok=True)
        logger.info(f"[RUN] Running Bergamo converter")
        bergamo_settings = BergamoSettings(
            input_dir=pophys_dir,
            output_dir=output_dir,
            unique_id=unique_id,
            session_fp=session_fp,
        )
        bergamo_stitcher = BergamoTiffStitcher(bergamo_settings)
        logger.debug(f"[RUN] Calling bergamo_stitcher.run_converter()")
        bergamo_stitcher.run_converter()
        logger.info(f"[RUN] Bergamo converter completed")
    elif "multiplane" in data_description["name"]:
        logger.info(f"[RUN] Detected multiplane dataset")
        # # --- normal multiplane splitting ---
        job_settings.input_dir = pophys_dir
        logger.debug(f"[RUN] Searching for split directories")
        split_directories = find_split_directories(pophys_dir)
        logger.debug(f"[RUN] Found {len(split_directories)} split directories")

        if len(split_directories) == 0:
            logger.info(f"[RUN] No split directories found, running TiffSplitterCLI")
            runner = TiffSplitterCLI(job_settings)
            logger.debug(f"[RUN] Calling runner.run_job()")
            runner.run_job()
            logger.info(f"[RUN] TiffSplitterCLI completed")
        else:
            logger.info(f"[RUN] Split directories already exist, skipping splitting")
            output_dir = Path(output_dir)
            for split_dir in split_directories:
                new_directory = output_dir / split_dir
                new_directory.mkdir(parents=True, exist_ok=True)
                with open(new_directory / f"{split_dir}.txt", "w") as f:
                    f.write(f"{split_dir}.h5")

        # --- averaged depth handling ---
        logger.debug(f"[RUN] Searching for averaged depth TIFF files")
        avg_depth_files = list(pophys_dir.glob("*_averaged_depth.tiff"))
        logger.debug(f"[RUN] Found {len(avg_depth_files)} averaged depth TIFF files")

        if avg_depth_files:
            avg_depth_path = avg_depth_files[0]
            avg_output_dir = output_dir / "averaged_depths"
            logger.info(
                f"Processing averaged depth TIFF: {avg_depth_path} -> {output_dir}"
            )

            logger.debug(f"[RUN] Getting exp_ids from pophys_dir")
            exp_ids = get_exp_ids_from_pophys(pophys_dir)
            logger.debug(f"[RUN] Got exp_ids: {exp_ids}")

            if exp_ids is not None:
                logger.info(f"[RUN] Processing {len(exp_ids)} experiments")
                logger.debug(f"[RUN] Creating AvgImageTiffSplitter")
                splitter = AvgImageTiffSplitter(avg_depth_path)
                logger.debug(f"[RUN] Calling write_avg_depth_slices")
                write_avg_depth_slices(splitter, output_dir)
                logger.debug(f"[RUN] write_avg_depth_slices completed")

                logger.debug(f"[RUN] Calling pair_exp_ids_with_avg_depth_pngs")
                pair_exp_ids_with_avg_depth_pngs(
                    exp_ids,
                    session_fp,
                    pophys_dir,
                    output_dir,
                    Path("/results/matched_tiff_vals"),
                )
                logger.info(f"[RUN] pair_exp_ids_with_avg_depth_pngs completed")
            else:
                logger.warning(f"[RUN] No exp_ids found, skipping pair matching")
        else:
            logger.warning(f"[RUN] No averaged depth files found, skipping averaged depth processing")

        logger.debug(f"[RUN] Calling create_vasculature")
        create_vasculature(pophys_dir, output_dir)
        logger.debug(f"[RUN] create_vasculature completed")
    else:
        logger.warning(f"[RUN] Unknown dataset type, rig_id={session.get('rig_id', 'N/A')}, data_description_name={data_description.get('name', 'N/A')}")

    logger.info("=" * 80)
    logger.info("END OF RUN - SUCCESS")
    logger.info("=" * 80)


if __name__ == "__main__":
    run()
