#!/bin/bash

# MemProfiler Run Script
# This script handles execution of Tracer, Analyzer, and Visualizer

set -e

echo "=========================================="
echo "MemProfiler Execution"
echo "=========================================="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Add ~/.local/bin to PATH for uv
export PATH="$HOME/.local/bin:$PATH"

# Step 1: Run Tracer
echo ""
echo "[Step 1] Running Tracer..."
cd Tracer/build/
./src/mprofiler --category /name --no-print-save --no-print-stack ./test/test_case
cd "$SCRIPT_DIR"

echo ""
echo "Tracedata is saved in: Tracer/build/tracedata/test_case/"

# Step 2: Run Analyzer
echo ""
echo "[Step 2] Running Analyzer..."
cd Analyzer/
bash script/run_analyzer.sh
cd "$SCRIPT_DIR"

# Step 3: Run Visualizer
echo ""
echo "[Step 3] Running Visualizer..."
cd Analyzer/
uv run visualizer/metrics_plotter.py --base-dir ../Tracer/build/ --benchmark-name test_case
cd "$SCRIPT_DIR"

echo ""
echo "=========================================="
echo "Execution completed successfully!"
echo "=========================================="
