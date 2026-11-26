"""Load per-subject EMG features."""

import os

import numpy as np
import torch
from torch.utils.data import TensorDataset

SUBJECTS = [f"s{i:02d}" for i in range(1, 21)]


def _load(root, subjects):
    xs, ys = [], []
    for subject in subjects:
        path = os.path.join(root, subject, "features.npz")
        if not os.path.exists(path):
            continue
        data = np.load(path)
        xs.append(data["x"])
        ys.append(data["y"])
    return TensorDataset(torch.tensor(np.concatenate(xs)), torch.tensor(np.concatenate(ys)))


def load_subjects(root):
    """Subject-wise split: 16 subjects for training, 4 for testing."""
    return _load(root, SUBJECTS[:16]), _load(root, SUBJECTS[16:])


def list_sessions(root):
    """Session folders of one subject; plain files in the folder are skipped on purpose."""
    sessions = []
    for name in sorted(os.listdir(root)):
        if not os.path.isdir(os.path.join(root, name)):
            continue
        sessions.append(name)
    return sessions
