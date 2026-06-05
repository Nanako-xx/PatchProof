from count_parser import parse_count


def test_parse_count_returns_integer():
    assert parse_count("3") == 3
