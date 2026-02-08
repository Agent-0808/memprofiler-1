# Analyzer

## Install uv

```bash
pip install uv
# or use:
python -m pip install uv
```

## Dependency

```bash
uv sync
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
