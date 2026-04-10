# FOV Baseline & Mirrored Planes Fix Report

## Overview

Two related bugs were identified and fixed across the `aind-pophys-converter`
library and the `aind-pophys-converter-capsule`. One dev branch per repo.

---

## Branches

### `fix/fov-baseline-error` (library: `aind-pophys-converter`)

**File:** `src/aind_pophys_converter/mesoscope_splitter.py`

**Problem:** The mesoscope splitter assumed ROI indices were consistent across
all TIFF file types (timeseries, depth, surface, zstack). In practice,
ScanImage can assign ROI indices differently across file types -- roi_index=0
in the depth file pointed to VISp, but roi_index=0 in the surface file pointed
to VISl. The existing check detected the inconsistency but treated it as a
fatal error rather than correcting for it.

**Solution:** Instead of requiring index consistency, match ROIs across splitters
by their physical (x, y) center coordinates. Before processing, validate that
depth and surface image the same set of FOVs (1:1 spatial match). Then build a
remapping table for each splitter that translates from the canonical valid ROI
center index to that splitter's actual roi_index. All three splitters (depth,
surface, zstack) are remapped, so swapped indices in any file type are
corrected transparently.

**Changes:**

- **`validate_roi_pairing(depth_splitter, surface_splitter, tolerance=1.0)`** --
  New function. Before any processing, confirms depth and surface splitters have
  the same set of ROI centers in a 1:1 spatial match within tolerance. Errors on
  count mismatch or any unmatched ROI beyond tolerance.

- **`build_roi_remap(splitter, valid_roi_centers, tolerance=1.0, roi_indices=None)`**
  -- New function. Builds a `{valid_center_index: splitter_roi_index}` dict by
  matching each timeseries-derived valid center to the nearest splitter ROI
  center. Enforces 1:1 mapping and distance tolerance. Accepts optional
  `roi_indices` parameter for splitters without `n_rois` (zstack).

- **`run_job()`** -- Now calls `validate_roi_pairing`, builds remaps for all
  three splitters (depth, surface, zstack), and passes them to
  `_process_single_fov`. The zstack remap uses
  `roi_indices=list(zstack_splitter._roi_to_path.keys())`.

- **`_process_single_fov()`** -- Rewritten. Establishes `baseline_center` from
  the depth splitter, then uses remap dicts to resolve the correct roi_index
  for all three splitters. No fallback to session roi_index. Logs when a remap
  differs from the session roi_index.

- **Removed `_raise_roi_center_error()`** -- Replaced by the remap mechanism.

---

### `fix-handle-mirror-planes` (capsule: `aind-pophys-converter-capsule`)

**File:** `code/run_capsule.py`

**Problem:** Child averaged-depth TIFs were named by `scanfield_z` and matched
to parent TIFs using `abs()`. This caused two issues:

1. Mirrored planes (e.g. `scanfield_z=57` and `scanfield_z=-57`) collided when
   keyed by `abs(float(p.stem))` -- one entry silently overwrote the other in
   the dict, causing wrong pairings or `FileNotFoundError` when the paired file
   was deleted mid-loop.
2. `scanfield_z` fluctuates between sessions due to surface depth changes,
   making it unreliable for cross-session (parent/child) matching.

**Root cause:** `intended_depth` (from platform.json) is the stable cross-session
identifier, but the code was using `scanfield_z` for naming and matching child
TIFs.

**Solution:** Replace `scanfield_z` with `intended_depth` and
`targeted_structure_id` as the basis for naming and matching child TIFs. A
mapping from `scanfield_z` to `(intended_depth, targeted_structure_id)` is built
from platform.json at the start. Child TIFs are named
`<structure_id>_<intended_depth>.tif` (unique per plane), and pairing uses a
direct dict lookup on the compound key -- no tolerance matching, no `abs()`,
no ambiguity.

**Changes:**

- **`write_avg_depth_slices(splitter, output_dir, scanfield_z_to_plane)`** --
  Now accepts a mapping from `scanfield_z` to
  `{intended_depth, targeted_structure_id}` built from platform.json. Names
  output files as `<structure_id>_<intended_depth>.tif` (e.g. `VISp_200.tif`).
  Uses exact match on `scanfield_z` with epsilon=0.01 fallback for floating
  point safety. Raises `RuntimeError` if no match found.

- **`pair_depth_tifs_with_avg_depth_pngs()`** -- Matches child TIFs by
  `(targeted_structure_id, intended_depth)` compound key via direct dict lookup.
  No tolerance matching, no `abs()`, no nearest-neighbor ambiguity. Both parent
  and child are now matched by the same stable identifiers.

- **`run()`** -- Builds the `scanfield_z_to_plane` mapping from platform.json
  imaging planes and passes it to `write_avg_depth_slices`.

---

## Assumptions

### On the data

1. **`intended_depth` + `targeted_structure_id` is unique per plane within a
   session.** If two planes share both values, child TIF filenames
   (`<structure_id>_<intended_depth>.tif`) will collide.

2. **`intended_depth` is consistent across parent and child sessions.** Parent
   TIFs are named by `intended_depth`; child TIFs are now also named by
   `intended_depth`. If the parent session used different intended_depth values
   for the same physical planes, matching will fail.

3. **`scanimage_scanfield_z` in the TIFF metadata matches platform.json's
   `scanimage_scanfield_z` within 0.01.** These come from the same session's
   source of truth. The epsilon guards against floating point representation
   differences only, not real value drift.

4. **Every plane in the averaged depth TIFF has a corresponding entry in
   platform.json.** `write_avg_depth_slices` iterates over the splitter's
   `roi_z_int_manifest` and expects each z_value to exist in the
   `scanfield_z_to_plane` mapping.

5. **Parent TIF filenames follow the pattern
   `<timestamp>_<intended_depth>_<targeted_structure_id>_depth.tif`.** The glob
   in `pair_depth_tifs_with_avg_depth_pngs` depends on this naming convention.

6. **The `parent_session` field in platform.json reliably indicates child
   sessions.** `is_child_session_via_platform_json` gates the entire pairing
   code path on this field being non-null.

### On the splitter logic

7. **All splitters (timeseries, depth, surface, zstack) image the same set of
   physical FOVs.** `validate_roi_pairing` checks depth vs surface explicitly.
   The remaps check each splitter against the timeseries-derived valid centers.
   If any splitter is missing a FOV or has an extra one, the remap will fail.

8. **The timeseries splitter's ROI centers are the source of truth.**
   `valid_roi_centers` is derived from the timeseries splitter and all other
   splitters are matched against it.

9. **The depth splitter shares roi_index ordering with the timeseries
   splitter.** `baseline_center` is established by looking up
   `depth_splitter.roi_center(i_roi=roi_index)` using the session's `roi_index`
   directly. If the depth splitter also has swapped indices relative to the
   timeseries, `baseline_center` would be wrong. (Note: the depth and
   timeseries data showed identical centers in all tested datasets.)

10. **ROI centers within a single splitter are far enough apart to be
    unambiguous.** `get_valid_roi_centers` deduplicates with eps=0.01.
    `build_roi_remap` uses nearest-neighbor with a 1.0 tolerance. If two FOVs
    have centers closer than the tolerance, the 1:1 matching could pair them
    incorrectly.

11. **ROI centers between splitters for the same physical FOV are within 1.0
    unit of each other.** This is the tolerance used in `validate_roi_pairing`
    and `build_roi_remap`. In tested data, offsets were ~0.14 between depth and
    surface for the same FOV, while distinct FOVs were ~10.7 apart.

12. **Each zstack TIFF has exactly one ROI with `discretePlaneMode==0`.** The
    zstack splitter raises an error if this isn't the case. The remap depends
    on `_roi_to_path` being correctly populated from this logic.

13. **`zstack_splitter._roi_to_path` accurately reflects the zstack's ROI
    indices.** The zstack remap accesses this private attribute to get the list
    of valid roi indices. If the internal structure of `ZStackSplitter` changes,
    this will break.
