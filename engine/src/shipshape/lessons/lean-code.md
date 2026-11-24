---
concept: Keeping code lean
summary: Unused imports and variables are leftovers; they slow reading, add dependencies and sometimes hide a typo.
---

## The idea

Code accumulates leftovers: an import from an experiment you abandoned, a variable you computed and never used. Each one costs a little: readers wonder what it is for, an unused import can pull in a heavy package (or fail if it is not installed), and an unused variable is sometimes a typo for one you meant to use. Deleting them is safe and makes the real code easier to see.

## Before and after

```python
# Before
import os
import sys
import json

import numpy as np


def mean_rms(windows):
    n = len(windows)
    return np.mean(np.sqrt(np.mean(windows**2, axis=1)))
```

```python
# After
import numpy as np


def mean_rms(windows):
    return np.mean(np.sqrt(np.mean(windows**2, axis=1)))
```

## Why engineers care

Lean code is quicker to review and has fewer surprises. Linters fix most of this automatically (`ruff check --fix`), so leftovers in shared code suggest the tools were not run.

## How Shipshape spots it

Through ruff's rules F401 (imports that are never used) and F841 (local variables assigned and never read). Imports kept on purpose, for example to re-export names from a package's `__init__.py`, can look unused.

## Read more

- [Ruff rule: unused-import (F401)](https://docs.astral.sh/ruff/rules/unused-import/)
- [Ruff rule: unused-variable (F841)](https://docs.astral.sh/ruff/rules/unused-variable/)
