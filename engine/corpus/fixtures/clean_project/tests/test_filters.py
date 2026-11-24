import numpy as np

from emgkit.filters import rms_envelope


def test_envelope_of_constant_signal() -> None:
    envelope = rms_envelope(np.ones(100), window=5)
    assert np.allclose(envelope[10:90], 1.0)
