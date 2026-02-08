# Tracer

## Get Started

```bash
mprofiler [arguments...] <target_executable> [arguments for target executable]
```

## Arguments

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

## Repo Structure

```text
Tracer/
├── include/            # External Dependencies (Boost, etc.)
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
├── CMakeLists.txt      # Project Build Config
└── README.md           # Documentation
```
