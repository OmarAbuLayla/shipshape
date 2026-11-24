---
concept: Type hints as documentation
summary: Type hints say what goes in and out of a function; they document the code and let tools catch mistakes before running it.
---

## The idea

`def make_windows(recordings, size, step):` leaves the reader guessing: is `recordings` a list of arrays, a DataFrame, a path? What comes back? Type hints answer that in the signature itself, and unlike a comment they are checked: editors complete and warn based on them, and a type checker like mypy finds whole classes of bugs (a `None` where an array was expected, a string passed as a number) without running anything.

Python does not enforce hints at runtime, so you can add them gradually, starting with the public functions other code calls.

## Before and after

```python
# Before
def make_windows(recordings, size=400, step=200): ...
```

```python
# After
import numpy as np


def make_windows(
    recordings: list[dict[str, np.ndarray]], size: int = 400, step: int = 200
) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...
```

## Why engineers care

Hints make code faster to read, safer to change and easier to hand over. In teams they are often required, and they are a quick signal in a code sample that the author thinks about interfaces.

## How Shipshape spots it

It reports a project when at least half of its public functions (names not starting with `_`) have no annotations at all, listing them; projects with fewer than five public functions are left alone. It does not run a type checker, because that needs the project's dependencies installed, so it cannot tell whether existing hints are correct.

## Read more

- [Python: typing](https://docs.python.org/3/library/typing.html)
- [mypy: getting started](https://mypy.readthedocs.io/en/stable/getting_started.html)
