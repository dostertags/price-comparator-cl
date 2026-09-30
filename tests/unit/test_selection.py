from price_comparator.comparison.selection import SelectionConfig, select_best
from price_comparator.models import PriceKind
from tests.factories import make_offer, scored

CFG = SelectionConfig(min_score=0.60)


def _prices(items):
    return [(o.offer.store, o.offer.price_clp) for o in items]


def test_cheapest_confident_offer_wins():
    offers = [
        scored(make_offer("Sodimac", price=80_000), 0.9),
        scored(make_offer("Falabella", price=60_000), 0.88),
        scored(make_offer("Hites", price=70_000), 0.92),
    ]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Falabella"
    assert sel.best_match.offer.store == "Hites"


def test_cheap_but_wrong_product_does_not_win():
    offers = [
        scored(make_offer("Sodimac", "Broca accesorio", price=3_000), 0.30),
        scored(make_offer("Falabella", price=60_000), 0.9),
    ]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Falabella"
    low = next(o for o in sel.annotated if o.offer.price_clp == 3_000)
    assert "coincidencia" in low.discard_reason


def test_tie_on_price_goes_to_higher_score():
    offers = [
        scored(make_offer("Sodimac", price=50_000), 0.85),
        scored(make_offer("Hites", price=50_000), 0.9),
    ]
    assert select_best(offers, CFG).best_price.offer.store == "Hites"


def test_full_tie_uses_fixed_store_order():
    offers = [
        scored(make_offer("Hites", price=50_000), 0.9),
        scored(make_offer("Sodimac", price=50_000), 0.9),
    ]
    assert select_best(offers, CFG).best_price.offer.store == "Sodimac"


def test_from_price_does_not_beat_exact_price():
    offers = [
        scored(make_offer("Sodimac", price=10_000, kind=PriceKind.FROM), 0.9),
        scored(make_offer("Falabella", price=60_000), 0.9),
    ]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Falabella"


def test_from_price_wins_only_when_it_is_the_only_option_and_is_noted():
    offers = [scored(make_offer("Sodimac", price=10_000, kind=PriceKind.FROM), 0.9)]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Sodimac"
    assert any("desde" in n for n in sel.notes)


def test_out_of_stock_is_excluded_by_default():
    offers = [
        scored(make_offer("Sodimac", price=40_000, in_stock=False), 0.9),
        scored(make_offer("Falabella", price=60_000, in_stock=True), 0.9),
    ]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Falabella"
    assert any("stock" in o.discard_reason for o in sel.annotated)


def test_out_of_stock_can_be_included():
    offers = [scored(make_offer("Sodimac", price=40_000, in_stock=False), 0.9)]
    cfg = SelectionConfig(min_score=0.60, include_out_of_stock=True)
    assert select_best(offers, cfg).best_price.offer.price_clp == 40_000


def test_unknown_stock_counts_as_available_and_is_noted():
    offers = [scored(make_offer("Sodimac", price=40_000, in_stock=None), 0.9)]
    sel = select_best(offers, CFG)
    assert sel.best_price is not None
    assert any("stock no verificado" in n for n in sel.notes)


def test_price_outlier_needs_high_score_to_win():
    offers = [
        scored(make_offer("Sodimac", "Accesorio", price=990), 0.65),
        scored(make_offer("Falabella", price=99_990), 0.9),
        scored(make_offer("Hites", price=104_990), 0.9),
    ]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Falabella"
    assert any("posible error" in o.discard_reason for o in sel.annotated)


def test_outlier_with_high_score_may_win():
    offers = [
        scored(make_offer("Sodimac", price=9_990), 0.95),
        scored(make_offer("Falabella", price=99_990), 0.9),
        scored(make_offer("Hites", price=104_990), 0.9),
    ]
    assert select_best(offers, CFG).best_price.offer.store == "Sodimac"


def test_below_threshold_only_yields_best_match_without_best_price():
    offers = [scored(make_offer("Sodimac", price=40_000), 0.45)]
    sel = select_best(offers, CFG)
    assert sel.best_price is None
    assert sel.best_match is not None


def test_invalid_offers_are_ignored_but_kept_in_annotated():
    offers = [
        scored(make_offer("Sodimac", price=None), 0.99, reason="sin precio"),
        scored(make_offer("Falabella", price=60_000), 0.8),
    ]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Falabella"
    assert len(sel.annotated) == 2


def test_no_offers_returns_empty_selection():
    sel = select_best([], CFG)
    assert sel.best_price is None
    assert sel.best_match is None
    assert sel.annotated == []


def test_a_much_better_match_beats_a_cheaper_worse_one():
    """Regresión real: «Zapatilla Adidas Ultraboost» elegía una Hoops más barata."""
    offers = [
        scored(make_offer("Falabella", "Zapatillas Ultraboost 5", 111_990), 0.97),
        scored(make_offer("Hites", "Zapatilla Adidas Hoops", 43_990), 0.72),
    ]
    sel = select_best(offers, CFG)
    assert sel.best_price.offer.store == "Falabella"
    worse = next(o for o in sel.annotated if o.offer.store == "Hites")
    assert "inferior" in worse.discard_reason
    assert sel.best_match.offer.store == "Falabella"


def test_offers_within_the_band_still_compete_on_price():
    offers = [
        scored(make_offer("Falabella", price=111_990), 0.97),
        scored(make_offer("Hites", price=43_990), 0.90),
    ]
    assert select_best(offers, CFG).best_price.offer.store == "Hites"


def test_the_band_is_configurable():
    offers = [
        scored(make_offer("Falabella", price=111_990), 0.97),
        scored(make_offer("Hites", price=43_990), 0.72),
    ]
    wide = SelectionConfig(min_score=0.60, band=0.5)
    assert select_best(offers, wide).best_price.offer.store == "Hites"


def test_band_is_measured_against_the_best_available_offer_not_an_out_of_stock_one():
    offers = [
        scored(make_offer("Falabella", price=111_990, in_stock=False), 0.99),
        scored(make_offer("Hites", price=43_990, in_stock=True), 0.75),
    ]
    assert select_best(offers, CFG).best_price.offer.store == "Hites"
