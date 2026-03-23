#!/usr/bin/env bash
# Assemble /scratch/data/ from split v1-data + v2-metadata assets.
# Symlinks data dirs (read-only, no disk cost), copies v2 metadata JSON.
set -e

PRIMARY="/data/multiplane-ophys_839909_2026-02-26_15-11-01"
V2_META="/data/multiplane-ophys_839909_2026-02-26_15-11-01_metadata-upgrader-split-v2-metadata"
TARGET="/scratch/data"

rm -rf "$TARGET"
mkdir -p "$TARGET"

# Symlink data directories (read-only, no disk cost)
for dir in pophys; do
    ln -s "$PRIMARY/$dir" "$TARGET/$dir"
done

# Copy v2 metadata JSON files
for f in acquisition.json instrument.json data_description.json procedures.json processing.json subject.json; do
    cp "$V2_META/$f" "$TARGET/"
done


echo "Assembled test data at $TARGET"
ls -la "$TARGET"
