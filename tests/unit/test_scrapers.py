import json

import pytest

from price_comparator.models import PriceKind, ScrapeStatus
from price_comparator.scrapers.base import Scraper
from price_comparator.scrapers.falabella import FalabellaScraper
from price_comparator.scrapers.fetch import FetchError, FetchResponse
from price_comparator.scrapers.hites import HitesScraper
from price_comparator.scrapers.prices import choose_prices
from price_comparator.scrapers.sodimac import SodimacScraper
from tests.fakes import FakeFetcher, ok

# ---------------------------------------------------------------- choose_prices


def test_choose_prices_splits_public_list_and_card():
    entries = [
        ("cmrPrice", 169_990, False),
        ("eventPrice", 184_990, False),
        ("normalPrice", 299_990, True),
    ]
    assert choose_prices(entries) == (184_990, 299_990, 169_990)


def test_choose_prices_takes_lowest_public_price():
    entries = [("internetPrice", 149_990, False), ("normalPrice", 189_990, False)]
    assert choose_prices(entries)[0] == 149_990


def test_choose_prices_combo_is_list_price_not_public():
    assert choose_prices([("NORMAL", 259_890, False), ("COMBO", 293_966, False)]) == (
        259_890,
        293_966,
        None,
    )


def test_choose_prices_ignores_unknown_kinds_and_returns_none_when_no_public():
    assert choose_prices([("mystery", 1_000, False)]) == (None, None, None)


# ------------------------------------------------------------------ Scraper base


def test_search_builds_request_with_query_as_param():
    fetcher = FakeFetcher({"sodimac.cl": ok("<html></html>")})
    SodimacScraper(fetcher).search("taladro & sierra")
    url, params = fetcher.calls[0]
    assert url == "https://www.sodimac.cl/sodimac-cl/search"
    assert params == {"Ntt": "taladro & sierra"}


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ScrapeStatus.BLOCKED, ScrapeStatus.BLOCKED),
        (ScrapeStatus.TIMEOUT, ScrapeStatus.TIMEOUT),
        (ScrapeStatus.ERROR, ScrapeStatus.ERROR),
    ],
)
def test_fetch_errors_map_to_status_without_raising(kind, expected):
    fetcher = FakeFetcher({"sodimac.cl": FetchError(kind, "detalle")})
    res = SodimacScraper(fetcher).search("x")
    assert res.status is expected
    assert res.offers == []
    assert res.detail == "detalle"


def test_http_404_is_empty():
    fetcher = FakeFetcher({"sodimac.cl": FetchResponse(404, "", "https://www.sodimac.cl/")})
    assert SodimacScraper(fetcher).search("x").status is ScrapeStatus.EMPTY


def test_other_http_status_is_error():
    fetcher = FakeFetcher({"sodimac.cl": FetchResponse(418, "", "https://www.sodimac.cl/")})
    assert SodimacScraper(fetcher).search("x").status is ScrapeStatus.ERROR


def test_offers_are_capped_at_max_offers(fx):
    fetcher = FakeFetcher({"sodimac.cl": ok(fx("sodimac_results.html"))})
    res = SodimacScraper(fetcher, max_offers=2).search("taladro")
    assert len(res.offers) == 2


def test_parser_bug_is_contained_as_error_status():
    class Broken(SodimacScraper):
        def parse(self, text, final_url):
            raise ValueError("boom")

    fetcher = FakeFetcher({"sodimac.cl": ok("<html></html>")})
    res = Broken(fetcher).search("x")
    assert res.status is ScrapeStatus.ERROR
    assert "boom" in res.detail


def test_elapsed_is_measured_with_injected_clock(fx):
    ticks = iter([10.0, 12.5])
    fetcher = FakeFetcher({"sodimac.cl": ok(fx("sodimac_results.html"))})
    res = SodimacScraper(fetcher, clock=lambda: next(ticks)).search("taladro")
    assert res.elapsed_s == pytest.approx(2.5)


def test_scraper_is_a_context_manager_and_closes_fetcher():
    fetcher = FakeFetcher()
    with SodimacScraper(fetcher) as sc:
        assert isinstance(sc, Scraper)
    assert fetcher.closed


# --------------------------------------------------------------------- Sodimac


def test_sodimac_parses_results(fx):
    out = SodimacScraper(FakeFetcher()).parse(fx("sodimac_results.html"), "")
    assert out.status is ScrapeStatus.OK
    assert len(out.offers) == 5
    first = out.offers[0]
    assert first.store == "Sodimac"
    assert first.title == "Taladro percutor eléctrico 13 mm 750W"
    assert first.brand == "Bosch"
    assert first.model == "GSB 13 RE"
    assert first.price_clp == 79_990
    assert first.price_kind is PriceKind.EXACT
    assert first.url == "https://www.sodimac.cl/sodimac-cl/search?Ntt=7404727"


def test_sodimac_combo_uses_normal_price_and_keeps_combo_as_list(fx):
    offers = SodimacScraper(FakeFetcher()).parse(fx("sodimac_results.html"), "").offers
    combo = next(o for o in offers if o.title.startswith("Combo"))
    assert combo.price_clp == 259_890
    assert combo.list_price_clp == 293_966


def test_sodimac_redirect_to_home_means_empty(fx):
    assert (
        SodimacScraper(FakeFetcher()).parse(fx("sodimac_empty.html"), "").status
        is ScrapeStatus.EMPTY
    )


def test_sodimac_search_page_without_results_is_layout_changed(fx):
    out = SodimacScraper(FakeFetcher()).parse(fx("sodimac_layout_changed.html"), "")
    assert out.status is ScrapeStatus.LAYOUT_CHANGED


def test_sodimac_page_without_next_data_is_layout_changed():
    out = SodimacScraper(FakeFetcher()).parse("<html><body>hola</body></html>", "")
    assert out.status is ScrapeStatus.LAYOUT_CHANGED


def test_sodimac_drops_cards_without_title_or_price():
    def page(results):
        data = {
            "page": "/search",
            "props": {"pageProps": {"searchProps": {"searchData": {"results": results}}}},
        }
        return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'

    good = {
        "productId": "1",
        "displayName": "Sierra",
        "prices": [{"type": "NORMAL", "priceWithoutFormatting": 9990}],
    }
    no_price = {"productId": "2", "displayName": "Martillo", "prices": []}
    no_title = {
        "productId": "3",
        "displayName": "",
        "prices": [{"type": "NORMAL", "priceWithoutFormatting": 5000}],
    }
    out = SodimacScraper(FakeFetcher()).parse(page([good, no_price, no_title]), "")
    assert [o.title for o in out.offers] == ["Sierra"]
    assert out.dropped == 2


# -------------------------------------------------------------------- Falabella


def test_falabella_parses_and_dedupes_sponsored_duplicates(fx):
    out = FalabellaScraper(FakeFetcher()).parse(fx("falabella_results.html"), "")
    assert out.status is ScrapeStatus.OK
    assert len(out.offers) == 3
    assert len({o.url for o in out.offers}) == 3


def test_falabella_prices_and_urls(fx):
    offers = FalabellaScraper(FakeFetcher()).parse(fx("falabella_results.html"), "").offers
    kit = next(o for o in offers if "CLX2" in o.title)
    assert kit.price_clp == 184_990
    assert kit.list_price_clp == 299_990
    assert kit.card_price_clp == 169_990
    assert kit.url.startswith("https://www.falabella.com/falabella-cl/product/")
    first = offers[0]
    assert first.price_clp == 149_990


def test_falabella_flags_marketplace_sellers(fx):
    offers = FalabellaScraper(FakeFetcher()).parse(fx("falabella_results.html"), "").offers
    by_seller = {o.seller: o.is_marketplace for o in offers}
    assert by_seller["Sodimac"] is False
    assert by_seller["Lernen"] is True


def test_falabella_empty_and_layout_changed(fx):
    sc = FalabellaScraper(FakeFetcher())
    assert sc.parse(fx("falabella_empty.html"), "").status is ScrapeStatus.EMPTY
    assert sc.parse(fx("falabella_layout_changed.html"), "").status is ScrapeStatus.LAYOUT_CHANGED


# ------------------------------------------------------------------------ Hites


def test_hites_parses_json_ld(fx):
    out = HitesScraper(FakeFetcher()).parse(fx("hites_results.html"), "")
    assert out.status is ScrapeStatus.OK
    assert len(out.offers) == 5
    first = out.offers[0]
    assert first.store == "Hites"
    assert first.price_clp == 41_990
    assert first.brand == "FLOWMAK"
    assert first.title == "Taladro Percutor Atornillador 13mm Sin Batería Flowmak"
    assert first.url.startswith("https://www.hites.com/taladro-percutor-atornillador-13mm")


def test_hites_hidden_out_of_stock_badge_does_not_mark_everything_out_of_stock(fx):
    """Regresión real: la insignia «SIN STOCK» existe en TODAS las tarjetas dentro de `d-none`."""
    offers = HitesScraper(FakeFetcher()).parse(fx("hites_results.html"), "").offers
    assert all(o.in_stock is True for o in offers)


def test_hites_visible_out_of_stock_badge_marks_out_of_stock(fx):
    html = fx("hites_results.html").replace("oos-tags d-none", "oos-tags", 1)
    offers = HitesScraper(FakeFetcher()).parse(html, "").offers
    assert offers[0].in_stock is False
    assert all(o.in_stock is True for o in offers[1:])


def test_hites_json_ld_out_of_stock(fx):
    html = fx("hites_results.html").replace(
        "http://schema.org/InStock", "http://schema.org/OutOfStock", 1
    )
    assert HitesScraper(FakeFetcher()).parse(html, "").offers[0].in_stock is False


def test_hites_aggregate_offer_is_a_from_price():
    item = {
        "@type": "ListItem",
        "item": {
            "@type": "Product",
            "name": "Taladro",
            "url": "https://www.hites.com/taladro.html",
            "offers": {"@type": "AggregateOffer", "lowPrice": 19990, "highPrice": 49990},
        },
    }
    ld = {"@type": "ItemList", "itemListElement": [item]}
    html = f'<script type="application/ld+json">{json.dumps(ld)}</script>'
    offer = HitesScraper(FakeFetcher()).parse(html, "").offers[0]
    assert offer.price_clp == 19_990
    assert offer.price_kind is PriceKind.FROM


def test_hites_ignores_broken_json_ld_blocks(fx):
    html = '<script type="application/ld+json">{no es json</script>' + fx("hites_results.html")
    assert len(HitesScraper(FakeFetcher()).parse(html, "").offers) == 5


def test_hites_empty_and_layout_changed(fx):
    sc = HitesScraper(FakeFetcher())
    assert sc.parse(fx("hites_empty.html"), "").status is ScrapeStatus.EMPTY
    assert sc.parse(fx("hites_layout_changed.html"), "").status is ScrapeStatus.LAYOUT_CHANGED


# --- Falabella redirige a la ficha del producto cuando la búsqueda tiene un único resultado ----

PDP_URL = "https://www.falabella.com/falabella-cl/product/155453372/botas-militares/1"


def test_falabella_single_result_redirect_is_parsed_from_the_product_page(fx):
    """Regresión real: «Botas de trabajo cuero» devolvía layout_changed y se perdía la oferta."""
    out = FalabellaScraper(FakeFetcher()).parse(fx("falabella_product_page.html"), PDP_URL)
    assert out.status is ScrapeStatus.OK
    (offer,) = out.offers
    assert offer.title == "Botas Trabajo Unisex Adulto Cuero Comandos Tacticos"
    assert offer.brand == "COMANDOS TACTICOS"
    assert offer.price_clp == 57_990
    assert offer.list_price_clp == 69_990
    assert offer.url == PDP_URL


def test_falabella_product_page_without_prices_is_layout_changed():
    data = {
        "page": "/product",
        "props": {"pageProps": {"productData": {"name": "X", "variants": []}}},
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    out = FalabellaScraper(FakeFetcher()).parse(html, PDP_URL)
    assert out.status is ScrapeStatus.LAYOUT_CHANGED


# --- Una página desconocida se reintenta una vez y deja un diagnóstico útil -------------------


def test_unrecognized_page_is_retried_once_and_can_recover(fx):
    """Regresión real: una página rara transitoria se reportaba como «cambió el sitio»."""
    fetcher = FakeFetcher(
        {"sodimac.cl": [ok("<html>interstitial</html>"), ok(fx("sodimac_results.html"))]}
    )
    res = SodimacScraper(fetcher).search("taladro")
    assert res.status is ScrapeStatus.OK
    assert len(fetcher.calls) == 2


def test_persistent_layout_change_is_retried_once_only_and_explains_itself():
    page = ok(
        "<html><head><title>Otra cosa</title></head></html>",
        url="https://www.sodimac.cl/sodimac-cl/otra?Ntt=secreto",
    )
    fetcher = FakeFetcher({"sodimac.cl": page})
    res = SodimacScraper(fetcher).search("secreto")
    assert res.status is ScrapeStatus.LAYOUT_CHANGED
    assert len(fetcher.calls) == 2
    assert "página no reconocida" in res.detail and "Otra cosa" in res.detail
    assert "secreto" not in res.detail  # la consulta del usuario no va en los mensajes


def test_ok_and_empty_pages_are_not_retried(fx):
    fetcher = FakeFetcher({"sodimac.cl": ok(fx("sodimac_results.html"))})
    SodimacScraper(fetcher).search("taladro")
    assert len(fetcher.calls) == 1
    fetcher = FakeFetcher({"sodimac.cl": ok(fx("sodimac_empty.html"))})
    assert SodimacScraper(fetcher).search("nada").status is ScrapeStatus.EMPTY
    assert len(fetcher.calls) == 1


# --- Seguridad: redirecciones y entradas gigantes -------------------------------------------


def test_redirect_to_a_foreign_domain_is_refused(fx):
    page = ok(fx("sodimac_results.html"), url="https://evil.example.com/sodimac-cl/search")
    res = SodimacScraper(FakeFetcher({"sodimac.cl": page})).search("taladro")
    assert res.status is ScrapeStatus.ERROR
    assert res.offers == []
    assert "dominio" in res.detail


def test_redirect_to_a_subdomain_of_the_store_is_fine(fx):
    page = ok(fx("sodimac_results.html"), url="https://m.sodimac.cl/sodimac-cl/search")
    res = SodimacScraper(FakeFetcher({"sodimac.cl": page})).search("taladro")
    assert res.status is ScrapeStatus.OK


def test_lookalike_domain_is_refused(fx):
    page = ok(fx("sodimac_results.html"), url="https://sodimac.cl.evil.com/search")
    assert (
        SodimacScraper(FakeFetcher({"sodimac.cl": page})).search("x").status is ScrapeStatus.ERROR
    )


def test_a_page_with_thousands_of_items_is_capped():
    sc = SodimacScraper(FakeFetcher())
    items = (
        {
            "productId": str(i),
            "displayName": f"P{i}",
            "prices": [{"type": "NORMAL", "priceWithoutFormatting": 9990}],
        }
        for i in range(5000)
    )
    out = sc.collect(items, sc._offer)
    assert len(out.offers) <= 500


def test_a_price_of_infinity_drops_only_that_card_not_the_page():
    def page(results):
        data = {
            "page": "/search",
            "props": {"pageProps": {"searchProps": {"searchData": {"results": results}}}},
        }
        return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'

    bad = {
        "productId": "1",
        "displayName": "Raro",
        "prices": [{"type": "NORMAL", "priceWithoutFormatting": float("inf")}],
    }
    good = {
        "productId": "2",
        "displayName": "Sano",
        "prices": [{"type": "NORMAL", "priceWithoutFormatting": 9990}],
    }
    out = SodimacScraper(FakeFetcher()).parse(page([bad, good]), "")
    assert [o.title for o in out.offers] == ["Sano"]
