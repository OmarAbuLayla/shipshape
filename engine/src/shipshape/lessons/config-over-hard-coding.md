---
concept: Config over hard-coding
summary: Paths and settings that only exist on your machine belong in a config file, an argument or an environment variable, not in the code.
---

## The idea

`DATA = "C:/Users/me/Desktop/emg_data_FINAL2"` works perfectly, on one laptop. Anyone else, including you on the lab server or in two years, has to find and edit that line before anything runs, and the edit then sits in version control as a change to the code. Settings that differ between machines or runs (data folders, output folders, sampling rates you experiment with) are configuration, and configuration should live outside the code.

The usual options, from simplest: a path relative to the project, a command-line argument, an environment variable, or a small config file (YAML, TOML) that each machine can adapt.

## Before and after

```python
# Before
DATA_DIR = "C:/Users/me/Desktop/emg_data_FINAL2"
```

```python
# After: relative to the project by default, overridable per machine
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("EMG_DATA_DIR", PROJECT / "data"))
```

## Why engineers care

Hard-coded paths are the first thing that breaks when code moves: to a colleague, a cluster, a container, a reviewer trying to reproduce your results. They also leak details you may not want to publish, like user names and folder layouts.

## How Shipshape spots it

It looks for string literals that are absolute, machine-specific paths: Windows drive paths, and Unix paths under `/home`, `/Users`, `/mnt` and similar. Test files are skipped, because tests use made-up absolute paths on purpose. It does not see paths built at runtime from pieces, and it does not judge relative paths.

## Read more

- [The Twelve-Factor App: store config in the environment](https://12factor.net/config)
- [Python: pathlib](https://docs.python.org/3/library/pathlib.html)
