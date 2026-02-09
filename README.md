# memprofiler

memory tracing tool, used for offline debugging

## Environment

- Ubuntu 22.04
- CMake 3.22.1
- GCC 12.3.0
- Python >= 3.12

### Clone the Repository

```bash
git clone https://github.com/ibelie/memprofiler.git
cd memprofiler
```

### Install Dependencies

```bash
sudo apt update
sudo apt install -y cmake build-essential libdw-dev libelf-dev libzstd-dev libunwind-dev libboost-all-dev python3-pip
```

## Get Started

```bash
bash ./setup_env.sh
bash ./run.sh
```

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

### Install Python Dependencies

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
