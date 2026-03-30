#!/usr/bin/env bash
# Copy pophys data + v2 metadata into /results/ for publishing as a combined data asset.
set -euo pipefail

# # --- multiplane-ophys_839909_2026-02-26_15-11-01 ---
# PRIMARY="/data/multiplane-ophys_839909_2026-02-26_15-11-01"
# V2_META="/data/multiplane-ophys_839909_2026-02-26_15-11-01_metadata-upgrader-split-v2-metadata"
# TARGET="/results/multiplane-ophys_839909_2026-02-26_15-11-01_v2"

# echo "Target: $TARGET"
# mkdir -p "$TARGET"

# echo "Copying pophys/..."
# cp -r "$PRIMARY/pophys" "$TARGET/pophys"

# echo "Copying v2 metadata..."
# for f in acquisition.json instrument.json data_description.json procedures.json processing.json subject.json; do
#     cp "$V2_META/$f" "$TARGET/$f"
# done

# echo "Done: $TARGET"
# ls -lh "$TARGET"

# --- single-plane-ophys_767715_2025-07-25_17-40-22 ---
PRIMARY="/data/single-plane-ophys_767715_2025-07-25_17-40-22"
V2_META="/data/single-plane-ophys_767715_2025-07-25_17-40-22_metadata-upgrader-split-v2-metadata"
TARGET="/results/single-plane-ophys_767715_2025-07-25_17-40-22_v2"

echo "Target: $TARGET"
mkdir -p "$TARGET"

echo "Copying pophys/..."
cp -r "$PRIMARY/pophys" "$TARGET/pophys"

echo "Copying v2 metadata..."
for f in acquisition.json instrument.json data_description.json procedures.json processing.json subject.json; do
    cp "$V2_META/$f" "$TARGET/$f"
done

echo "Done: $TARGET"
ls -lh "$TARGET"
