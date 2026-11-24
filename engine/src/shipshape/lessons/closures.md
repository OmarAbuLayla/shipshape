---
concept: Closures and late binding
summary: A function defined in a loop sees the loop variable's final value, not the value it had when the function was created.
---

## The idea

When a function (or lambda) uses a variable from the surrounding code, it looks the variable up when it *runs*, not when it is defined. Inside a loop that means every function created in the loop ends up seeing the last value of the loop variable. Callbacks, lists of lambdas and functions submitted to a thread pool are where this bites.

The fix is to bind the current value explicitly, as a default argument or with `functools.partial`.

## Before and after

```python
# Before: all three callbacks print "fold 2"
callbacks = []
for fold in range(3):
    callbacks.append(lambda: print("fold", fold))
```

```python
# After: each callback keeps its own value
import functools

callbacks = []
for fold in range(3):
    callbacks.append(functools.partial(print, "fold", fold))
```

## Why engineers care

The code looks correct and runs without errors, but does the same thing three times. These bugs are hard to spot by reading and easy to prevent once you know the rule.

## How Shipshape spots it

Through ruff's rule B023: a function or lambda defined inside a loop that uses the loop variable without binding it.

## Read more

- [Python FAQ: lambdas defined in a loop all return the same result](https://docs.python.org/3/faq/programming.html#why-do-lambdas-defined-in-a-loop-with-different-values-all-return-the-same-result)
- [Ruff rule: function-uses-loop-variable (B023)](https://docs.astral.sh/ruff/rules/function-uses-loop-variable/)
