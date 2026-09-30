import pytest

from price_comparator.comparison.validation import ValidationRules, sanitize_offer, validate_offer
from tests.factories import make_offer

RULES = ValidationRules()


def test_valid_offer_has_no_reason():
    assert validate_offer(make_offer(), RULES) == ""


@pytest.mark.parametrize("title", ["", "   "])
def test_empty_title_rejected(title):
    assert "nombre" in validate_offer(make_offer(title=title), RULES)


def test_long_title_rejected():
    assert "largo" in validate_offer(make_offer(title="x" * 301), RULES)


def test_control_chars_in_title_rejected():
    assert "control" in validate_offer(make_offer(title="Taladro\x00"), RULES)


@pytest.mark.parametrize("price", [None, 0, -10])
def test_missing_or_non_positive_price_rejected(price):
    assert "precio" in validate_offer(make_offer(price=price), RULES)


@pytest.mark.parametrize("price", [499, 50_000_001])
def test_price_outside_realistic_range_rejected(price):
    assert "rango" in validate_offer(make_offer(price=price), RULES)


def test_price_range_is_configurable():
    rules = ValidationRules(min_price=1, max_price=100)
    assert validate_offer(make_offer(price=50), rules) == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://www.sodimac.cl/p/1",
        "https://evil.example.com/p/1",
        "https://user:pass@www.sodimac.cl/p/1",  # pragma: allowlist secret
        "https://www.sodimac.cl.evil.com/p/1",
        "",
        "https://www.sodimac.cl/" + "a" * 2100,
        "javascript:alert(1)",
        "https://www.sodimac.cl/p",
        "https://www.sodimac.cl/con espacio",
    ],
)
def test_bad_urls_rejected(url):
    assert "url" in validate_offer(make_offer(url=url), RULES)


def test_url_must_match_the_offers_own_store():
    offer = make_offer(store="Sodimac", url="https://www.falabella.com/p/1")
    assert "url" in validate_offer(offer, RULES)


def test_subdomains_of_allowed_hosts_are_accepted():
    assert validate_offer(make_offer(url="https://media.sodimac.cl/p/1"), RULES) == ""


def test_sanitize_drops_list_price_lower_than_price():
    offer = make_offer(price=100_000, list_price_clp=80_000, card_price_clp=90_000)
    clean = sanitize_offer(offer)
    assert clean.list_price_clp is None
    assert clean.card_price_clp == 90_000


def test_sanitize_drops_non_positive_secondary_prices():
    clean = sanitize_offer(make_offer(price=100_000, list_price_clp=0, card_price_clp=-5))
    assert clean.list_price_clp is None
    assert clean.card_price_clp is None


def test_sanitize_repairs_mojibake_in_title_and_brand():
    offer = make_offer(title="Caja Cosm\u00c3\u00a9tica", brand="Ni\u00c3\u00b1o")
    clean = sanitize_offer(offer)
    assert clean.title == "Caja Cosm\u00e9tica"
    assert clean.brand == "Ni\u00f1o"


def test_sanitize_bounds_every_text_field_so_scoring_cannot_be_starved():
    """Un título de megabytes haría inmanejable el puntaje (fuzzy O(n·m)) antes de validarlo."""
    huge = "x" * 1_000_000
    clean = sanitize_offer(make_offer(title=huge, brand=huge, model=huge, seller=huge))
    assert len(clean.title) <= 301
    assert max(len(clean.brand), len(clean.model), len(clean.seller)) <= 100
    assert "largo" in validate_offer(clean, RULES)  # sigue marcándose como demasiado largo
