import pytest

from price_comparator.comparison.pricing import parse_price
from price_comparator.comparison.text import normalize_name, strip_accents


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1.299.990", 1_299_990),
        ("12.990", 12_990),
        ("$ 9.990 ", 9_990),
        ("1299990.0", 1_299_990),
        ("149.990", 149_990),
        ("1.299.990,00", 1_299_990),
        (41990, 41_990),
        (41990.0, 41_990),
        (["149.990"], 149_990),
        ("59.990 c/u", 59_990),
    ],
)
def test_parse_price_valid(raw, expected):
    assert parse_price(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "  ", "Agotado", "0", 0, -5, "-1.000", [], True])
def test_parse_price_invalid_returns_none(raw):
    assert parse_price(raw) is None


def test_normalize_name_collapses_whitespace_and_control_chars():
    assert normalize_name("  Taladro \n\t percutor\x00  750W ") == "Taladro percutor 750W"


def test_normalize_name_truncates_to_limit():
    assert len(normalize_name("a" * 500, max_len=200)) == 200


def test_normalize_name_handles_non_strings():
    assert normalize_name(1234) == "1234"
    assert normalize_name(None) == ""


def test_strip_accents():
    assert strip_accents("Batería eléctrica ñandú") == "Bateria electrica nandu"


def test_fix_mojibake_repairs_utf8_read_as_latin1():
    from price_comparator.comparison.text import fix_mojibake

    assert fix_mojibake("Caja Cosm\u00c3\u00a9tica") == "Caja Cosm\u00e9tica"
    assert fix_mojibake("Ni\u00c3\u00b1o") == "Ni\u00f1o"


def test_fix_mojibake_leaves_healthy_text_alone():
    from price_comparator.comparison.text import fix_mojibake

    assert fix_mojibake("Taladro eléctrico ñandú") == "Taladro eléctrico ñandú"
    assert fix_mojibake("PRO Ã?") == "PRO Ã?"  # no se puede revertir: se deja tal cual


@pytest.mark.parametrize(
    "raw",
    ["9" * 5000, "9" * 16, float("inf"), float("-inf"), float("nan"), 1e30, 10**16, "1e999"],
)
def test_hostile_or_absurd_prices_are_none_not_a_crash(raw):
    """Un solo precio raro no debe tumbar el parseo de toda la página (inf, miles de dígitos)."""
    assert parse_price(raw) is None


def test_the_largest_accepted_price_is_15_digits():
    assert parse_price("999.999.999.999.999") == 999_999_999_999_999
