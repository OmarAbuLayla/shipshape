---
concept: Reproducible experiments
summary: Without a fixed random seed, every run gives different numbers, and nobody can tell an improvement from luck.
---

## The idea

Training a model involves randomness everywhere: the data split, shuffling, weight initialisation, dropout, augmentation. That is fine, as long as you control it. Setting a seed makes the random choices repeatable, so running the same code on the same data gives the same result. Then a change in the score means your change did something, not that the dice rolled differently.

Reproducible does not mean "one lucky seed". The honest way to report results is several seeds with the mean and spread. Seeds make each of those runs repeatable.

## Before and after

```python
# Before: a different split and different weights on every run
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
model = build_model()
```

```python
# After: one seed, set once, passed where it matters
import random

import numpy as np
import torch

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED)
model = build_model()
```

## Why engineers care

A result you cannot reproduce is a result you cannot debug, compare or defend. "It got 91% yesterday" is not useful if today's run gives 87% and you cannot tell why. Supervisors and reviewers increasingly ask for seeds and the variation across them.

## How Shipshape spots it

It looks for random calls (`random`, `np.random`), shuffling splits (`train_test_split`, every `*ShuffleSplit`, and `KFold` with `shuffle=True`) and layers whose weights are initialised randomly, and reports them when no seed is set anywhere in the project (`seed(...)`, `manual_seed`, `random_state=` and similar). It does not check that every source of randomness is covered, and GPU operations can stay slightly non-deterministic even with seeds.

## Read more

- [scikit-learn: controlling randomness](https://scikit-learn.org/stable/common_pitfalls.html#controlling-randomness)
- [PyTorch: reproducibility](https://pytorch.org/docs/stable/notes/randomness.html)
- [NumPy: random generators](https://numpy.org/doc/stable/reference/random/generator.html)
