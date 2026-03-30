# Changes: aind-data-schema v1 → v2 Upgrade (Phase A)

## Overview

Upgrades `code/run_capsule.py` and the `aind-pophys-converter` library
(`bergamo_stitcher.py`, `mesoscope_splitter.py`) from `aind-data-schema==1.4.0`
to `aind-data-schema==2.6.0`.

Also fixes a pre-existing bug where `debug=True` was silently ignored in the
mesoscope splitting path.

---

## `code/run_capsule.py`

### Imports
- Removed `QCEvaluation` (deleted in v2) and `Modality` from
  `aind_data_schema.core.quality_control`.
- Added `Acquisition` and `DataDescription` imports from `aind_data_schema`.
- Added `QualityControl` to QC imports.
- Added `from aind_data_schema_models.modalities import Modality`.

### JobSettings
- Added `dump_every: int = 1000` field so the mesoscope splitter's frame-flush
  batch size can be configured via the capsule CLI without editing the library.

### File discovery and loading
- `session.json` → `acquisition.json` (glob pattern updated).
- Variable renamed: `session_fp` → `acquisition_fp`, `session` → `acquisition`,
  `data_description` (was `json.load`) now loaded via
  `DataDescription.model_validate_json()`.
- Both files are now validated Pydantic objects, not raw dicts.

### Attribute access
- `session.get("rig_id", "")` → `acquisition.instrument_id` (attribute access).
- `data_description["name"]` → `data_description.name` (attribute access).
- `BergamoSettings(session_fp=...)` → `BergamoSettings(acquisition_fp=...)`.

---

## `scratch/aind-pophys-converter/src/aind_pophys_converter/bergamo_stitcher.py`

### Imports
- Added `from aind_data_schema.core.acquisition import Acquisition`.

### BergamoSettings
- `session_fp: Path` → `acquisition_fp: Path`.

### BaseStitcher
- `self.session_fp` → `self.acquisition_fp`.

### BergamoTiffStitcher
- `_load_session() -> dict` → `_load_acquisition() -> Acquisition`:
  uses `Acquisition.model_validate_json()` instead of `json.load`.
- `_extract_tiff_from_session(session_data: dict)` →
  `_extract_tiff_from_acquisition(acquisition_data: Acquisition)`:
  - `session_data.get("stimulus_epochs", {})` → `acquisition_data.stimulus_epochs`.
  - Sort key: `dateutil.parser.parse(x["stimulus_start_time"])` →
    `x.stimulus_start_time` (already a datetime).
  - `epoch.get("output_parameters", {})` removed — v2 `StimulusEpoch` has
    `extra='forbid'`, so the v1 custom field was serialized into `epoch.notes`
    as JSON by the auto-upgrader. Now parsed with `json.loads(epoch.notes or "")`.
  - Dict key access (`epoch["stimulus_name"]`) → attribute access
    (`epoch.stimulus_name`).
- `run_converter`: `session_meta` / `_extract_tiff_from_session` renamed to
  `acquisition_meta` / `_extract_tiff_from_acquisition`.

### CLI (`from_args`)
- `--session-file` → `--acquisition-file`.
- `session_fp=Path(job_args.session_file)` →
  `acquisition_fp=Path(job_args.acquisition_file)`.

---

## `scratch/aind-pophys-converter/src/aind_pophys_converter/mesoscope_splitter.py`

### Bug fix: debug mode was silently ignored
- `split_timeseries_tiff` accepted `debug` but never forwarded it to
  `_split_timeseries_tiff`. Fixed by passing `debug=debug`.
- `_split_timeseries_tiff` now breaks early when `debug=True`, stopping after
  `(max_offset + 1) * DEBUG_N_FRAMES` pages.
- Added module-level constant `DEBUG_N_FRAMES = 100`.

### Imports
- Added:
  ```python
  from aind_data_schema.components.configs import ImagingConfig, PlanarImage
  from aind_data_schema.core.acquisition import Acquisition
  ```

### JobSettings
- Added `dump_every: int = Field(default=1000, ...)` — frame-flush batch size,
  previously read from session.json at runtime.

### TiffSplitterCLI.__init__
- `*session.json` glob → `*acquisition.json`.
- `json.load(f)` → `Acquisition.model_validate_json(acquisition_json.read_text())`.
- `self.session_data` → `self.acquisition_data` (validated `Acquisition` object).
- `self.dump_every = job_settings.dump_every` stored on instance.

### New method: `_get_imaging_planes()`
- Traverses `acquisition_data.data_streams → configurations (ImagingConfig) →
  images (PlanarImage) → planes`, returns list sorted by `plane_index`.
- Replaces the v1 pattern of iterating `session_data["data_streams"]` and
  checking `ophys_fovs`.

### `_create_experiment_metadata`
- Signature: `(self, plane)` — takes a Pydantic `Plane`/`CoupledPlane` object
  instead of a raw `fov: dict`.
- `targeted_structure` derived from `plane.targeted_structure.acronym`.
- `fov_id` uses `plane.plane_index` (was `fov["index"]`).
- Dropped v1-only fields (`fov_coordinate_ml`, `fov_coordinate_ap`,
  `fov_reference`, `fov_scale_factor`) — not present in v2 schema; per-file
  metadata dicts now stored as empty `{}`.

### `_process_single_fov`
- Signature: `(self, plane, roi_index: int, z_value: float, ...)` — explicit
  `roi_index` and `z_value` params instead of reading from `fov` dict.
- Removed `fov["scanimage_roi_index"]` and `fov["scanfield_z"]` lookups.

### `_process_timeseries_data` and `run_job`
- Loop changed from `session_data["data_streams"] → ophys_fovs` to
  `_get_imaging_planes()`.
- `roi_index` and `z_value` now resolved via
  `timeseries_splitter.roi_z_int_manifest[plane.plane_index]`.
- Documented ordering assumption: v2 `plane.depth` is in physical micrometers
  and cannot be matched to the raw ScanImage z-actuator values stored in the
  TIFF. Code relies on the metadata auto-upgrader preserving the same ordering
  as the v1 `scanfield_z` lookup. This assumption is recorded in comments at
  both call sites.
- `self.session_data.get("dump_every", 1000)` → `self.dump_every`.

---

## `code/run_capsule.py` — QC construction (Step 4)

### QCEvaluation → per-metric JSON files
- Removed `QCEvaluation` entirely from both `pair_depth_tifs_with_avg_depth_pngs`
  and `create_vasculature`.
- Each `QCMetric` now carries `modality=Modality.POPHYS`, `stage=Stage.RAW`,
  and `tags={"evaluation": "<group name>", "type": "Operational QC"}` — moving
  the group-level fields down to each metric per v2 schema.
- `tags` changed from `list[str]` to `dict[str, str]`.
- Metrics are written as individual `*_metric.json` files (one per metric),
  compatible with the downstream QC aggregator (`qc_aggregator_reference.py`)
  which globs for `*metric*.json` and assembles a single `QualityControl`.
- FOV pairing: one `{targeted_structure_id}_{intended_depth}_fov_metric.json`
  per plane (e.g. `VISp_200_fov_metric.json`). Removed `um` suffix from all
  `unique_id` usages — IDs like `VISp_200` are not unit-bearing identifiers.
- Vasculature: `vasculature_metric.json` (was `vasculature_evaluation.json`).
- Metric descriptions rewritten to be self-contained and reviewer-actionable.
  Old evaluation-level `name`/`description` fields dropped.

### platform.json discovery — symlink fix
- `next(input_dir.rglob("*platform.json"), None)` → `next(pophys_dir.glob("*platform.json"), None)`.
- `Path.rglob()` in Python ≤3.12 does not follow symlinks; `pophys/` is a
  symlink in the dev environment. Using `pophys_dir.glob()` resolves correctly.

---

## `code/run` script

- Added `--debug True` to the python invocation for development runs.

---

## `scratch/aind-pophys-converter/src/aind_pophys_converter/mesoscope_splitter.py` — additional fixes

### Debug print
- Added `print("Debug mode active: clipping timeseries to {DEBUG_N_FRAMES} frames per plane.")`
  at the start of the page loop in `_split_timeseries_tiff` when `debug=True`,
  so debug mode is explicitly visible in run output.

### temp_dir creation
- `TiffSplitterCLI.__init__` now calls `Path(self.temp_dir).mkdir(parents=True, exist_ok=True)`
  after setting `self.temp_dir`, preventing `FileNotFoundError` from `tempfile.mkdtemp`
  when the temp directory does not yet exist.

---

## Phase A status: COMPLETE

End-to-end run verified against real data in debug mode:
- 8 planes output (`VISp_0–3`, `VISl_4–7`), each timeseries `(100, 512, 512)`
- All file types present: `.h5`, `_depth.tif`, `_surface.tif`, `_z_stack_local.h5`
- 8 FOV QC metric JSONs + `vasculature_metric.json` written
- No errors or tracebacks

Skipped: library unit test fixture updates (`session.json` → `acquisition.json`).
These remain as tech debt for Phase B or a dedicated test pass.
