---
concept: One name, one meaning
summary: Defining or importing the same name twice silently replaces the first one, so code may call a different function than you think.
---

## The idea

If a module defines `def preprocess(...)` near the top and again further down, or imports `load` and later defines its own `load`, Python keeps only the last one. Everything that uses the name gets the second version, with no warning. This usually happens when code is copied between notebooks or files, and it leads to confusing bugs where a fix to the first definition seems to have no effect.

## Before and after

```python
# Before
from utils import normalize


def normalize(x):  # replaces the imported one for the whole module
    return x / x.max()
```

```python
# After: two names for two different things
from utils import zscore


def scale_to_max(x):
    return x / x.max()
```

## Why engineers care

Duplicate names make it unclear which code actually runs. Editing the wrong copy is a classic way to lose an afternoon.

## How Shipshape spots it

Through ruff's rule F811: a name that is defined or imported again before the first definition was ever used.

## Read more

- [Ruff rule: redefined-while-unused (F811)](https://docs.astral.sh/ruff/rules/redefined-while-unused/)
