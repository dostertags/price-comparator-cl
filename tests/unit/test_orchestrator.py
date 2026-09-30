import threading
import time

from price_comparator.comparison.selection import SelectionConfig
from price_comparator.models import ComparisonStatus, ScrapeResult, ScrapeStatus
from price_comparator.orchestrator import Comparator
from tests.factories import make_offer
from tests.fakes import FakeScraper, result

TALADRO = "Taladro percutor 750W"


def sodimac(price=80_000, title=TALADRO):
    return FakeScraper("Sodimac", result("Sodimac", make_offer("Sodimac", title, price)))


def falabella(price=60_000, title=TALADRO):
    return FakeScraper("Falabella", result("Falabella", make_offer("Falabella", title, price)))


def hites(price=70_000, title=TALADRO):
    return FakeScraper("Hites", result("Hites", make_offer("Hites", title, price)))


def failing(store, status):
    return FakeScraper(store, ScrapeResult(store, status, detail="x"))


def comparator(scrapers, **kw):
    kw.setdefault("cleaner", lambda _name: [])
    return Comparator(scrapers, **kw)


def test_cheapest_confident_offer_across_stores_wins():
    comp = comparator([sodimac(), falabella(), hites()]).compare_one(TALADRO)
    assert comp.status is ComparisonStatus.FOUND
    assert comp.best_price.offer.store == "Falabella"
    assert comp.best_price.offer.price_clp == 60_000
    assert set(comp.stores) == {"Sodimac", "Falabella", "Hites"}
    assert comp.stores["Sodimac"].best.offer.price_clp == 80_000


def test_one_failing_store_does_not_stop_the_others_and_is_noted():
    comp = comparator([sodimac(), failing("Falabella", ScrapeStatus.BLOCKED), hites()]).compare_one(
        TALADRO
    )
    assert comp.status is ComparisonStatus.FOUND
    assert comp.best_price.offer.store == "Hites"
    assert comp.stores["Falabella"].status is ScrapeStatus.BLOCKED
    assert any("Falabella" in n and "blocked" in n for n in comp.notes)


def test_a_scraper_that_raises_is_contained_as_error():
    boom = FakeScraper("Falabella", RuntimeError("bug"))
    comp = comparator([sodimac(), boom]).compare_one(TALADRO)
    assert comp.status is ComparisonStatus.FOUND
    assert comp.stores["Falabella"].status is ScrapeStatus.ERROR


def test_all_stores_down_is_no_data_and_skips_the_second_sweep():
    scrapers = [failing(s, ScrapeStatus.BLOCKED) for s in ("Sodimac", "Falabella", "Hites")]
    comp = comparator(scrapers, cleaner=lambda n: ["algo mas simple"]).compare_one(TALADRO)
    assert comp.status is ComparisonStatus.NO_DATA
    assert all(len(s.queries) == 1 for s in scrapers)


def test_all_stores_empty_is_no_results():
    scrapers = [
        FakeScraper(s, ScrapeResult(s, ScrapeStatus.EMPTY)) for s in ("Sodimac", "Falabella")
    ]
    assert comparator(scrapers).compare_one(TALADRO).status is ComparisonStatus.NO_RESULTS


def test_only_poor_matches_is_low_confidence_but_keeps_best_match():
    sc = [
        FakeScraper(
            "Sodimac", result("Sodimac", make_offer("Sodimac", "Cortina de baño azul", 9_990))
        )
    ]
    comp = comparator(sc).compare_one(TALADRO)
    assert comp.status is ComparisonStatus.LOW_CONFIDENCE
    assert comp.best_price is None
    assert comp.best_match is not None


def test_empty_name_is_no_name_and_never_searches():
    sc = sodimac()
    comp = comparator([sc]).compare_one("   ")
    assert comp.status is ComparisonStatus.NO_NAME
    assert sc.queries == []


def test_invalid_offers_are_discarded_with_reason_but_listed():
    bad = make_offer("Sodimac", TALADRO, 60_000, url="https://evil.example.com/x")
    sc = FakeScraper("Sodimac", result("Sodimac", bad))
    comp = comparator([sc]).compare_one(TALADRO)
    assert comp.best_price is None
    assert "url" in comp.offers[0].discard_reason


def test_brand_and_model_count_for_the_score():
    offer = make_offer(
        "Sodimac", "Taladro percutor eléctrico", 60_000, brand="Bosch", model="GSB 13 RE"
    )
    sc = FakeScraper("Sodimac", result("Sodimac", offer))
    comp = comparator([sc]).compare_one("Bosch GSB 13 RE taladro")
    assert comp.status is ComparisonStatus.FOUND


def test_second_sweep_recovers_with_a_simpler_query():
    def behaviour(query):
        if query == "taladro percutor":
            return result("Sodimac", make_offer("Sodimac", "Taladro percutor 13mm", 55_000))
        return ScrapeResult("Sodimac", ScrapeStatus.EMPTY)

    sc = FakeScraper("Sodimac", behaviour)
    comp = comparator([sc], cleaner=lambda n: ["sin utilidad", "taladro percutor"]).compare_one(
        "2 UN Taladro percutor 13mm (marca X) especial"
    )
    assert comp.status is ComparisonStatus.FOUND
    assert comp.query_used == "taladro percutor"
    assert any("simplificada" in n for n in comp.notes)


def test_second_sweep_is_capped_and_skipped_when_first_query_succeeds():
    sc = FakeScraper("Sodimac", ScrapeResult("Sodimac", ScrapeStatus.EMPTY))
    comparator([sc], cleaner=lambda n: ["a", "b", "c", "d", "e"], max_alt_queries=3).compare_one(
        TALADRO
    )
    assert len(sc.queries) == 1 + 3

    ok = sodimac()
    comparator([ok], cleaner=lambda n: ["a", "b"]).compare_one(TALADRO)
    assert len(ok.queries) == 1


def test_slow_scraper_times_out_without_blocking_the_others():
    release = threading.Event()

    def slow(_q):
        release.wait(2)
        return result("Hites", make_offer("Hites", TALADRO, 1_000))

    started = time.monotonic()
    comp = comparator([sodimac(), FakeScraper("Hites", slow)], scraper_budget_s=0.1).compare_one(
        TALADRO
    )
    release.set()
    assert time.monotonic() - started < 1.5
    assert comp.stores["Hites"].status is ScrapeStatus.TIMEOUT
    assert comp.status is ComparisonStatus.FOUND
    assert comp.best_price.offer.store == "Sodimac"


def test_run_dedupes_names_and_keeps_input_order():
    sc = sodimac()
    report = comparator([sc]).run([TALADRO, "  taladro   PERCUTOR 750w ", "", TALADRO])
    assert len(report.comparisons) == 4
    assert len(sc.queries) == 1
    assert report.comparisons[0] is report.comparisons[1] is report.comparisons[3]
    assert report.comparisons[2].status is ComparisonStatus.NO_NAME
    assert report.unique == 1


def test_run_reports_progress_once_per_unique_product():
    seen = []
    comparator([sodimac()], workers=2).run(
        [TALADRO, "Sierra circular 1200W"],
        on_progress=lambda done, total, c: seen.append((done, total)),
    )
    assert sorted(seen) == [(1, 2), (2, 2)]


def test_source_broken_when_every_searched_product_has_no_data():
    scrapers = [
        failing("Sodimac", ScrapeStatus.LAYOUT_CHANGED),
        failing("Hites", ScrapeStatus.BLOCKED),
    ]
    report = comparator(scrapers).run([TALADRO, "Sierra"])
    assert report.source_broken is True


def test_source_not_broken_when_something_worked():
    report = comparator([sodimac(), failing("Hites", ScrapeStatus.BLOCKED)]).run([TALADRO])
    assert report.source_broken is False


def test_interrupt_returns_partial_results_marked_interrupted():
    def interrupt(done, total, comp):
        raise KeyboardInterrupt

    report = comparator([sodimac()], workers=1).run(
        [TALADRO, "Sierra circular 1200W", "Martillo demoledor"], on_progress=interrupt
    )
    assert report.interrupted is True
    assert len(report.comparisons) == 3
    assert any(
        c.status is ComparisonStatus.NO_DATA and "interrump" in " ".join(c.notes)
        for c in report.comparisons
    )


def test_selection_config_is_applied():
    strict = SelectionConfig(min_score=0.99)
    comp = comparator([sodimac(title="Taladro percutor 800W")], selection=strict).compare_one(
        TALADRO
    )
    assert comp.best_price is None


def test_second_sweep_matches_are_scored_against_the_original_name_not_the_simple_query():
    """Regresión real: la consulta «Cosa» traía «Casa De Verano» y se marcaba Encontrado."""

    def behaviour(query):
        if query == "Cosa":
            return result("Sodimac", make_offer("Sodimac", "Casa De Verano Verde", 199_990))
        return ScrapeResult("Sodimac", ScrapeStatus.EMPTY)

    sc = FakeScraper("Sodimac", behaviour)
    comp = comparator([sc], cleaner=lambda n: ["Cosa"]).compare_one("Cosa inexistente zzqxkjwv")
    assert comp.status is not ComparisonStatus.FOUND
    assert comp.best_price is None


def test_second_sweep_scores_against_the_original_without_noise_so_real_recoveries_survive():
    """El ruido (cantidad, paréntesis) no debe hundir el puntaje de una recuperación legítima."""

    def behaviour(query):
        if query == "taladro percutor":
            return result("Sodimac", make_offer("Sodimac", "Taladro percutor 13mm", 55_000))
        return ScrapeResult("Sodimac", ScrapeStatus.EMPTY)

    sc = FakeScraper("Sodimac", behaviour)
    comp = comparator([sc], cleaner=lambda n: ["taladro percutor"]).compare_one(
        "2 UN Taladro percutor 13mm (marca X modelo ABC-123) especial"
    )
    assert comp.status is ComparisonStatus.FOUND
