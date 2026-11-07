import pytest

from dcfmc.io.numbers import detect_locale, parse_number


@pytest.mark.parametrize("raw,locale,expected", [
    ("1,499.60", None, 1499.60),
    ("1.499,60 €", None, 1499.60),
    ("4,65%", None, 0.0465),
    ("4.235%", None, 0.04235),        # bug in v1: read as 0.4235
    ("0.125", None, 0.125),           # bug in v1: read as 125
    ("0,045", None, 0.045),           # bug in v1: read as 45
    ("179.138 m", "eu", 179138),
    ("1.105", "eu", 1105),
    ("1,105", "eu", 1.105),
    ("1.105", "us", 1.105),
    ("$40,31", "eu", 40.31),
    ("4444,00", None, 4444.0),
    ("(1,234.5)", None, -1234.5),
    ("-3,5%", None, -0.035),
    ("12 309", None, 12309),
    ("2.500 m", "eu", 2500),
    ("1,234,567", None, 1234567),
    (0.19, None, 0.19),
])
def test_parse(raw, locale, expected):
    p = parse_number(raw, locale=locale)
    assert p is not None
    assert p.value == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", "n/a", "#N/A", "abc", float("nan")])
def test_parse_none(raw):
    assert parse_number(raw) is None


def test_ambiguous_flagged_without_locale():
    p = parse_number("1.105")
    assert p.ambiguous


def test_scale_suffix():
    assert parse_number("1,2 bn", locale="eu").scale_to_millions == 1e3


def test_detect_locale():
    assert detect_locale(["4,86%", "179.138 m", "1.283,60 €"]) == "eu"
    assert detect_locale(["4.86%", "1,283.60", "$40.31"]) == "us"
