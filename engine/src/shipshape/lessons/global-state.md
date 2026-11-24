---
concept: Avoiding global state
summary: Functions that change global variables have hidden inputs and outputs; pass values in and return results instead.
---

## The idea

`global counter` lets a function change a variable defined outside it. That makes the function's behaviour depend on everything that ran before, and its effects invisible from its signature. Calling it twice, in a different order or from a test gives different results, and two parts of the program can silently overwrite each other's values.

Pass what a function needs as arguments, return what it produces, and keep shared state in an object you hand around explicitly.

## Before and after

```python
# Before
best_score = 0.0


def evaluate(model, data):
    global best_score
    score = model.score(*data)
    best_score = max(best_score, score)
```

```python
# After: inputs and outputs are visible
def evaluate(model, data, best_score: float) -> float:
    return max(best_score, model.score(*data))
```

## Why engineers care

Hidden state is the root of "it works when I run the cells in this order" problems, and it makes testing and parallel runs unreliable.

## How Shipshape spots it

Through ruff's rule PLW0603: any use of the `global` statement to rebind a module-level name inside a function. Changing a global list or dict in place (without `global`) is not caught.

## Read more

- [Python FAQ: rules for local and global variables](https://docs.python.org/3/faq/programming.html#what-are-the-rules-for-local-and-global-variables-in-python)
- [Ruff rule: global-statement (PLW0603)](https://docs.astral.sh/ruff/rules/global-statement/)
