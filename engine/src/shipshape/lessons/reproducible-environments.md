---
concept: Reproducible environments
summary: List the packages your project needs, with versions, so the code runs the same way on another machine and next year.
---

## The idea

Your code is only half of what runs: the other half is NumPy, PyTorch, scikit-learn and their exact versions. A project without a list of dependencies forces everyone to guess what to install, and a list without versions ("numpy", "torch") installs whatever is newest today, which may behave differently from what you used. Pinned versions (`numpy==1.26.4`) or a lock file make the environment rebuildable.

Pick one place: `requirements.txt`, `environment.yml` for conda, or `pyproject.toml` for a package. Pin exact versions for experiments you want to reproduce; ranges are fine for libraries other people install.

## Before and after

```text
# Before: requirements.txt
numpy
pandas
torch>=2.0
```

```text
# After: requirements.txt
numpy==1.26.4
pandas==2.2.2
torch==2.3.1
```

## Why engineers care

"Works on my machine" usually means "works with my versions". Default behaviours change between releases (a metric's averaging, a random generator, a deprecated argument), so the same code can quietly produce different numbers. A pinned environment is also the first thing anyone asks for when they try to run your work.

## How Shipshape spots it

It reports a project that imports third-party packages but has no `requirements*.txt`, `environment.yml`, `pyproject.toml`, `Pipfile` or similar. When a requirements file exists, it reports entries without an exact version. It reads these files without installing anything, so it cannot tell whether the versions actually work together.

## Read more

- [pip: requirements files](https://pip.pypa.io/en/stable/user_guide/#requirements-files)
- [conda: managing environments](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html)
