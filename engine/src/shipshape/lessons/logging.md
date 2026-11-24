---
concept: Logging instead of printing
summary: print() is fine in scripts; in code others import, use logging so the caller decides what is shown and where it goes.
---

## The idea

`print("loading", folder)` is the quickest way to see what code is doing, and in a one-off script that is fine. In a module that other code imports, those prints become noise nobody can switch off: they flood notebooks, cluttering test output and job logs. The `logging` module solves this. Each module asks for a named logger and reports at a level (debug, info, warning, error); the application decides once which levels to show and where to send them (screen, file, nothing).

## Before and after

```python
# Before
def load_subject(subject_id):
    print("loading subject", subject_id)
    ...
```

```python
# After: the module logs; whoever runs the program decides what is shown
import logging

log = logging.getLogger(__name__)


def load_subject(subject_id):
    log.info("Loading subject %s", subject_id)
    ...


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
```

## Why engineers care

Logs are how you find out what happened in a long training run or on a server: with timestamps, levels and the module name. Prints give you none of that and cannot be silenced, so code full of prints is hard to reuse and hard to debug at scale.

## How Shipshape spots it

It counts `print()` calls in importable modules and reports them once it finds five or more. Scripts, command-line interfaces, entry points (files with an `if __name__ == "__main__":` block) and UI code are exempt, because printing is their job.

## Read more

- [Python: logging HOWTO](https://docs.python.org/3/howto/logging.html)
