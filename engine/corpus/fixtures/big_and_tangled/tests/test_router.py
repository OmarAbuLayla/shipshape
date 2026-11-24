from router import route


def test_unknown_command() -> None:
    assert route("nope") == 0
