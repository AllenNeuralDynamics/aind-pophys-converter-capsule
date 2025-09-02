"""top level run script"""

import json
import numpy as np
from pathlib import Path
import pytz
import re
from datetime import datetime as dt


from aind_pophys_converter.bergamo_stitcher import (BergamoSettings,
                                                    BergamoTiffStitcher)
from aind_pophys_converter.mesoscope_splitter import (TiffSplitterCLI,
                                                      find_split_directories)
from aind_pophys_converter.mesoscope_splitter import AvgImageTiffSplitter
from aind_data_schema.core.quality_control import QCMetric, QCEvaluation, Stage, Modality, QCStatus, Status
from PIL import Image, ImageDraw, ImageFont
from pydantic_settings import BaseSettings
from typing import Dict, Any, List, Tuple

from tifffile import TiffFile


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



def pair_exp_ids_with_avg_depth_pngs(
    exp_ids: List[str],
    session_json_path: Path,
    pophys_dir: Path,
    avg_png_dir: Path,
    output_dir: Path,
) -> None:
    """
    Pair each exp_id with the closest averaged-depth PNG slice based on session.json scanfield_z.
    Writes side-by-side merged PNGs and a QCEvaluation JSON.
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

    metrics: List[QCMetric] = []

    # --- Pair exp_ids to FOVs and PNGs ---
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
            print(f"Skipping exp_id {exp_id}: raw TIFF not found at {raw_tif_path}")
            continue
        raw_img = Image.open(raw_tif_path)
        avg_img = Image.open(png_path)

        # Merge side-by-side
        total_width = raw_img.width + avg_img.width
        max_height = max(raw_img.height, avg_img.height)
        merged = Image.new("L", (total_width, max_height))
        merged.paste(raw_img, (0, 0))
        merged.paste(avg_img, (raw_img.width, 0))

        # Save merged PNG
        merged_path = output_dir / f"{exp_id}_merged.png"
        merged.save(merged_path)
        print(f"Saved merged image for exp_id {exp_id} -> {merged_path}")

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

    # --- Write combined QCEvaluation JSON ---
    if metrics:
        evaluation = QCEvaluation(
            name="Merged Raw vs Averaged Depth PNGs",
            description="QC evaluation of merged raw TIFFs and closest averaged depth PNG slices",
            metrics=metrics,
            modality=Modality.POPHYS,
            stage=Stage.RAW,
        )
        eval_out_path = output_dir / "merged_planes_evaluation.json"
        with open(eval_out_path, "w") as f:
            json.dump(json.loads(evaluation.model_dump_json()), f, indent=4)
        print(f"Saved evaluation JSON -> {eval_out_path}")

def write_avg_depth_slices(splitter, output_dir: Path):
    """
    Write each slice from the averaged-depth TIFF as a separate TIFF
    named by its z-value.

    Args:
        splitter: AvgImageTiffSplitter instance for the averaged TIFF.
        output_dir: folder to save per-slice TIFFs.
    """
    output_dir.mkdir(exist_ok=True, parents=True)

    for roi_idx, z_int in splitter.roi_z_int_manifest:
        z_value = splitter._z_from_int(z_int)
        tiff_path = output_dir / f"{z_value:.1f}.tif"
        png_path = output_dir / f"{z_value:.1f}.png"

        # Write TIFF
        splitter.write_output_file(i_roi=roi_idx, z_value=z_value, output_path=tiff_path)
        print(f"Saved TIFF: {tiff_path}")

        # Convert TIFF to PNG
        img_array = np.array(Image.open(tiff_path))
        img_min, img_max = img_array.min(), img_array.max()
        if img_max > img_min:
            img_scaled = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
        else:
            img_scaled = np.zeros_like(img_array, dtype=np.uint8)
        Image.fromarray(img_scaled).save(png_path)
        print(f"Saved PNG: {png_path}")



def get_exp_ids_from_pophys(pophys_dir: Path) -> List[str]:
    """
    Grab all experiment IDs from files like <exp_id>_depth.tif in a pophys directory.
    Returns a sorted list of IDs as strings.
    """
    tif_pattern = re.compile(r"(\d+)_depth\.tif$", re.IGNORECASE)
    exp_ids: List[str] = []

    for p in pophys_dir.glob("*_depth.tif"):
        m = tif_pattern.search(p.name)
        if m:
            exp_ids.append(m.group(1))

    if not exp_ids:
        raise FileNotFoundError(f"No '*_depth.tif' files found in {pophys_dir}")

    return sorted(exp_ids, key=int)

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
        unique_id = "MOp2_3_0" # TODO: read from CCF when available
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
        # --- normal multiplane splitting ---
        job_settings.input_dir = pophys_dir
        split_directories = find_split_directories(pophys_dir)
        '''
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
        '''

        # --- averaged depth handling ---
        avg_depth_files = list(pophys_dir.glob("*_averaged_depth.tiff"))
        if avg_depth_files:
            avg_depth_path = avg_depth_files[0]
            avg_output_dir = output_dir / "averaged_depths"
            print(f"Processing averaged depth TIFF: {avg_depth_path} → {avg_output_dir}")

            exp_ids = get_exp_ids_from_pophys(pophys_dir)
            splitter = AvgImageTiffSplitter(avg_depth_path)
            write_avg_depth_slices(splitter, Path("/results/tiff_vals"))
            pair_exp_ids_with_avg_depth_pngs(exp_ids,session_fp,pophys_dir,Path("/results/tiff_vals"),Path("/results/matched_tiff_vals"))

if __name__ == "__main__":
    run()
