"""top level run script"""

import json
from pathlib import Path

from aind_pophys_converter.bergamo_stitcher import (BergamoSettings,
                                                    BergamoTiffStitcher)
from aind_pophys_converter.mesoscope_splitter import (TiffSplitterCLI,
                                                      find_split_directories)
from pydantic_settings import BaseSettings

class JobSettings(BaseSettings, cli_parse_args=True):
    """
    Settings for the job.
    """

    input_dir: str
    temp_dir: str = None
    output_dir: str = None
    debug: bool = False


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
    else:
        pass


if __name__ == "__main__":
    run()
