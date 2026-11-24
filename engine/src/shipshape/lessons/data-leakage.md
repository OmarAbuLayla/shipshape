---
concept: Data leakage in evaluation
summary: If the same subject, patient or recording appears in both training and test data, the test score measures memory, not skill.
---

## The idea

A test set is supposed to answer one question: how well will the model do on data it has never seen? That only works if nothing about the test data reached training. In biosignal, medical and many research datasets, the samples are not independent. Ten thousand EMG windows may come from only twenty people, and two windows from the same person share their muscles, their electrode placement and their noise. If you split windows at random, almost every test subject also appears in training, and the model can recognise the *person* instead of learning the *gesture*.

The fix is to split by the thing that makes samples related: subject, patient, session, paper, user. Everything from one group goes to the same side.

## Before and after

```python
# Before: windows from the same subject land on both sides
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)
```

```python
# After: every subject is entirely in training or entirely in test
from sklearn.model_selection import GroupShuffleSplit

splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
train_idx, test_idx = next(splitter.split(X, y, groups=subjects))
X_train, X_test = X[train_idx], X[test_idx]
y_train, y_test = y[train_idx], y[test_idx]
```

## Why engineers care

Leakage produces results that look excellent and do not hold up: 95% accuracy in the paper, 60% on the next participant. It is one of the most common reasons machine-learning results fail to reproduce, and reviewers who know the field check for it first. A subject-wise split usually lowers the score. That lower number is the honest one.

## How Shipshape spots it

It looks for sample-wise splits (`train_test_split`, `KFold`, `ShuffleSplit`, or hand-made ones: `i % 5 == 4`, shuffled indices sliced into train and test, or `df.sample(frac=0.8)` with `df.drop(train.index)`), in scripts and notebooks, in files that also track groups (variables such as `subject`, `patient`, `participant`, `session`), with no group-aware splitter (`GroupKFold`, `GroupShuffleSplit`, `LeaveOneGroupOut`) in sight. Because it cannot know how your data was collected, it phrases this as a question. It misses leakage hidden in custom code, in preprocessing fitted on all data before the split (a scaler, a feature selector), and in how the data was recorded.

## Read more

- [scikit-learn: cross-validation for grouped data](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data)
- [scikit-learn: common pitfalls, including data leakage](https://scikit-learn.org/stable/common_pitfalls.html)
- [Kapoor & Narayanan: leakage and the reproducibility crisis in ML-based science](https://reproducible.cs.princeton.edu/)
