---
concept: Version control instead of copies
summary: Folders like old/ and project_v2/ are version control by hand; git keeps one copy and every version you ever had.
---

## The idea

Copying a package to `old/preprocessing/` or `pipeline_backup/` before changing it feels safe, but the copies drift apart: a bug fixed in one stays in the other, a sampling rate changes in only one place, and after a few weeks nobody knows which copy the results came from. Git solves this properly: one copy of the code, every earlier version one command away, and branches for experiments you are not sure about yet.

Delete the copies, commit the current version, and use a branch (`git switch -c new-filter`) for the next experiment.

## Before and after

```text
# Before
preprocessing/filters.py        fs=2000
old/preprocessing/filters.py    fs=1000   <- which one did the paper use?
```

```text
# After
preprocessing/filters.py        one copy, history in git
$ git log -- preprocessing/filters.py
$ git switch -c try-notch-filter
```

## Why engineers care

Duplicated code doubles maintenance and hides which version produced which result. A clean history is also how you show your work: what changed, when and why.

## How Shipshape spots it

It compares packages (folders with an `__init__.py`): same-named ones by their file lists, renamed ones (`data` and `data_old`) by content, and reports pairs where 60% or more of the files match. Single files are compared too (`structure.copied-files`): files of 10+ lines whose code lines match 85% or more, such as one `lr_scheduler.py` per experiment folder or `train_2.py` next to `train.py`. Copies that were changed more than that are not caught.

## Read more

- [Software Carpentry: version control with git](https://swcarpentry.github.io/git-novice/)
