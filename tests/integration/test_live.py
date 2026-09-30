"""Consultas reales a las tiendas. Excluidas por defecto: `pytest -m live tests/integration`.

`layout_changed` FALLA a propósito: es la señal de que una tienda cambió su HTML.
Un bloqueo (403/429) se omite: es un límite de tasa, no un bug del scraper.
"""

import pytest

from price_comparator.comparison.validation import ValidationRules, validate_offer
from price_comparator.models import ScrapeStatus
from price_comparator.scrapers.falabella import FalabellaScraper
from price_comparator.scrapers.fetch import HttpFetcher
from price_comparator.scrapers.hites import HitesScraper
from price_comparator.scrapers.sodimac import SodimacScraper

pytestmark = pytest.mark.live


@pytest.mark.parametrize("scraper_cls", [SodimacScraper, FalabellaScraper, HitesScraper])
def test_store_returns_valid_offers(scraper_cls):
    fetcher = HttpFetcher(timeout_s=10, max_retries=2, delay_range=(1.0, 2.0))
    with scraper_cls(fetcher, max_offers=3) as scraper:
        res = scraper.search("taladro percutor")

    if res.status in (ScrapeStatus.BLOCKED, ScrapeStatus.TIMEOUT):
        pytest.skip(f"{scraper.store}: {res.status.value} ({res.detail})")
    assert res.status is ScrapeStatus.OK, f"{scraper.store}: {res.status.value} {res.detail}"
    assert res.offers
    rules = ValidationRules()
    for offer in res.offers:
        assert validate_offer(offer, rules) == "", offer
