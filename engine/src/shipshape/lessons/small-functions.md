---
concept: Keeping functions small
summary: A function with many branches has many paths to test and understand; split it into smaller steps or replace branch chains with a lookup.
---

## The idea

Cyclomatic complexity counts the independent paths through a function: every `if`, `elif`, loop, `and`/`or` and `except` adds one. A function at 3 is easy to hold in your head; at 15 it has fifteen paths, and each needs its own test before you can trust it. Long `if/elif` chains on a mode string, nested loops with flags, and feature extractors that handle every option inline are the usual suspects.

Two refactors help most: extract each step into its own well-named function, and replace a chain of `elif mode == ...` with a dictionary that maps the option to the function that handles it.

## Before and after

```python
# Before
def feature(x, mode):
    if mode == "mav":
        return np.mean(np.abs(x))
    elif mode == "rms":
        return np.sqrt(np.mean(x**2))
    elif mode == "wl":
        return np.sum(np.abs(np.diff(x)))
    else:
        raise ValueError(mode)
```

```python
# After: one small function per feature, and a table to pick one
FEATURES = {
    "mav": lambda x: np.mean(np.abs(x)),
    "rms": lambda x: np.sqrt(np.mean(x**2)),
    "wl": lambda x: np.sum(np.abs(np.diff(x))),
}


def feature(x, mode):
    return FEATURES[mode](x)
```

## Why engineers care

Complex functions are where bugs hide and where changes break things. They are hard to review, hard to test and hard to reuse in part. Keeping functions small is the single habit that most improves code others can work with.

## How Shipshape spots it

It measures cyclomatic complexity with radon and reports every function at 15 or more (major if the worst reaches 25), as one finding listing them all. Test files are skipped. Complexity is a signal, not a verdict: a long but flat `match` statement can score high and still be readable.

## Read more

- [radon: cyclomatic complexity](https://radon.readthedocs.io/en/latest/intro.html#cyclomatic-complexity)
