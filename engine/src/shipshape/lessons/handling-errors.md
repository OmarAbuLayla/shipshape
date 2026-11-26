---
concept: Handling errors on purpose
summary: An except block that does nothing hides bugs; catch the error you expect, and say what should happen.
---

## The idea

Exceptions are Python's way of saying "something you assumed is not true". A bare `except:` or `except Exception: pass` answers every one of them with silence: a typo, a missing file, a corrupt recording, even Ctrl+C. The program keeps going with missing data, and the bug shows up much later, somewhere else, looking like a different problem.

Handling an error on purpose means three things: catch only the exception you expect, do something deliberate about it (skip and log, retry, use a default, or stop), and leave everything else to crash loudly.

## Before and after

```python
# Before: every failure disappears, including bugs in your own code
for path in files:
    try:
        recordings.append(load(path))
    except:
        pass
```

```python
# After: the expected problem is handled and reported; anything else still fails
import logging

log = logging.getLogger(__name__)

for path in files:
    try:
        recordings.append(load(path))
    except (OSError, ValueError) as exc:
        log.warning("Skipping %s: %s", path, exc)
```

## Why engineers care

Silent failures are the most expensive kind: the experiment "runs", the numbers come out, and nobody knows that half the recordings were skipped. Reviewers treat a bare `except: pass` as a red flag, because it makes every result downstream of it untrustworthy.

## How Shipshape spots it

Missing data skipped in a loop without a word (`if not os.path.exists(p): continue`, or `except FileNotFoundError: continue`) is reported as `correctness.silent-data-skip`. `isdir()`/`isfile()` used to filter a folder listing is not a skip, and a line with a comment explaining why is treated as deliberate. It flags bare `except:` clauses and `except Exception:` (or `BaseException`) blocks whose body is only `pass`, `...` or `continue`. A comment on the `except` line explaining why the error is safe to ignore counts as handling it on purpose, so such blocks are not flagged. It does not judge whether a more specific handler does the right thing.

## Read more

- [Python tutorial: errors and exceptions](https://docs.python.org/3/tutorial/errors.html)
- [Ruff rule: bare except (E722)](https://docs.astral.sh/ruff/rules/bare-except/)
