---
concept: Small interfaces
summary: A function with many parameters is hard to call correctly; group related settings into a dataclass or config object.
---

## The idea

`extract(window, "td", True, False, 2000, "mean")`: which argument is which? Functions with more than five or six parameters are easy to call wrongly, especially when several are booleans or numbers of the same kind. They also tend to do too many things. Two remedies: group parameters that belong together (all feature settings, all training settings) into a dataclass, and split functions whose flags switch between different behaviours.

## Before and after

```python
# Before
def extract(window, feature_set="td", normalize=True, include_freq=False, fs=2000, mode="mean"): ...
```

```python
# After
from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureConfig:
    feature_set: str = "td"
    normalize: bool = True
    include_freq: bool = False
    fs: int = 2000
    mode: str = "mean"


def extract(window, config: FeatureConfig = FeatureConfig()): ...
```

## Why engineers care

Small interfaces are easier to use, document and test. A config object can also be saved next to each result, which is a big step towards reproducible experiments.

## How Shipshape spots it

Through ruff's rule PLR0913: functions with more than five parameters (`self` and `cls` are not counted).

## Read more

- [Python: dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Ruff rule: too-many-arguments (PLR0913)](https://docs.astral.sh/ruff/rules/too-many-arguments/)
