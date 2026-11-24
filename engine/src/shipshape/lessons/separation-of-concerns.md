---
concept: Separation of concerns
summary: A file that loads data, trains, plots and reports does four jobs; split it so each part can be read, tested and reused alone.
---

## The idea

When a project grows from one notebook, everything tends to stay in one file: loading, preprocessing, the model, training, evaluation, plotting. At a few hundred lines that file is hard to navigate and impossible to reuse in parts: you cannot import the preprocessing without also importing the plotting and its dependencies. Separation of concerns means each module has one job and a clear interface, and the pieces are wired together in a short script.

A common research layout: `data.py` (loading), `features.py` (preprocessing), `models.py`, `train.py` (the experiment), `plots.py`.

## Before and after

```text
# Before
analysis.py        1,200 lines: load + filter + features + model + train + plot
```

```text
# After
data.py            load recordings
features.py        filtering and feature extraction
models.py          model definitions
train.py           the experiment: wires the pieces together
plots.py           figures for the paper
```

## Why engineers care

Small, focused modules are easier to review, test and change without fear. They make reuse possible (the same loader for three experiments) and make the structure of the work visible to someone reading it for the first time.

## How Shipshape spots it

It reports non-test Python files with 400 or more lines of code (major from 700), with how many top-level definitions and imported packages they contain. Line count is a proxy: a long file of simple constants is less of a problem than the number suggests. The architecture map shows how files depend on each other.

## Read more

- [The Hitchhiker's Guide to Python: structuring your project](https://docs.python-guide.org/writing/structure/)
