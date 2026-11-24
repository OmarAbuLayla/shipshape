"""Subject-aware train/test splitting."""

from __future__ import annotations

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

SEED = 42


def split_by_subject(
    windows: np.ndarray, labels: np.ndarray, subjects: np.ndarray, test_size: float = 0.2
) -> tuple[np.ndarray, np.ndarray]:
    """Return train and test indices with every subject on exactly one side."""
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=SEED)
    train_idx, test_idx = next(splitter.split(windows, labels, groups=subjects))
    return train_idx, test_idx
