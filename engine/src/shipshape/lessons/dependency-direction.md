---
concept: Dependency direction
summary: When two modules import each other, neither can be understood or tested alone; dependencies should point one way.
---

## The idea

Healthy code has layers: low-level modules (config, data loading) are imported by higher-level ones (models, training), never the other way round. An import cycle (`train.py` imports `models.py`, which imports `train.py`) breaks that. Python then loads one of the two half-finished, which causes confusing `ImportError`s or missing names that depend on which file runs first. It also means the two modules are really one, split across two files.

The fix is usually to move what both need into a third module both can import, or to pass the value in as an argument instead of importing it.

## Before and after

```python
# Before
# train.py
import models

DEVICE = "cuda"

# models.py
from train import DEVICE  # models now depends on the training script
```

```python
# After
# config.py
DEVICE = "cuda"

# models.py
from config import DEVICE

# train.py
import models
```

## Why engineers care

Cycles make code fragile: renaming or moving one function breaks the other module in surprising ways, and tests cannot import one part without dragging in everything. A clear dependency direction is what makes a codebase feel like it has an architecture.

## How Shipshape spots it

It resolves the project's own imports and finds groups of modules that import each other at module level, directly or around a longer loop, reporting the shortest cycle. Imports inside functions (deliberately lazy) and test files are ignored, as is a module importing its own package's `__init__`. Dynamic imports are invisible to it.

## Read more

- [Python FAQ: best practices for using import in a module](https://docs.python.org/3/faq/programming.html#what-are-the-best-practices-for-using-import-in-a-module)
