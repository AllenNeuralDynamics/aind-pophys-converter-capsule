# Fix: Match child planes by intended_depth instead of scanfield_z

## Problem

`pair_depth_tifs_with_avg_depth_pngs` matches child averaged-depth TIFs to parent
depth TIFs using `scanimage_scanfield_z`. This is unreliable for two reasons:

1. **Mirrored planes**: scanfield_z can be positive or negative for the same
   physical depth (e.g. 57 and -57). The current `abs()` approach causes dict
   key collisions, silently pairing wrong planes.

2. **Day-to-day fluctuations**: scanfield_z varies between sessions due to
   surface depth changes. It is not a stable identifier across parent/child
   sessions.

`intended_depth` (from platform.json) is consistent across sessions and uniquely
identifies each plane. The parent TIFs are already matched by `intended_depth` —
the child TIFs should be too.

## Current flow

1. `write_avg_depth_slices` writes child TIFs named by scanfield z-value
   (e.g. `57.0.tif`, `-57.0.tif`) derived from the TIFF metadata via
   `splitter._z_from_int(z_int)`.

2. `pair_depth_tifs_with_avg_depth_pngs` builds a dict `{z_value: path}` from
   those filenames and matches each platform.json plane by closest
   `scanimage_scanfield_z`.

## Proposed fix

### 1. Build a scanfield_z → intended_depth mapping from platform.json

In `pair_depth_tifs_with_avg_depth_pngs`, after loading `imaging_planes`,
build a lookup:

```python
scanfield_z_to_intended_depth = {
    plane["scanimage_scanfield_z"]: plane["intended_depth"]
    for plane in imaging_planes
}
```

### 2. Change `write_avg_depth_slices` to accept this mapping and name files by intended_depth

Update the signature to accept the mapping. For each `(roi_idx, z_int)`,
resolve `z_value = splitter._z_from_int(z_int)`, do an **exact lookup** in
the mapping, and name the output file by the corresponding `intended_depth`.
Error if the z_value is not found — within the same session these values come
from the same source of truth, so any mismatch is a real problem.

```python
def write_avg_depth_slices(splitter, output_dir: Path, scanfield_z_to_depth: dict):
    output_dir.mkdir(exist_ok=True, parents=True)

    for roi_idx, z_int in splitter.roi_z_int_manifest:
        z_value = splitter._z_from_int(z_int)

        intended_depth = scanfield_z_to_depth.get(z_value)
        if intended_depth is None:
            raise RuntimeError(
                f"scanfield_z={z_value} from TIFF metadata not found in "
                f"platform.json. Known values: {list(scanfield_z_to_depth.keys())}"
            )
        tif_path = output_dir / f"{intended_depth}.tif"

        with tempfile.NamedTemporaryFile(suffix=".tif") as tmp_tif:
            tmp_path = Path(tmp_tif.name)
            splitter.write_output_file(
                i_roi=roi_idx, z_value=z_value, output_path=tmp_path
            )
            img_array = tifffile.imread(tmp_path)

        tifffile.imwrite(tif_path, img_array.astype(np.float32))
```

### 3. Simplify pairing in `pair_depth_tifs_with_avg_depth_pngs`

With child TIFs now named by `intended_depth`, the matching becomes a direct
lookup instead of a nearest-z search:

```python
child_tifs = {int(float(p.stem)): p for p in avg_slice_dir.glob("*.tif")}

for plane in imaging_planes:
    intended_depth = plane["intended_depth"]
    child_tif_path = child_tifs.get(intended_depth)
    if child_tif_path is None:
        print(f"WARNING: No child TIF for intended_depth={intended_depth}")
        continue
    # ... parent matching by intended_depth + targeted_structure_id (unchanged)
```

No `abs()`, no nearest-neighbor ambiguity, no mirrored plane collisions.

### 4. Update the call site in `run()`

Pass the mapping (or platform planes) to `write_avg_depth_slices`:

```python
with open(platform_fp) as f:
    platform_json = json.load(f)
imaging_planes = [
    plane
    for group in platform_json.get("imaging_plane_groups", [])
    for plane in group.get("imaging_planes", [])
]
scanfield_z_to_depth = {
    p["scanimage_scanfield_z"]: p["intended_depth"]
    for p in imaging_planes
}

splitter = AvgImageTiffSplitter(avg_depth_path)
write_avg_depth_slices(splitter, output_dir, scanfield_z_to_depth)
```

### 5. Revert the intermediate abs() fix

The two-line fix on lines 151/183 becomes unnecessary since we no longer
key or match by scanfield_z at all. Revert those changes.

## Files changed

- `code/run_capsule.py` — all changes are in this file:
  - `write_avg_depth_slices`: new parameter, name files by intended_depth
  - `pair_depth_tifs_with_avg_depth_pngs`: match child TIFs by intended_depth directly
  - `run()`: build mapping from platform.json, pass to write function

## Risks / edge cases

- **Multiple ROIs at the same intended_depth**: The current dataset has all
  planes at `targeted_structure_id=385` with unique intended_depths. If two
  ROIs share an intended_depth, the child TIF filename would collide. If this
  is possible, the filename should include `targeted_structure_id` as well
  (e.g. `385_160.tif`). Check with domain experts.

- **Exact match assumption**: We assume the splitter's z_value exactly matches
  platform.json's scanimage_scanfield_z since they come from the same session's
  source of truth. If this assumption ever breaks (e.g. floating point
  representation differences), the error will surface immediately rather than
  silently mismatching.
