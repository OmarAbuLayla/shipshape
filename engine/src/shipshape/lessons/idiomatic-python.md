---
concept: Idiomatic Python
summary: Compare with None using `is`, and use truth values directly; == None and == True can surprise you and read as unfamiliar.
---

## The idea

`None`, `True` and `False` are single objects in Python, and the idiomatic way to test for `None` is `x is None`. `x == None` usually works, but asks the object to compare itself, which arrays and DataFrames answer element by element: `if arr == None:` raises an error or does something unexpected. For booleans, `if done:` says the same as `if done == True:` with less noise, and also works for values that are truthy without being exactly `True`.

## Before and after

```python
# Before
if result == None:
    result = compute()
if converged == True:
    stop()
```

```python
# After
if result is None:
    result = compute()
if converged:
    stop()
```

## Why engineers care

Idioms are how Python developers read code quickly. Unidiomatic comparisons are small, but they slow reviewers down and occasionally hide real bugs with NumPy and pandas objects.

## How Shipshape spots it

Through ruff's rules E711 (comparison to `None` with `==` or `!=`) and E712 (comparison to `True` or `False` with `==` or `!=`).

## Read more

- [PEP 8: programming recommendations](https://peps.python.org/pep-0008/#programming-recommendations)
- [Ruff rule: none-comparison (E711)](https://docs.astral.sh/ruff/rules/none-comparison/)
