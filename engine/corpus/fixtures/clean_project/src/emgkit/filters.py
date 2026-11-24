"""Signal filters for surface EMG."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def bandpass(signal: np.ndarray, fs: float, low: float = 20.0, high: float = 450.0) -> np.ndarray:
    """Zero-phase Butterworth bandpass along the last axis."""
    # 20-450 Hz keeps most sEMG power and drops motion artefacts below 20 Hz.
    sos = butter(4, [low, high], btype="band", fs=fs, output="sos")
    return sosfiltfilt(sos, signal, axis=-1)


def rms_envelope(signal: np.ndarray, window: int) -> np.ndarray:
    """Moving RMS envelope with a centred window of ``window`` samples."""
    kernel = np.ones(window) / window
    return np.sqrt(np.convolve(signal**2, kernel, mode="same"))
