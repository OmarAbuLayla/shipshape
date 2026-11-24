from monolith import feature_01


def test_feature_is_positive() -> None:
    assert feature_01([1.0, 2.0]) >= 0
