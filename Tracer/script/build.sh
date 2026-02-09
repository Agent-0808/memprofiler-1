#!/bin/bash

SCRIPT_PATH="$(cd "$(dirname "$0")" &> /dev/null && pwd)"
ROOT_PATH="$(dirname "$SCRIPT_PATH")"
BUILD_PATH="$ROOT_PATH/build"

# rm -rf $BUILD_PATH
mkdir $BUILD_PATH

cd $BUILD_PATH

cmake ../

# 构建项目
cmake --build .