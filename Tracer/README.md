# Tracer

## Build

```bash
bash ./script/build.sh
```

## Usage

```
Usage: mprofiler [OPTION...] [COMMAND]...

  Examples:
    mprofiler -p 12345        # Profile progress with specified pid(12345).
    mprofiler command args... # Run command with args and profile it.
  
  Options:
    -h, --help          Show help options
    -p, --pid           Specified pid of target progress
    --no-trace          Don't get trace data
    --no-stack          Don't get stack trace
    --no-save           Don't save trace data  
    --save-dir          Specified save directory
    --category          Specified save category
                            Preset: "/name/time" "/name-time" "time-name" "/name"
    --stack             Specified max stack trace depth, -1 means don't trace
    --no-print-log      Don't print logs
    --no-print-stack    Don't print stack trace
    --no-print-save     Don't print saved entries
    --no-print-extra    Don't print extra info
    --extra key=value   Specified extra key-value pair(Saved in statinfo.txt)
```

## Examples

* Profile a target executable
  Output files will be saved in `tracedata/[target_executable]/[timestamp]/`

```bash
mprofiler --no-print-save --no-print-stack path/to/target_executable
```

* Profile a target executable with arguments
Output files will be saved in `output/[target_executable]/`

```bash
mprofiler --no-print-save --no-print-stack --category /name path/to/target_executable [arguments for target_executable]
```

* Profile a target executable with verbose info
Output files will be saved in `output/[target_executable]/`

```bash
mprofiler --save-dir output --category /name target_executable [arguments for target_executable]
```

## Repo Structure

```text
Tracer/
├── src/                # Source Code
│   ├── main.cpp            # Entry Point
│   ├── tracer.cpp/h        # Core Tracer Logic
│   ├── debugger.h          # Debugger Utilities
│   ├── config.cpp/h        # Configuration Manager
│   ├── target_loader.cpp/h # Target Process Loader
│   ├── trace_data.cpp/h    # Trace Data Structures
│   ├── utils.h             # General Utilities
│   ├── zip_stream.cpp/h    # Zip Compression Stream
│   └── CMakeLists.txt      # Source Build Config
├── test/               # Example Target Programs
├── scripts/            # Scripts for Build
├── CMakeLists.txt      # Project Build Config
└── README.md           # Documentation
```
