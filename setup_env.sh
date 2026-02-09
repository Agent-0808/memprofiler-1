#!/bin/bash

# MemProfiler Environment Setup Script
# This script handles environment setup and compilation

set -e

echo "=========================================="
echo "MemProfiler Environment Setup"
echo "=========================================="

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Add ~/.local/bin to PATH for uv
export PATH="$HOME/.local/bin:$PATH"

# Step 1: Install system dependencies
echo ""
echo "[Step 1] Installing system dependencies..."
sudo apt update
sudo apt install -y cmake build-essential libdw-dev libelf-dev libzstd-dev libunwind-dev libboost-all-dev python3-pip

# Step 2: Build Tracer
echo ""
echo "[Step 2] Building Tracer..."
cd ./Tracer/
bash ./script/build.sh
cd "$SCRIPT_DIR"

# Step 3: Install uv
echo ""
echo "[Step 3] Installing uv..."
python3 -m pip install uv

# Step 4: Install Analyzer Dependencies
echo ""
echo "[Step 4] Installing Analyzer dependencies..."
cd Analyzer/
uv sync
cd "$SCRIPT_DIR"

echo ""
echo "=========================================="
echo "Environment setup completed successfully!"
echo "=========================================="
