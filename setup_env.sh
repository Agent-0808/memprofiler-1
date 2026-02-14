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

echo "Attempting to install packages..."

# 定义包列表："包名=版本" 或 "包名"
declare -a PACKAGES=(
    "cmake=3.22.1-1ubuntu1.22.04.2"
    "build-essential=12.9ubuntu3"
    "libdw-dev=0.186-1ubuntu0.1"
    "libelf-dev=0.186-1ubuntu0.1"
    "libzstd-dev=1.4.8+dfsg-3build1"
    "libunwind-dev=1.3.2-2build2.1"
    "libboost-all-dev=1.74.0.3ubuntu7"
    "python3-pip=22.0.2+dfsg-1ubuntu0.7"
)

# Packages that failed to install with specified version
declare -a VERSION_MISMATCH_PKGS=()

for pkg in "${PACKAGES[@]}"; do
    if sudo apt install -y "$pkg" 2>/dev/null; then
        echo "  [OK] $pkg"
    else
        # Record package that failed to install with specified version
        pkg_name="${pkg%%=*}"
        echo "  [FAIL] $pkg, trying $pkg_name without version..."
        if sudo apt install -y "$pkg_name"; then
            echo "  [OK] $pkg_name (no version constraint)"
            VERSION_MISMATCH_PKGS+=("$pkg")
        else
            echo "  [ERROR] Failed to install $pkg_name"
        fi
    fi
done

echo "Package installation completed."

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

if [ ${#VERSION_MISMATCH_PKGS[@]} -gt 0 ]; then
    echo ""
    echo "=========================================="
    echo "Warning: The following packages failed to install with specified version:"
    for pkg in "${VERSION_MISMATCH_PKGS[@]}"; do
        echo "  - $pkg"
    done
    echo "=========================================="
fi

echo ""
echo "=========================================="
echo "Environment setup completed successfully!"
echo "=========================================="
