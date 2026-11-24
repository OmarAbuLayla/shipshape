---
concept: Mutable default arguments
summary: A list or dict as a default argument is created once and shared by every call, so changes leak from one call into the next.
---

## The idea

Python evaluates default values once, when the function is defined, not on every call. For numbers and strings that does not matter. For a list, dict or set it does: every call that uses the default gets the *same* object, and if the function changes it, the change is still there next time. The classic symptom is a function that "remembers" items from earlier calls.

The fix is to default to `None` and create a fresh object inside.

## Before and after

```python
# Before: every call without `sessions` shares, and grows, the same list
def load_subject(subject_id, sessions=[]):
    sessions.append(subject_id)
    return sessions
```

```python
# After
def load_subject(subject_id, sessions=None):
    sessions = [] if sessions is None else sessions
    sessions.append(subject_id)
    return sessions
```

## Why engineers care

It is a real bug, not a style issue, and one of the best-known Python traps: results depend on what ran before. Experienced reviewers spot it instantly.

## How Shipshape spots it

Through ruff's rule B006: a list, dict or set literal (or a call that creates one) used as a default argument. It flags the pattern whether or not the function actually modifies the default.

## Read more

- [Python FAQ: why are default values shared between objects?](https://docs.python.org/3/faq/programming.html#why-are-default-values-shared-between-objects)
- [Ruff rule: mutable-argument-default (B006)](https://docs.astral.sh/ruff/rules/mutable-argument-default/)
