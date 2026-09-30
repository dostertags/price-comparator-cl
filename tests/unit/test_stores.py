"""La lista de tiendas vive en un solo lugar; todo lo demás debe derivar de ella."""

from urllib.parse import urlsplit

from price_comparator import stores
from price_comparator.comparison import selection, validation
from price_comparator.config import Settings
from price_comparator.excel import writer
from price_comparator.scrapers.fetch import HttpFetcher
from price_comparator.scrapers.registry import SCRAPER_CLASSES, make_fetcher


def test_scrapers_are_registered_in_the_same_order_as_the_store_list():
    assert [c.store for c in SCRAPER_CLASSES] == list(stores.STORES)


def test_every_scraper_url_belongs_to_its_store_hosts():
    for cls in SCRAPER_CLASSES:
        host = urlsplit(cls.search_url).hostname or ""
        assert any(host == h or host.endswith("." + h) for h in stores.STORE_HOSTS[cls.store])


def test_selection_writer_and_validation_derive_from_the_single_source():
    assert selection.STORE_ORDER is stores.STORES
    assert writer.STORES is stores.STORES
    assert validation.DEFAULT_HOSTS is stores.STORE_HOSTS


def test_fetcher_deadline_is_shorter_than_the_orchestrator_budget():
    settings = Settings.from_env({})
    fetcher = make_fetcher(settings)
    assert isinstance(fetcher, HttpFetcher)
    assert fetcher.total_budget_s < settings.scraper_budget_s
