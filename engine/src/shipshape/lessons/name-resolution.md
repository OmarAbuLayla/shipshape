---
concept: How Python resolves names
summary: A name that is never defined only fails when that line runs, which may be hours into a job or never in your tests.
---

## The idea

Python looks names up when a line executes: first in the function, then in enclosing functions, then in the module, then in the built-ins. A typo (`recrodings`), a missing import, or a variable defined only in one branch is not an error until that exact line runs. In a training script that can mean a crash after three hours, at the evaluation step.

Linters find these names statically, before anything runs, which is why they are worth running on every save.

## Before and after

```python
# Before: works until the except branch runs
def load(path):
    try:
        return read(path)
    except OSError:
        log.warning("missing %s", path)  # `log` was never defined
```

```python
# After
import logging

log = logging.getLogger(__name__)


def load(path):
    try:
        return read(path)
    except OSError:
        log.warning("missing %s", path)
```

## Why engineers care

These are guaranteed crashes waiting for the right moment. Catching them before running is free, and code that has them signals it was never checked by a linter.

## How Shipshape spots it

Through ruff's rule F821: names used but never defined, imported or built in. Names created dynamically (for example by `globals()` or `exec`) look undefined to it.

## Read more

- [Python reference: resolution of names](https://docs.python.org/3/reference/executionmodel.html#resolution-of-names)
- [Ruff rule: undefined-name (F821)](https://docs.astral.sh/ruff/rules/undefined-name/)
