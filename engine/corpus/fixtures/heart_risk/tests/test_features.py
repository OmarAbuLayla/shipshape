import pandas as pd

from features import add_features


def test_pulse_pressure():
    df = pd.DataFrame({"sbp": [120], "dbp": [80], "chol": [200], "hdl": [50], "bmi": [24], "age": [50]})
    assert add_features(df)["pulse_pressure"][0] == 40
