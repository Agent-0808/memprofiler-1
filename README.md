# memprofiler

memory tracing tool, used for offline debugging

## Environment

- Ubuntu 22.04
- CMake 3.22.1
- GCC 12.3.0
- Python >= 3.12

## Tracer

### Build Tracer

```bash
cd ./Tracer/
bash ./script/build.sh
```

### Trace

```bash
cd build/
./src/mprofiler --category /name --no-print-save --no-print-stack ./test/test_case 
```

Output tracedata will be in `Tracer/build/tracedata/test_case/`

## Analyzer

### Install uv

```bash
python -m pip install uv
```

### Install Dependencies

```bash
cd ../../Analyzer/
uv sync
```

### Run Analyzer

```bash
bash script/run_analyzer.sh
```

### Run Visualizer

```bash
uv run visualizer/metrics_plotter.py --base-dir ../Tracer/build/ --benchmark-name test_case
```

## License

This project is licensed under the BSD 2-Clause License - see the [LICENSE](LICENSE) file for details.

## Copyright

Copyright (c) 2026, Chen Jie, Joungtao, Xuzheng Jiang. All rights reserved.
