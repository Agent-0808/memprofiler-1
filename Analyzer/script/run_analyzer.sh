#!/bin/bash

cd "$(dirname "$0")/.."

uv run main.py \
    --input "../Tracer/build/tracedata/test_case" \
    --memory-layout \
    --snapshot-interval "10000000000" \
    --compact-json \
    --skip-cpp \
    --final-events \
    --callstack-depth "-1" \
    --enable-peak-focus \
    --peak-focus-events "50" \
    --peak-focus-context "32768" \
    --peak-focus-output-events "500" \
    --generate-peak-before-layout \
    --events-after-peak "10" \
    --peak-detection-window "50" \
    --peak-window "5000000000" \
    --clear-cache \
    --clear-output-dir
