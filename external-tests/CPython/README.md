# Profiling CPython 3.12 (pyperformance) using MemProfiler

This guide explains how to use **MemProfiler** (`mprofiler`) to analyze the memory allocation behavior of CPython 3.12 while running the `pyperformance` benchmark suite.

When running tests, it automatically creates and configures virtual environments (venvs) for isolation. If we attach MemProfiler to the main `pyperformance` process directly, it will capture a massive amount of irrelevant data (e.g., venv creation, file copying), adding noise to the analysis.

**The Solution:**
By modifying the `_prep_cmd` function inside the `pyperformance` source code—which is responsible for generating the final execution command—we can dynamically inject `mprofiler` as a wrapper **only** when the actual benchmark script is executed. This ensures MemProfiler only profiles the target benchmark script, ignoring the environment setup phase.

---

## Build CPython (Debug Mode)

To allow MemProfiler to capture symbol information, we need to build CPython in Debug mode.

```bash
# Clone the CPython repository and checkout the 3.12 branch
git clone --branch 3.12 https://github.com/python/cpython.git cpython-3.12
cd cpython-3.12
mkdir build-debug
cd build-debug

# Configure for Debug mode
../configure --with-pydebug

# Build CPython
make
```

Once completed, a `python` executable will be generated in the current directory.

---

## Install pyperformance

Install `pyperformance` to your local user directory using Python 3.12:

```bash
python3.12 -m pip install --user pyperformance
```

---

## Inject MemProfiler into pyperformance

After installation, you need to replace the `_benchmark.py` file inside the `pyperformance` package. *(You can use the provided modified file attachment).*

**File Location**

```text
~/.local/lib/python3.12/site-packages/pyperformance/_benchmark.py
```

### Modification Details:

Locate the `_prep_cmd` function in `_benchmark.py`. We modified this function to prepend `mprofiler` to the Python execution command.

Here is the modified code snippet. **Note:** Please update the `mprofiler` and `output_dir` variables to your actual paths.

```python
def _prep_cmd(python, script, opts, runid, on_set_envvar=None):
    # Populate the environment variables.
    env = dict(os.environ)
    def set_envvar(name, value):
        env[name] = value
        if on_set_envvar is not None:
            on_set_envvar(name)
        
    # on_set_envvar() may update "opts" so all calls to set_envvar()
    # must happen before building argv.
    set_envvar('PYPERFORMANCE_RUNID', str(runid))

    # ========================== MemProfiler Injection ==========================
    # TODO: Provide the paths to MemProfiler and the output directory here
    output_dir = 'MemProfiler-CPython-test'
    mprofiler = '/path/to/mprofiler'
  
    # Configure mprofiler: silence logs, specify output dir, and categorize by benchmark name
    mprof_arg = [
        '--no-print-log', 
        '--save-dir', output_dir, 
        '--category', runid.bench.name
    ]
  
    # Add extra metadata
    mprof_extra = [
        '--extra', 
        f'projectID=cpython,version=3.12,bench={runid.bench.name},runid={runid},venv={python}'
    ]

    # Build argv. 
    # mprofiler and its arguments are injected before the python executable.
    argv = [
        mprofiler, *mprof_arg, *mprof_extra, 
        python, '-u', script,
        *(opts or ()),
    ]
    # ===========================================================================

    # Debug prints to verify the command
    print('benchname = [%s]' % runid.bench.name)   
    print('python = [%s]' % python)
    print('script = [%s]' % script)
    print('opts = [%s]' % ' '.join(map(repr, opts)))
    print('argv = [%s]' % ', '.join(map(repr, argv)))

    return argv, env
```

---

## Run the Benchmark and Analyze

Once the modification is in place, you can run the benchmark suite just like you normally would.
Make sure to specify the Debug build of CPython you compiled in Step 1 as the target interpreter:

```bash
pyperformance run --python /path/to/cpython/python
```

After the benchmark suite finishes, The trace files will be saved in the `output_dir` directory in category.
You can analyze the results using the MemProfiler Analyzer.
