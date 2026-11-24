import numpy as np

from emgkit.splits import split_by_subject


def test_no_subject_on_both_sides() -> None:
    subjects = np.repeat(np.arange(10), 5)
    windows = np.zeros((50, 8))
    train, test = split_by_subject(windows, np.zeros(50), subjects)
    assert not set(subjects[train]) & set(subjects[test])
