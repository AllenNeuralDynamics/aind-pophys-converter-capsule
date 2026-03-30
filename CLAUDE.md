# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Code Ocean capsule. Real data at `/data/` (read-only). Outputs go to `/results/`. The library `aind-pophys-converter` is installed in editable mode at `scratch/aind-pophys-converter/`.

Installed schema: `aind-data-schema==2.6.0`, `aind-data-schema-models==5.4.1` (v2).

## Commands

### Run the capsule (full pipeline)
```bash
cd /root/capsule/code
bash assemble_test_data.sh
python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/
```

Add `--debug True` to clip data during development. Debug behavior differs by path:
- **Mesoscope**: 100 frames per plane (frame-level clip within each plane's timeseries)
- **Bergamo**: 1 tiff file per epoch (each epoch has ~600 frames/file; clipping per-epoch exercises all epoch metadata paths)

### Run library tests
```bash
cd /root/capsule/scratch/aind-pophys-converter
python -m pytest tests/ -v
# Single test file:
python -m pytest tests/test_mesoscope_splitter.py -v
# With coverage:
python -m pytest tests/ --cov=aind_pophys_converter --cov-fail-under=85
```

### Lint / format
```bash
cd /root/capsule/scratch/aind-pophys-converter
black src/ tests/ --line-length 79
isort src/ tests/
flake8 src/ tests/
```

## Architecture

### Two-tier structure
- **`code/run_capsule.py`** — thin capsule entry point; loads settings, dispatches to library
- **`scratch/aind-pophys-converter/src/aind_pophys_converter/`** — all domain logic

### Processing paths

The capsule routes based on instrument type detected from `acquisition.instrument_id` and `data_description.name`:

1. **Bergamo** (`"Bergamo" in instrument_id`) → `BergamoTiffStitcher.run_converter()` → HDF5
2. **Mesoscope** (`"multiplane" in data_description.name`) → `TiffSplitterCLI.run_job()` → split TIFs + HDF5

After splitting, both paths generate QC JSON metrics:
- `pair_depth_tifs_with_avg_depth_pngs()` → `*_fov_metric.json` per plane
- `create_vasculature()` → `vasculature_metric.json`

### Key modules
- `job.py` — top-level `run()` orchestrator, FOV + vasculature QC helpers
- `settings.py` — `JobSettings` (Pydantic + CLI): `input_dir`, `output_dir`, `temp_dir`, `debug`, `dump_every`
- `qc.py` — `write_fov_metric()`, `write_vasculature_metric()` write individual `*_metric.json` files
- `mesoscope_splitter.py` — `TiffSplitterCLI`; plane traversal via `_get_imaging_planes()` (v2: `data_streams → configs (ImagingConfig) → images (PlanarImage) → planes`)
- `bergamo_stitcher.py` — `BergamoTiffStitcher`; loads `acquisition.json` as Pydantic `Acquisition`

### Data asset layout
| Asset | Contents |
|---|---|
| `multiplane-ophys_839909_2026-02-26_15-11-01/` | TIFF data + v1 metadata (session.json, rig.json) |
| `multiplane-ophys_839909_2026-02-26_15-11-01_metadata-upgrader-split-v2-metadata/` | v2 metadata only (acquisition.json, instrument.json) |

`code/assemble_test_data.sh` symlinks `pophys/` from the primary asset and copies v2 JSON files into `/scratch/data/`, producing a unified input directory. This assembly step is temporary — when a native v2 data asset exists (TIFF + v2 metadata together), point `--input_dir` directly at it.

### v2 schema key patterns
- File: `acquisition.json` (was `session.json`), `instrument.json` (was `rig.json`)
- Instrument ID: `acquisition.instrument_id` (was `session["rig_id"]`)
- Modality import: `from aind_data_schema_models.modalities import Modality`
- QC: flat `QCMetric(modality=Modality.POPHYS, stage=Stage.RAW, tags={"evaluation": "...", "type": "Operational QC"}, ...)` — no `QCEvaluation` wrapper
- Tags: `dict[str, str]` (was `list[str]`)

### QC aggregation
Individual `*_metric.json` files are written per FOV/metric. A downstream aggregator (see `qc_aggregator_reference.py`) globs them and assembles into a single `QualityControl` object. The capsule does **not** write a combined QC file.

## Style
NumPy docstrings, type hints, Black (79 cols), isort, flake8, Conventional Commits.
