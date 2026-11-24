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

It compares packages (folders with an `__init__.py`) that share a name and reports pairs whose file lists overlap by 60% or more, with at least three files between them. It compares file names, not contents, so a renamed copy is not caught.

## Read more

- [Software Carpentry: version control with git](https://swcarpentry.github.io/git-novice/)
