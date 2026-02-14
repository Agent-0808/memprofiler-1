# Analyzer
This component parses compressed logs and performs complex heap state reconstruction.

## Get Started

### Install uv

```bash
pip install uv
# or use:
python -m pip install uv
```

### Install Dependencies

```bash
uv sync
```

## Usage

### Analyze

```
usage: main.py --input INPUT_FOLDER [arguments]

options:
  --input INPUT         (str, required) Path to input folder, containing memory.profile file
  --output-dir OUTPUT_DIR
                        (str, default=output) Path to output folder
  --clear-output-dir    (bool, default=False) Clear output directory
  --compact-json        (bool, default=False) Output as compact JSON format
  --fragmentation       (bool, default=False) Whether to generate fragmentation report
  --brk-events          (bool, default=False) Whether to generate brk events report
  --memory-layout       (bool, default=False) Whether to generate memory layout report
  --final-events        (bool, default=False) Whether to generate final events report
  --report-for-snapshots
                        (bool, default=False) Whether to generate report for all snapshots
  --timestamps TIMESTAMPS
                        (str | None, default=None) Specified snapshot timestamps (comma-separated)
  --snapshot-interval SNAPSHOT_INTERVAL
                        (int | None, default=None) Specified snapshot interval (nanoseconds)

  --peak-window PEAK_WINDOW
                        (int, default=500000000) Peak Context Size (nanoseconds)
  --peak-detection-window PEAK_DETECTION_WINDOW
                        (int, default=500) Peak detection window (Events)
  --callstack-depth CALLSTACK_DEPTH
                        (int, default=-1) Callstack depth
  --events-after-peak EVENTS_AFTER_PEAK
                        (int, default=0) Add extra events after the peak (for visualization)

  --enable-peak-focus   (bool, default=False) Enable peak focus
  --peak-focus-events PEAK_FOCUS_EVENTS
                        (int, default=50) Number of events to focus on after the peak
  --peak-focus-context PEAK_FOCUS_CONTEXT
                        (int, default=8192) Context expansion size (Bytes)
  --peak-focus-output-events PEAK_FOCUS_OUTPUT_EVENTS
                        (int, default=500) Final prune event count
  --generate-peak-before-layout
                        (bool, default=False) Generate peak before layout (for visualization)

  --no-cache            (bool, default=False) Disable Cache
  --clear-cache         (bool, default=False) Clear Cache
  --log-interval LOG_INTERVAL
                        (int, default=2000) Log interval (Events)
  --skip-cpp            (bool, default=False) Whether to skip C++ Operations (new/delete etc.)
```

### Visualize

```
usage: metrics_plotter.py [--timestamp TIMESTAMP] [--benchmark-name BENCHMARK_NAME] [--base-dir BASE_DIR] [-h]

options:
  --timestamp TIMESTAMP
                        (str, default=final)
  --benchmark-name BENCHMARK_NAME
                        (str, default=test_case)
  --base-dir BASE_DIR   (Path | None, default=Path(__file__).parent.parent)
```

## Run

```bash
# Analyze
uv run main.py --input ...

# Visualize
uv run visualizer/metrics_plotter.py --input ...
```

## Repo Structure

```text
Analyzer/
├── main.py             # Entry Point
├── parser_core.py      # Parser Core
├── analysis.py         # Analysis
├── common_types.py     # Type Classes
├── config.py           # Config Class
├── output_handler.py   # Handle Output
├── snapshot_manager.py # Snapshot Manager
├── utils.py            # Utils
├── visualizer/         # Tool: Visualizer
│   ├── metrics_plotter.py   # Plot Metrics
│   ├── memory_visualizer.py # Memory Visualizer
│   └── patchMatplotlib.py   # Patch Matplotlib and ttkbootstrap
├── pyproject.toml      # Project Config
├── uv.lock             # Lock File
└── README.md           # Documentation
```
