#!/usr/bin/env bash
# Dev environment reset: clean outputs, preserve library, assemble test data.
set -e

echo "Cleaning /results/..."
rm -rf /results/*

echo "Cleaning /scratch/ (preserving aind-pophys-converter)..."
find /scratch -mindepth 1 -maxdepth 1 ! -name 'aind-pophys-converter' -exec rm -rf {} +

echo "Installing aind-pophys-converter in editable mode..."
pip install -e /scratch/aind-pophys-converter/

echo "Assembling test data..."
bash "$(dirname "$0")/assemble_test_data.sh"

echo "Dev environment ready."
