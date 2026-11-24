import numpy as np
from sklearn.model_selection import train_test_split


def make_windows(recordings, size=400, step=200):
    windows, labels, subjects = [], [], []
    for rec in recordings:
        signal = rec["emg"]
        for start in range(0, len(signal) - size, step):
            windows.append(signal[start:start + size])
            labels.append(rec["word"])
            subjects.append(rec["subject_id"])
    return np.array(windows), np.array(labels), np.array(subjects)


def prepare_dataset(recordings):
    X, y, subjects = make_windows(recordings)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=True)
    return X_train, X_test, y_train, y_test
