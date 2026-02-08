#!/bin/bash

# MemProfiler Setup Script
# This script automates the setup and execution process described in README.md

set -e

echo "=========================================="
echo "MemProfiler Setup and Execution Script"
echo "=========================================="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Step 1: Build Tracer
echo ""
echo "[Step 1] Building Tracer..."
cd ./Tracer/
bash ./script/build.sh
cd "$SCRIPT_DIR"

# Step 2: Run Tracer
echo ""
echo "[Step 2] Running Tracer..."
cd Tracer/build/
./src/mprofiler --category /name --no-print-save --no-print-stack ./test/test_case
cd "$SCRIPT_DIR"

echo ""
echo "Tracedata is saved in: Tracer/build/tracedata/test_case/"

# Step 3: Install uv
echo ""
echo "[Step 3] Installing uv..."
pip install uv

# Step 4: Install Analyzer Dependencies
echo ""
echo "[Step 4] Installing Analyzer dependencies..."
cd Analyzer/
uv sync
cd "$SCRIPT_DIR"

# Step 5: Run Analyzer
echo ""
echo "[Step 5] Running Analyzer..."
cd Analyzer/
bash script/run_analyzer.sh
cd "$SCRIPT_DIR"

# Step 6: Run Visualizer
echo ""
echo "[Step 6] Running Visualizer..."
cd Analyzer/
uv run visualizer/metrics_plotter.py --base-dir ../Tracer/build/ --benchmark-name test_case
cd "$SCRIPT_DIR"

echo ""
echo "=========================================="
echo "Setup and execution completed successfully!"
echo "=========================================="
