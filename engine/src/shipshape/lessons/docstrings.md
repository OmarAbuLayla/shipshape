---
concept: Documenting interfaces
summary: A short docstring on every public function says what it does and what it expects, so nobody has to read its body to use it.
---

## The idea

A docstring is the first string inside a function, class or module. It shows up in editors, in `help()` and in generated documentation. For anything other code calls, one or two sentences go a long way: what it does, what the arguments mean (units, shapes, allowed values) and what it returns or raises. The body says *how*; the docstring says *what for*, which is what a caller needs.

You do not need a docstring on every three-line helper. Larger and public functions are where the reader would otherwise have to reverse-engineer intent.

## Before and after

```python
# Before
def bandpass(emg, low=20, high=450):
    b, a = butter(4, [low / (FS / 2), high / (FS / 2)], btype="band")
    return filtfilt(b, a, emg, axis=0)
```

```python
# After
def bandpass(emg, low=20, high=450):
    """Zero-phase 4th-order Butterworth band-pass along time (axis 0).

    `emg` is samples x channels at FS Hz; `low` and `high` are cut-offs in Hz.
    """
    b, a = butter(4, [low / (FS / 2), high / (FS / 2)], btype="band")
    return filtfilt(b, a, emg, axis=0)
```

## Why engineers care

Undocumented interfaces slow everyone down and invite misuse: someone passes channels x samples, the filter runs along the wrong axis, nothing crashes. Docstrings are also what reviewers and future you read first.

## How Shipshape spots it

It reports a project when 60% or more of its public definitions with eight or more lines have no docstring (and there are at least five of them), listing them. Short helpers and private functions (names starting with `_`) are left alone. It does not judge the quality of existing docstrings.

## Read more

- [PEP 257: docstring conventions](https://peps.python.org/pep-0257/)
