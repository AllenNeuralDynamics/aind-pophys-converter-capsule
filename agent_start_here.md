# CLAUDE.md — aind-pophys-converter-capsule Schema Upgrade Workspace

## Environment

You are running inside a **Code Ocean capsule**. You have access to real data at `/data/` (read-only — you cannot modify anything under `/data/`). You can run the capsule code directly and test against real input. Write all outputs to `/results/`.

## Task

Upgrade `aind-pophys-converter-capsule` from `aind-data-schema==1.4.0` to `aind-data-schema==2.6.0`.

The library `aind-pophys-converter` is installed in editable mode at `scratch/aind-pophys-converter/`.

## Workspace Layout

```
CAPSULE/
├── .codeocean/
│   ├── app-panel.json         # UI params (input_dir, output_dir, temp_dir, debug)
│   ├── datasets.json          # Attached datasets
│   └── environment.json       # Pip packages — MUST UPDATE (mirrors Dockerfile)
├── code/
│   ├── run                    # Bash entry point (runs: python -u run_capsule.py)
│   └── run_capsule.py         # Main capsule orchestrator (425 lines) — PRIMARY EDIT TARGET
├── environment/
│   └── Dockerfile             # Pins schema + models versions — MUST UPDATE
├── scratch/
│   └── aind-pophys-converter/ # Library (editable install)
│       ├── src/aind_pophys_converter/
│       │   ├── bergamo_stitcher.py      # Bergamo TIFF→HDF5 stitching
│       │   ├── mesoscope_splitter.py    # Mesoscope TIFF splitting
│       │   └── utils/                   # tiff_metadata, full_field_utils, logging
│       └── tests/
└── data/                      # REAL DATA — Code Ocean mount (read-only)
    ├── multiplane-ophys_839909_2026-02-26_15-11-01/          # Primary data asset (v1 metadata)
    │   ├── behavior/
    │   ├── behavior-videos/
    │   ├── original_metadata/
    │   ├── pophys/                    # TIFF data lives here
    │   ├── data_description.json
    │   ├── metadata.nd.json
    │   ├── procedures.json
    │   ├── processing.json
    │   ├── rig.json                   # v1 name — becomes instrument.json in v2
    │   ├── session.json               # v1 name — becomes acquisition.json in v2
    │   └── subject.json
    └── multiplane-ophys_839909_2026-02-26_15-11-01_metadata-upgrader-split-v2-metadata/  # v2 metadata
        ├── acquisition.json           # v2 equivalent of session.json
        ├── data_description.json
        ├── instrument.json            # v2 equivalent of rig.json
        ├── procedures.json
        ├── processing.json
        └── subject.json
```

### Data Asset Notes

The primary data asset has **v1 metadata** (session.json, rig.json). A separate companion asset provides the **v2 metadata** (acquisition.json, instrument.json). `/data/` is **immutable** — you cannot modify anything under it.

### Development Testing Strategy

Since the TIFF data and v2 metadata are in separate data assets, assemble a unified working directory in `/scratch/data/` using symlinks before running:

```bash
# Create /scratch/data/ that combines real data (symlinks) with v2 metadata (copies)
# See "Test Data Assembly Script" section below for the script.

# Then run the capsule with:
python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/
```

This keeps the file discovery code clean (single `input_dir`, single `rglob` tree). When real v2 data assets arrive (TIFF data + v2 metadata in one asset), just delete the assembly step and point `input_dir` directly at `/data/<asset-name>/`.

### Test Data Assembly Script

Create `code/assemble_test_data.sh` (temporary — remove when v2 data assets exist natively):

```bash
#!/usr/bin/env bash
# Assemble /scratch/data/ from split v1-data + v2-metadata assets.
# Symlinks data dirs (read-only, no disk cost), copies v2 metadata JSON.
set -e

PRIMARY="/data/multiplane-ophys_839909_2026-02-26_15-11-01"
V2_META="/data/multiplane-ophys_839909_2026-02-26_15-11-01_metadata-upgrader-split-v2-metadata"
TARGET="/scratch/data"

rm -rf "$TARGET"
mkdir -p "$TARGET"

# Symlink all data directories from primary asset
for dir in behavior behavior-videos original_metadata pophys; do
    ln -s "$PRIMARY/$dir" "$TARGET/$dir"
done

# Copy v2 metadata JSON files (small files, need to be in same tree)
cp "$V2_META"/acquisition.json "$TARGET/"
cp "$V2_META"/instrument.json "$TARGET/"
cp "$V2_META"/data_description.json "$TARGET/"
cp "$V2_META"/procedures.json "$TARGET/"
cp "$V2_META"/processing.json "$TARGET/"
cp "$V2_META"/subject.json "$TARGET/"

# Copy platform.json from primary if it exists (not in v2 metadata asset)
if [ -f "$PRIMARY"/*platform.json ]; then
    cp "$PRIMARY"/*platform.json "$TARGET/"
fi

echo "Assembled test data at $TARGET"
ls -la "$TARGET"
```

Result:
```
/scratch/data/
├── behavior/           → symlink to /data/.../behavior/
├── behavior-videos/    → symlink to /data/.../behavior-videos/
├── original_metadata/  → symlink to /data/.../original_metadata/
├── pophys/             → symlink to /data/.../pophys/
├── acquisition.json    # copied from v2 metadata asset
├── instrument.json     # copied from v2 metadata asset
├── data_description.json
├── procedures.json
├── processing.json
└── subject.json
```

## Coding Style

- NumPy-style docstrings with type hints
- `unittest.TestCase` for tests, `unittest.mock.patch` for mocking
- Black (line-length 79), isort, flake8
- Conventional Commits: `feat(scope):`, `fix(scope):`, `chore(scope):`

## Guidelines

- Run tests before and after changes
- Never push without explicit user approval
- Read ALL context before diagnosing issues
- For version upgrades: always diff old vs new to find ALL breaking changes

---

## Execution Strategy

This work has three phases. **Do them sequentially, not interleaved.**

### Phase A: Schema Upgrade (do first)

Get the capsule and library working on aind-data-schema v2.6 **in place**, keeping the current capsule/library code structure. This is the risky part — field renames, missing fields, QC model rewrite. You want the shortest path to a working v2 capsule so you can validate against real data.

1. Create `code/assemble_test_data.sh` — builds `/scratch/data/` from split data assets
2. Bump deps in Dockerfile + environment.json (schema 2.6, models 5.4.1)
3. Fix imports — QCEvaluation → QualityControl, Modality import path
4. Fix QC construction — flat metrics, tags as dict, default_grouping
5. Fix file discovery — session.json → acquisition.json, rig_id → instrument_id
6. Fix library — mesoscope_splitter/bergamo_stitcher session→acquisition traversal
7. Update library tests — session.json → acquisition.json fixtures
8. **Test against real data** — `bash assemble_test_data.sh && python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/`

### Phase B: Capsule/Library Refactor (do second)

Once the capsule works on v2, restructure to the metadata-manager pattern: move all orchestration/QC logic into the library, reduce capsule to ~11 lines. This is purely structural — moving code between files with no logic changes. If something breaks, you know it's a structural issue, not a schema issue.

1. Create `settings.py`, `job.py`, `qc.py` in library — move code from capsule
2. Update `pyproject.toml` — add schema + pydantic-settings dependencies
3. Reduce capsule to ~11 lines (pure passthrough)
4. Write library tests for new modules
5. **Test against real data** — `bash assemble_test_data.sh && python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/`

### Phase C: Structured Logging with aind-log-utils (do last)

Once the refactored library is working, integrate `aind-log-utils` for structured JSON logging. This replaces ad-hoc `logging.basicConfig()` calls with AIND's standard structured logging that feeds into Grafana/Loki and CloudWatch.

1. Add `aind-log-utils` to library `pyproject.toml` dependencies
2. Add `aind-log-utils` to capsule Dockerfile/environment.json
3. Replace `logging.basicConfig(...)` in `job.py:run()` with `setup_logging(...)` call
4. Pass metadata (process_name, subject_id, asset_name) extracted from acquisition.json
5. **Test against real data** — `bash assemble_test_data.sh && python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/`

**Why this order?** Schema-first means you can test after each phase independently, and when something breaks you can isolate whether it's a schema issue, a structural issue, or a logging issue.

## Current Versions (v1 — before upgrade)

| Package | Current | Target |
|---------|---------|--------|
| aind-data-schema | 1.4.0 | 2.6.0 |
| aind-data-schema-models | 0.7.5 | >=5.4.1,<6 |
| aind-qcportal-schema | 0.4.0 | TBD (verify compatibility with schema v2) |

---

## Current Code Architecture

Understand what exists before changing it.

### aind-pophys-converter Library

The library at `scratch/aind-pophys-converter/` has **zero imports** from `aind_data_schema` or `aind_data_schema_models`. However, it **reads session.json as raw JSON** and depends on v1 field names and structure — so the library DOES need changes for the schema upgrade.

| Class | File | Purpose |
|-------|------|---------|
| `BergamoSettings` | bergamo_stitcher.py | Pydantic settings for Bergamo stitching |
| `BergamoTiffStitcher` | bergamo_stitcher.py | Stitch multi-plane Bergamo TIFFs → HDF5 |
| `TiffSplitterCLI` | mesoscope_splitter.py | Orchestrate mesoscope TIFF splitting |
| `AvgImageTiffSplitter` | mesoscope_splitter.py | Extract averaged depth images per ROI/z |
| `TimeSeriesSplitter` | mesoscope_splitter.py | Split timeseries → per-ROI HDF5 |
| `ZStackSplitter` | mesoscope_splitter.py | Split z-stacks |
| `ScanImageMetadata` | utils/tiff_metadata.py | Parse ScanImage TIFF metadata |
| `JobSettings` | mesoscope_splitter.py | Pydantic settings for splitting jobs |

Capsule imports from library:
```python
from aind_pophys_converter.bergamo_stitcher import BergamoSettings, BergamoTiffStitcher
from aind_pophys_converter.mesoscope_splitter import AvgImageTiffSplitter, TiffSplitterCLI, find_split_directories
```

### Capsule (run_capsule.py) — What It Does Today

The capsule (`code/run_capsule.py`, 425 lines) contains too much domain logic that should live in the library:
- File discovery (`rglob` for session.json, data_description.json, platform.json, pophys/)
- Rig-type branching (Bergamo vs multiplane)
- Averaged-depth TIFF processing (`write_avg_depth_slices`, `pair_depth_tifs_with_avg_depth_pngs`)
- Vasculature image creation (`create_vasculature`)
- All QC metric construction and JSON serialization
- Image manipulation (PIL border/label, side-by-side merge, normalization)

### Settings Objects (currently scattered)

There are three separate settings scattered across capsule and library:
- `JobSettings` in capsule (`BaseSettings, cli_parse_args=True`) — `input_dir`, `output_dir`, `temp_dir`, `debug`
- `JobSettings` in library `mesoscope_splitter.py` — `input_dir`, `output_dir`, `temp_dir`, `debug`
- `BergamoSettings` in library `bergamo_stitcher.py` — `input_dir`, `output_dir`, `unique_id`, `session_fp`

---

## Phase A: Schema v1.4 → v2.6 Migration Guide

### Files That Need Changes

**Capsule:**
1. **`environment/Dockerfile`** — bump version pins
2. **`.codeocean/environment.json`** — bump version pins (mirrors Dockerfile)
3. **`code/run_capsule.py`** — QC imports/construction + session.json→acquisition.json + rig_id→instrument_id

**Library (scratch/aind-pophys-converter/):**
4. **`src/aind_pophys_converter/mesoscope_splitter.py`** — session.json→acquisition.json file glob + data_streams/ophys_fovs traversal
5. **`src/aind_pophys_converter/bergamo_stitcher.py`** — session_fp→acquisition_fp + stimulus_epochs access
6. **`tests/test_mesoscope_splitter.py`** — update test fixtures for acquisition.json
7. **`tests/test_bergamo_stitcher.py`** — update test fixtures for acquisition.json

---

### Breaking Change #1: QCEvaluation DELETED — Flat Metric Model

The biggest change. In v1, QC was hierarchical: `QualityControl → QCEvaluation → QCMetric`. In v2, evaluations are gone: `QualityControl → QCMetric` (flat list).

**v1 imports (current code, line 12-14):**
```python
from aind_data_schema.core.quality_control import (Modality, QCEvaluation,
                                                   QCMetric, QCStatus, Stage,
                                                   Status)
```

**v2 imports (what it needs to become):**
```python
from aind_data_schema_models.modalities import Modality
from aind_data_schema.core.quality_control import (
    QCMetric, QCStatus, QualityControl, Stage, Status,
)
```

Key differences:
- `QCEvaluation` is **gone** — remove import entirely
- `Modality` moved from `aind_data_schema.core.quality_control` → `aind_data_schema_models.modalities`
- `QualityControl` is the new top-level container (replaces `QCEvaluation` for output)

### Breaking Change #2: QCMetric Now Requires modality + stage

In v1, `modality` and `stage` lived on `QCEvaluation`. In v2, each `QCMetric` carries its own `modality` and `stage`.

**v1 pattern (current code):**
```python
metric = QCMetric(
    name="...",
    description="...",
    status_history=[PendingStatus()],
    reference="...",
    value=DropdownMetric(...),
)
# modality/stage set on the QCEvaluation wrapper:
evaluation = QCEvaluation(
    name="Op. QC: Field-of-view Matching",
    metrics=metrics,
    modality=Modality.POPHYS,
    stage=Stage.RAW,
    tags=["Operational QC"],
)
```

**v2 pattern (what it needs to become):**
```python
metric = QCMetric(
    name="...",
    modality=Modality.POPHYS,          # MOVED HERE from QCEvaluation
    stage=Stage.RAW,                    # MOVED HERE from QCEvaluation
    description="...",
    status_history=[PendingStatus()],
    reference="...",
    value=DropdownMetric(...),
    tags={"evaluation": "FOV Matching", "type": "Operational QC"},  # dict, not list
)
# Then wrap in QualityControl (not QCEvaluation):
qc = QualityControl(
    metrics=metrics,
    default_grouping=["modality", ("evaluation",)],
    allow_tag_failures=[],
)
```

### Breaking Change #3: Tags Changed from List[str] to dict[str, str]

**v1:** `tags=["Operational QC"]` (on QCEvaluation)
**v2:** `tags={"category": "Operational QC"}` (on QCMetric, key-value pairs)

Tags enable hierarchical grouping. Choose meaningful keys. The `default_grouping` field on `QualityControl` references tag keys.

### Breaking Change #4: QualityControl Requires default_grouping

`QualityControl` (the top-level container) has two new required-ish fields:
- `default_grouping: List[str | tuple[str, ...]]` — tag keys for visualization grouping
- `allow_tag_failures: List[str]` — tag values allowed to fail without failing overall QC

Example:
```python
QualityControl(
    metrics=[...],
    default_grouping=["modality", "stage", ("evaluation",)],
    allow_tag_failures=[],
)
```

### Breaking Change #5: QCStatus.timestamp Must Be Timezone-Aware

The `timestamp` field on `QCStatus` is now `AwareDatetimeWithDefault`. The current code already uses `dt.now(seattle_tz).isoformat()` — but verify this still works with the v2 datetime validators. v2 has stricter datetime enforcement.

### Breaking Change #6: Output Format Change

**v1:** Each `QCEvaluation` saved as a separate JSON file (e.g., `merged_planes_evaluation.json`, `vasculature_evaluation.json`)
**v2:** Typically a single `quality_control.json` with all metrics in one `QualityControl` object.

Decide: keep separate files (each a `QualityControl`) or merge into one? The downstream QC portal may expect a specific format.

### Breaking Change #7: session.json → acquisition.json (File Rename)

In v2, core metadata files were renamed:
| v1 Filename | v2 Filename | Model Class |
|-------------|-------------|-------------|
| `session.json` | `acquisition.json` | `Acquisition` (was `Session`) |
| `rig.json` | `instrument.json` | `Instrument` (was `Rig`) |

The v2 CORE_FILES list: `subject`, `data_description`, `procedures`, `instrument`, `processing`, `acquisition`, `quality_control`, `model`.

**Impact on run_capsule.py (line 361):**
```python
# v1 (current):
session_fp = next(input_dir.rglob("session.json"))
# v2 (new):
acquisition_fp = next(input_dir.rglob("acquisition.json"))
```

**Impact on run_capsule.py (line 375) — Bergamo detection:**
```python
# v1 (current): reads rig_id from session.json
if "Bergamo" in session.get("rig_id", ""):
# v2 (new): rig_id → instrument_id, now on acquisition.json
if "Bergamo" in acquisition.get("instrument_id", ""):
```

### Breaking Change #8: session.json Structure → acquisition.json Structure

The internal structure changed significantly. The capsule reads `session.json` as raw JSON (not schema-validated), so field/key names matter.

**Key field renames:**
| v1 (session.json) | v2 (acquisition.json) | Notes |
|--------------------|------------------------|-------|
| `rig_id` | `instrument_id` | Used by capsule to detect Bergamo vs mesoscope |
| `data_streams[].ophys_fovs` | Gone — see below | FOV data restructured |
| `data_streams[].ophys_fovs[].scanfield_z` | `DataStream.configurations[ImagingConfig].images[PlanarImage].planes[Plane]` | Deeply nested now |
| `data_streams[].ophys_fovs[].scanimage_roi_index` | No direct equivalent in v2 schema | May need custom handling |
| `stimulus_epochs` | `stimulus_epochs` (still exists on Acquisition) | Structure changed — see StimulusEpoch model |
| `dump_every` | Not a standard schema field | Was custom; check if still present |

**v2 DataStream structure (no ophys_fovs):**
```python
class DataStream(DataModel):
    stream_start_time: datetime
    stream_end_time: datetime
    modalities: List[Modality.ONE_OF]
    active_devices: List[str]
    configurations: List[ImagingConfig | LaserConfig | DetectorConfig | ...]
    # NO ophys_fovs field
```

**v2 imaging data lives in ImagingConfig:**
```python
class ImagingConfig(DeviceConfig):
    channels: List[Channel]
    images: List[PlanarImage | PlanarImageStack | ImageSPIM]
    sampling_strategy: Optional[SamplingStrategy]

class PlanarImage(Image):
    planes: List[Plane | CoupledPlane | Slap2Plane]

class Plane(DataModel):
    scanimage_roi_index: int  # if present
    # depth/position info in image_to_acquisition_transform
```

### Breaking Change #9: Library Reads session.json Directly

**CRITICAL:** The `aind-pophys-converter` library (in `scratch/`) also reads `session.json` — it is NOT schema-free for this migration.

**Location: `mesoscope_splitter.py` line 1596:**
```python
session_json = next(self.input_dir.parent.glob("*session.json"), None)
if not session_json:
    raise ValueError("No session.json file found")
with open(session_json, "r") as f:
    self.session_data = json.load(f)
```

**The library then traverses v1 session structure:**
- `self.session_data["data_streams"]` (line 1797, 1881)
- `data_stream.get("ophys_fovs")` (line 1798, 1882)
- `fov["scanfield_z"]` (line 1801)
- `fov["scanimage_roi_index"]` (line 1802)
- `self.session_data.get("dump_every", 1000)` (line 1902)

**Location: `bergamo_stitcher.py`:**
- `BergamoSettings.session_fp` — path to session file
- `_load_session()` — loads session JSON
- `_extract_tiff_from_session()` — reads `session_data.get("stimulus_epochs", {})`

**Library changes needed:**
1. `mesoscope_splitter.py:1596` — glob for `*acquisition.json` instead of `*session.json`
2. `mesoscope_splitter.py:1797-1902` — traverse v2 acquisition structure to find FOV data (the `ophys_fovs` path is completely different in v2)
3. `bergamo_stitcher.py` — update `session_fp` naming and `stimulus_epochs` access pattern
4. All related tests in `tests/test_mesoscope_splitter.py` and `tests/test_bergamo_stitcher.py`

---

### Specific Code Locations to Modify in run_capsule.py

#### Imports (lines 12-15)
```python
# REMOVE:
from aind_data_schema.core.quality_control import (Modality, QCEvaluation,
                                                   QCMetric, QCStatus, Stage,
                                                   Status)
# REPLACE WITH:
from aind_data_schema_models.modalities import Modality
from aind_data_schema.core.quality_control import (
    QCMetric, QCStatus, QualityControl, Stage, Status,
)
```

#### PendingStatus() (lines 25-31)
May need adjustment for timezone-aware datetime. Current `isoformat()` string output may not validate — v2 expects an actual `datetime` object, not a string. Test this.

#### pair_depth_tifs_with_avg_depth_pngs() — QC construction (lines 234-267)
- Add `modality=Modality.POPHYS, stage=Stage.RAW` to each `QCMetric`
- Add `tags={"evaluation": "FOV Matching", "type": "Operational QC"}` to each metric
- Replace `QCEvaluation(...)` with `QualityControl(metrics=metrics, default_grouping=[...])`

#### create_vasculature() — QC construction (lines 314-346)
- Add `modality=Modality.POPHYS, stage=Stage.RAW` to the vasculature `QCMetric`
- Add `tags={"evaluation": "Window Clarity", "type": "Operational QC"}` to metric
- Replace `QCEvaluation(...)` with `QualityControl(metrics=[metric], default_grouping=[...])`

#### run() function — metadata file discovery (lines 361-374)
```python
# v1 (current):
session_fp = next(input_dir.rglob("session.json"))
# ...
with open(session_fp) as f:
    session = json.load(f)

# v2 (new):
acquisition_fp = next(input_dir.rglob("acquisition.json"))
# ...
with open(acquisition_fp) as f:
    acquisition = json.load(f)
```

#### run() function — Bergamo detection (line 375)
```python
# v1 (current):
if "Bergamo" in session.get("rig_id", ""):
# v2 (new):
if "Bergamo" in acquisition.get("instrument_id", ""):
```

#### Dockerfile (environment/Dockerfile)
```dockerfile
# CHANGE:
RUN pip install -U --no-cache-dir \
    aind-data-schema==2.6.0 \
    aind-data-schema-models==5.4.1 \
    aind-pophys-converter==0.0.1 \
    aind-qcportal-schema==0.4.0 \
    pydantic-settings==2.8.1 \
    pytz==2025.2 \
    tifffile==2024.2.12
```

#### .codeocean/environment.json
Mirror the same version bumps as the Dockerfile.

---

### QC v2 Reference (from aind-data-schema 2.6.0)

#### Complete v2 QCMetric signature:
```python
class QCMetric(DataModel):
    name: str                                    # Metric name
    modality: Modality.ONE_OF                    # NEW (was on QCEvaluation)
    stage: Stage                                 # NEW (was on QCEvaluation)
    value: Any                                   # Metric value (scalar, dict, DropdownMetric, etc.)
    status_history: List[QCStatus]               # Min length 1
    description: Optional[str] = None
    reference: Optional[str] = None              # Image URL or plot type
    tags: dict[str, str] = {}                    # NEW format (was list on QCEvaluation)
    evaluated_assets: Optional[List[str]] = None # For MULTI_ASSET stage only
```

#### Complete v2 QualityControl signature:
```python
class QualityControl(DataCoreModel):
    metrics: List[QCMetric | CurationMetric]     # Flat list (no QCEvaluation wrapper)
    key_experimenters: Optional[List[str]] = None
    notes: Optional[str] = None
    default_grouping: List[str | tuple[str, ...]] # REQUIRED — tag keys for viz grouping
    allow_tag_failures: List[str] = []            # Tag values that can fail
    status: Optional[dict] = None                 # Auto-computed by validator
```

#### Stage enum values:
```python
Stage.RAW          # "Raw data"
Stage.PROCESSING   # "Processing"
Stage.ANALYSIS     # "Analysis"
Stage.MULTI_ASSET  # "Multi-asset" (requires evaluated_assets)
```

#### Status enum values (unchanged):
```python
Status.FAIL    # "Fail"
Status.PASS    # "Pass"
Status.PENDING # "Pending"
```

#### Modality for pophys:
```python
Modality.POPHYS  # Population physiology (same name, different import path)
```

---

## Phase B: Capsule/Library Refactor — Metadata-Manager Pattern

**Do this AFTER Phase A is complete and validated against real data.**

### The Ideal Pattern: aind-metadata-manager

The `aind-metadata-manager` / `aind-metadata-manager-capsule` pairing demonstrates the target architecture. The capsule is **11 lines** — a pure passthrough:

```python
# aind-metadata-manager-capsule/code/run_capsule.py — THE ENTIRE FILE
import aind_metadata_manager.metadata_manager as manager


def run():
    """Run the capsule to process metadata."""
    manager.run()

if __name__ == "__main__":
    run()
```

The library owns **everything**: settings (with `BaseSettings, cli_parse_args=True`), the job class, and the `run()` entry point:

```python
# aind-metadata-manager/src/aind_metadata_manager/metadata_manager.py (simplified)
from pydantic_settings import BaseSettings

class MetadataSettings(BaseSettings, cli_parse_args=True):
    """All settings live in the library — CLI parsing included."""
    input_dir: Path = Path("/data")
    output_dir: Path = Path("/results")
    verbose: bool = False
    # ... all params

class MetadataManager:
    def __init__(self, settings: MetadataSettings):
        self.settings = settings

    def create_processing_metadata(self): ...
    def create_quality_control_metadata(self): ...
    # ...

def run() -> None:
    """Module-level entry point — capsule calls this directly."""
    settings = MetadataSettings()
    manager = MetadataManager(settings)
    # ... orchestration
```

Key insight: **`cli_parse_args=True` on BaseSettings** means the library itself handles CLI argument parsing. The capsule doesn't need to know about any parameters.

### Target Architecture

```
run_capsule.py (~11 lines — PURE PASSTHROUGH)
    │
    └── import aind_pophys_converter.job as job; job.run()

job.run() [IN LIBRARY — owns everything]
    │
    ├── PophysConverterSettings(BaseSettings, cli_parse_args=True) — parses CLI args
    ├── PophysConverterJob(settings) — instantiate job
    └── job.run()
        ├── Discover input files (acquisition.json, data_description.json, platform.json, pophys/)
        ├── Detect rig type (Bergamo vs multiplane) from acquisition.instrument_id
        ├── Branch:
        │   ├── Bergamo → BergamoTiffStitcher.run_converter()
        │   └── Multiplane → TiffSplitterCLI.run_job()
        │       ├── Averaged depth processing
        │       ├── Parent-child FOV matching + QC
        │       └── Vasculature image + QC
        └── Write QC output (quality_control.json)
```

### Step 1: Define a Unified Settings Object (IN THE LIBRARY)

Merge the three scattered settings into **one settings model in the library** with `BaseSettings, cli_parse_args=True`:

```python
# IN LIBRARY: src/aind_pophys_converter/settings.py (new file)
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class PophysConverterSettings(BaseSettings, cli_parse_args=True):
    """Settings for the pophys converter pipeline.

    Uses pydantic-settings with cli_parse_args=True so the library
    handles CLI argument parsing directly. The capsule just calls run().

    Parameters
    ----------
    input_dir : Path
        Top-level input directory containing metadata JSON files
        and a pophys/ subdirectory with TIFF data.
    output_dir : Path
        Directory to write converted outputs (HDF5, TIFFs, QC JSON).
    temp_dir : Optional[Path]
        Scratch directory for intermediate files.
    debug : bool
        If True, clip timeseries for faster debug runs.
    """

    input_dir: Path = Field(
        default=Path("/data"),
        description="Top-level input directory (contains acquisition.json, "
        "data_description.json, platform.json, pophys/)"
    )
    output_dir: Path = Field(
        default=Path("/results"),
        description="Output directory for converted files and QC"
    )
    temp_dir: Optional[Path] = Field(
        default=Path("/scratch"),
        description="Scratch directory for intermediate files"
    )
    debug: bool = Field(
        default=False,
        description="Clip timeseries for debug runs"
    )
```

```python
# IN CAPSULE: code/run_capsule.py — THE ENTIRE FILE (~11 lines)
import aind_pophys_converter.job as job


def run():
    """Run the capsule."""
    job.run()


if __name__ == "__main__":
    run()
```

The capsule is a pure passthrough. All settings, orchestration, and CLI parsing live in the library.

### Step 2: Create PophysConverterJob in the Library

Move ALL orchestration logic from `run_capsule.py:run()` into a job class:

```python
# IN LIBRARY: src/aind_pophys_converter/job.py (new file)
# This module contains: settings, job class, and run() entry point.
# The capsule just does: import aind_pophys_converter.job as job; job.run()
import json
import logging
from pathlib import Path

from aind_pophys_converter.settings import PophysConverterSettings
from aind_pophys_converter.bergamo_stitcher import BergamoSettings, BergamoTiffStitcher
from aind_pophys_converter.mesoscope_splitter import (
    AvgImageTiffSplitter, TiffSplitterCLI, JobSettings, find_split_directories,
)
from aind_pophys_converter.qc import create_fov_matching_qc, create_vasculature_qc


class PophysConverterJob:
    """Top-level pipeline for pophys data conversion and QC."""

    def __init__(self, settings: PophysConverterSettings):
        self.settings = settings

    def run(self):
        """Execute the full conversion pipeline."""
        input_dir = self.settings.input_dir
        output_dir = self.settings.output_dir

        # --- Discover metadata files ---
        acquisition_fp = next(input_dir.rglob("acquisition.json"))
        data_description_fp = next(input_dir.rglob("data_description.json"))
        platform_fp = next(input_dir.rglob("*platform.json"), None)
        if platform_fp is None:
            raise FileNotFoundError(f"No platform.json in {input_dir}")

        with open(acquisition_fp) as f:
            acquisition = json.load(f)
        with open(data_description_fp) as f:
            data_description = json.load(f)

        pophys_dir = next(input_dir.rglob("pophys/"))

        # --- Branch on rig type ---
        if "Bergamo" in acquisition.get("instrument_id", ""):
            self._run_bergamo(pophys_dir, output_dir, acquisition_fp)
        elif "multiplane" in data_description["name"]:
            self._run_multiplane(
                pophys_dir, output_dir, platform_fp, acquisition
            )

    def _run_bergamo(self, pophys_dir, output_dir, acquisition_fp):
        unique_id = "MOp2_3_0"  # TODO: read from CCF
        bergamo_output = output_dir / unique_id
        bergamo_output.mkdir(exist_ok=True)
        settings = BergamoSettings(
            input_dir=pophys_dir,
            output_dir=bergamo_output,
            unique_id=unique_id,
            acquisition_fp=acquisition_fp,  # renamed from session_fp
        )
        BergamoTiffStitcher(settings).run_converter()

    def _run_multiplane(self, pophys_dir, output_dir, platform_fp, acquisition):
        # ... splitting logic (currently lines 388-421 of run_capsule.py)
        # ... averaged depth processing
        # ... QC generation
        pass


def run() -> None:
    """Module-level entry point — capsule calls this directly.

    Following the metadata-manager pattern: settings parse CLI args
    automatically via pydantic-settings cli_parse_args=True.
    """
    settings = PophysConverterSettings()  # parses CLI args automatically
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
    )
    job = PophysConverterJob(settings)
    job.run()
```

### Step 3: Move QC Logic Into the Library

Currently all QC construction lives in the capsule. Move it to a dedicated module:

```python
# IN LIBRARY: src/aind_pophys_converter/qc.py (new file)
#
# Contains:
#   - pending_status() — create a PENDING QCStatus with Seattle timezone
#   - create_fov_matching_qc() — moved from pair_depth_tifs_with_avg_depth_pngs()
#   - create_vasculature_qc() — moved from create_vasculature()
#   - add_border_and_label() — PIL image utility
#   - write_avg_depth_slices() — averaged depth TIF splitting
#
# This module DOES depend on aind-data-schema (QCMetric, QualityControl, etc.)
# and aind-qcportal-schema (DropdownMetric).
```

This means `aind-data-schema` becomes a **library dependency** (in `pyproject.toml`), not just a capsule/Dockerfile dependency.

### Step 4: Update Library pyproject.toml

```toml
# Add to dependencies:
dependencies = [
    # ... existing deps ...
    "pydantic-settings",             # for BaseSettings with cli_parse_args=True
    "aind-data-schema>=2.6.0,<3",
    "aind-data-schema-models>=5.4.1,<6",
    "aind-qcportal-schema>=0.4.0",
    "Pillow",       # for image manipulation (add_border_and_label)
    "pytz",         # for Seattle timezone in QC timestamps
]
```

### Step 5: Update Library Module Layout

```
src/aind_pophys_converter/
├── __init__.py
├── settings.py              # NEW — PophysConverterSettings
├── job.py                   # NEW — PophysConverterJob (top-level orchestrator)
├── qc.py                    # NEW — QC metric/evaluation construction
├── bergamo_stitcher.py      # EXISTING — update session_fp → acquisition_fp
├── mesoscope_splitter.py    # EXISTING — update session.json → acquisition.json
└── utils/
    ├── __init__.py
    ├── full_field_utils.py  # EXISTING
    ├── logging_cfg.py       # EXISTING
    └── tiff_metadata.py     # EXISTING
```

### What Moves Where

| Current Location (capsule) | New Location (library) | Notes |
|---|---|---|
| `PendingStatus()` | `qc.py:pending_status()` | |
| `add_border_and_label()` | `qc.py:add_border_and_label()` | |
| `pair_depth_tifs_with_avg_depth_pngs()` | `qc.py:create_fov_matching_qc()` | Refactor to return QC object, not write JSON directly |
| `write_avg_depth_slices()` | `qc.py:write_avg_depth_slices()` | |
| `create_vasculature()` | `qc.py:create_vasculature_qc()` | Refactor similarly |
| `is_child_session_via_platform_json()` | `job.py:_is_child_session()` | Private method on job |
| `run()` orchestration (lines 356-425) | `job.py:PophysConverterJob.run()` | |
| `JobSettings(BaseSettings)` | `settings.py:PophysConverterSettings(BaseSettings, cli_parse_args=True)` | Library owns CLI parsing; capsule has NO settings class |

### What Stays in the Capsule

Only (~11 lines total):
1. `import aind_pophys_converter.job as job`
2. `def run(): job.run()`
3. `if __name__ == "__main__": run()`

No settings class, no logging setup, no orchestration. Pure passthrough (metadata-manager pattern).

### Impact on Testing

- **Library tests** can now test the full pipeline end-to-end with mock data (no capsule needed)
- **QC tests** can validate metric construction independently
- **Capsule tests** are trivial (if any) — just verify CLI parsing
- Coverage moves from "capsule has no tests" to "library has full coverage"

### Dependency Implications

Moving QC logic into the library means `aind-data-schema` becomes a library dependency. This is a design decision:

**Option A: Schema as core dependency** (recommended)
- Add `aind-data-schema>=2.6.0,<3` to `pyproject.toml` `dependencies`
- Pro: Clean, testable, versioned
- Con: Library now has heavier dep tree

**Option B: Schema as optional dependency**
- Add `qc = ["aind-data-schema>=2.6.0,<3", "aind-qcportal-schema>=0.4.0", "Pillow", "pytz"]` to `[project.optional-dependencies]`
- Pro: Library stays lightweight for users who only need TIFF splitting
- Con: More complex install, conditional imports
- Capsule Dockerfile: `pip install aind-pophys-converter[qc]`

---

## Phase C: Structured Logging with aind-log-utils

**Do this AFTER Phase B is complete and validated against real data.**

### What aind-log-utils Provides

`aind-log-utils` is AIND's standard structured logging library. It provides:
- **Structured JSON logs** with consistent fields across all AIND capsules
- **Dual output:** console + CloudWatch (when AWS creds are available on Code Ocean)
- **Automatic metadata injection** via a custom `LogRecord` factory — hostname, capsule_id, computation_id, subject_id, asset_name, process_name, AWS batch info
- **Start/stop lifecycle logs** with atexit handler
- **Graceful degradation** — console-only when AWS creds aren't available (local dev)

### Integration Pattern

```python
# In pyproject.toml dependencies:
"aind-log-utils"

# In code:
from aind_log_utils.log import setup_logging
```

### setup_logging() Signature

```python
def setup_logging(
    process_name: str,           # Name of this pipeline (e.g., "pophys-converter")
    subject_id: str = "undefined",    # From acquisition.json or data_description.json
    asset_name: str = "undefined",    # Dataset name (e.g., "multiplane-ophys_839909_...")
    send_start_log: bool = True,      # Emit "Starting"/"Stopping" logs (True for capsule entry points)
    disable_existing_loggers: bool = True,
):
```

### How It Works

1. Checks for AWS credentials (via STS)
2. **With AWS creds (Code Ocean):** Configures console + CloudWatch (`watchtower`) handlers. Log group: `aind/internal_logs`, stream: capsule_id. CloudWatch logs include structured fields (subject_id, asset_name, hostname, etc.).
3. **Without AWS creds (local):** Console handler only, with a warning.
4. Injects metadata into every `LogRecord` via a custom factory — so all `logging.info()` calls automatically include structured fields.
5. Registers an atexit handler to log "Stopping" on exit.

### Where to Call setup_logging()

In `job.py:run()`, replace the current `logging.basicConfig(...)` with `setup_logging(...)`:

```python
# BEFORE (Phase B):
def run() -> None:
    settings = PophysConverterSettings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
    )
    job = PophysConverterJob(settings)
    job.run()

# AFTER (Phase C):
def run() -> None:
    settings = PophysConverterSettings()

    # Extract metadata for structured logging
    # (subject_id and asset_name come from the input data)
    acquisition_fp = next(settings.input_dir.rglob("acquisition.json"), None)
    asset_name = settings.input_dir.name if settings.input_dir.name != "data" else "undefined"
    subject_id = "undefined"
    if acquisition_fp:
        import json
        with open(acquisition_fp) as f:
            acq = json.load(f)
        subject_id = acq.get("subject_id", "undefined")

    setup_logging(
        process_name="pophys-converter",
        subject_id=subject_id,
        asset_name=asset_name,
        send_start_log=True,
    )

    job = PophysConverterJob(settings)
    job.run()
```

### Standard Log Fields (injected automatically)

After `setup_logging()`, every `logging.info("...")` call automatically includes:

| Field | Source |
|-------|--------|
| `process_name` | Passed to `setup_logging()` |
| `subject_id` | Passed to `setup_logging()` |
| `asset_name` | Passed to `setup_logging()` |
| `hostname` | `$HOSTNAME` env var |
| `comp_id` | `$CO_COMPUTATION_ID` env var |
| `version` (capsule_id) | `$CO_CAPSULE_ID` env var |
| `log_session` | MD5 hash (timestamp + hostname + pid) |
| `CO_MEMORY`, `CO_CPUS` | Code Ocean resource env vars |
| `AWS_BATCH_JOB_ID`, etc. | AWS Batch env vars |

### Dependencies to Add

```toml
# In library pyproject.toml:
dependencies = [
    # ... existing deps from Phase B ...
    "aind-log-utils",
]
```

```dockerfile
# In Dockerfile:
RUN pip install -U --no-cache-dir \
    # ... existing deps ...
    aind-log-utils
```

### Notes

- `setup_logging()` calls `logging.config.dictConfig()` internally — it replaces all existing handlers. Call it **once** at the top of `run()`, before any other logging.
- The library modules (bergamo_stitcher, mesoscope_splitter) should just use `logging.getLogger(__name__)` as normal — `setup_logging()` configures the root logger, so all child loggers inherit the structured format.
- For library-only use (no capsule), call `setup_logging("pophys-converter", send_start_log=False)` to skip the lifecycle logs.

---

## Execution Checklist

### Phase A: Schema Upgrade

#### A0: Test Data Assembly
1. [ ] Create `code/assemble_test_data.sh` — symlinks data dirs + copies v2 metadata into `/scratch/data/`
2. [ ] Run script and verify `/scratch/data/` has pophys/ (symlink) + acquisition.json + instrument.json (copies)

#### A1: Bump Dependencies
3. [ ] Update `environment/Dockerfile` — `aind-data-schema==2.6.0`, `aind-data-schema-models==5.4.1`
4. [ ] Update `.codeocean/environment.json` — mirror Dockerfile
5. [ ] Verify `aind-qcportal-schema==0.4.0` is compatible with schema v2.6

#### A2: Fix Capsule QC Code (run_capsule.py)
4. [ ] Fix imports — remove `QCEvaluation`, add `QualityControl`, move `Modality` to `aind_data_schema_models`
5. [ ] Fix `PendingStatus()` — verify timezone-aware datetime works with v2 validators
6. [ ] Fix `pair_depth_tifs_with_avg_depth_pngs()` — add modality/stage/tags to each QCMetric, replace QCEvaluation with QualityControl
7. [ ] Fix `create_vasculature()` — same QC v2 pattern
8. [ ] Fix output format — decide single `quality_control.json` vs separate files

#### A3: Fix Capsule File Discovery (run_capsule.py)
9. [ ] `run()` line 361 — `session.json` → `acquisition.json`
10. [ ] `run()` line 375 — `session.get("rig_id")` → `acquisition.get("instrument_id")`
11. [ ] Update all variable names — `session` → `acquisition`, `session_fp` → `acquisition_fp`

#### A4: Fix Library (scratch/aind-pophys-converter/)
12. [ ] `mesoscope_splitter.py:1596` — glob `*acquisition.json` instead of `*session.json`
13. [ ] `mesoscope_splitter.py:1797-1902` — update `data_streams[].ophys_fovs` traversal to v2 structure (ImagingConfig → PlanarImage → Plane)
14. [ ] `mesoscope_splitter.py:1902` — verify `dump_every` field still exists in v2
15. [ ] `bergamo_stitcher.py` — rename `session_fp` → `acquisition_fp`, `_load_session` → `_load_acquisition`
16. [ ] `bergamo_stitcher.py` — verify `stimulus_epochs` structure in v2 Acquisition

#### A5: Fix Library Tests
17. [ ] Update `tests/test_mesoscope_splitter.py` — session.json → acquisition.json fixtures
18. [ ] Update `tests/test_bergamo_stitcher.py` — session → acquisition references

#### A6: Validate
19. [ ] Run library tests — all pass
20. [ ] **Test capsule against real data** — `bash assemble_test_data.sh && python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/`

### Phase B: Capsule/Library Refactor

#### B1: New Library Modules
21. [ ] Create `src/aind_pophys_converter/settings.py` — `PophysConverterSettings(BaseSettings, cli_parse_args=True)`
22. [ ] Create `src/aind_pophys_converter/qc.py` — move QC logic from capsule
23. [ ] Create `src/aind_pophys_converter/job.py` — `PophysConverterJob` orchestrator + `run()` entry point
24. [ ] Update `pyproject.toml` — add `pydantic-settings`, `aind-data-schema>=2.6.0,<3`, `aind-data-schema-models>=5.4.1,<6`, `aind-qcportal-schema`, `Pillow`, `pytz`

#### B2: Capsule Reduction
25. [ ] Reduce `code/run_capsule.py` to ~11 lines (pure passthrough: `import job; job.run()`)

#### B3: Library Tests for New Modules
26. [ ] Write tests for `qc.py` — metric construction, QualityControl output
27. [ ] Write tests for `job.py` — Bergamo vs multiplane branching, file discovery

#### B4: Validate
28. [ ] Run library tests — all pass
29. [ ] **Test capsule against real data** — `bash assemble_test_data.sh && python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/`

### Phase C: Structured Logging

#### C1: Add aind-log-utils Dependency
30. [ ] Add `aind-log-utils` to library `pyproject.toml` dependencies
31. [ ] Add `aind-log-utils` to capsule `environment/Dockerfile`
32. [ ] Add `aind-log-utils` to capsule `.codeocean/environment.json`

#### C2: Integrate setup_logging()
33. [ ] In `job.py:run()` — replace `logging.basicConfig(...)` with `setup_logging(...)` call
34. [ ] Extract `subject_id` from acquisition.json and `asset_name` from input directory name
35. [ ] Verify library modules use `logging.getLogger(__name__)` (not `logging.basicConfig`)

#### C3: Validate
36. [ ] Run library tests — all pass
37. [ ] **Test capsule against real data** — `bash assemble_test_data.sh && python -u run_capsule.py --input_dir /scratch/data/ --output_dir /results/ --temp_dir /scratch/temp/` — verify structured log fields in output
38. [ ] Verify CloudWatch integration works on Code Ocean (if AWS creds available)
