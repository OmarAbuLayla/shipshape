---
concept: Explicit imports
summary: from module import * hides where names come from and can silently overwrite your own; import the names you use.
---

## The idea

`from utils import *` pulls every public name from `utils` into your module. The reader can no longer tell where `load` or `config` comes from, tools cannot check whether names exist, and if two star imports define the same name, the later one silently wins. Explicit imports (`from utils import load_subject, bandpass`) or a module alias (`import utils`) keep every name traceable.

## Before and after

```python
# Before
from utils import *
from features import *
```

```python
# After
from features import extract
from utils import bandpass, load_subject
```

## Why engineers care

Readable code answers "where does this come from?" without searching. Star imports also make refactoring risky, because removing a name from one module can break another without any error until runtime.

## How Shipshape spots it

Through ruff's rule F403: any `from ... import *` statement.

## Read more

- [PEP 8: imports](https://peps.python.org/pep-0008/#imports)
- [Ruff rule: undefined-local-with-import-star (F403)](https://docs.astral.sh/ruff/rules/undefined-local-with-import-star/)
