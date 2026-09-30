"""Construcción de los scrapers activos."""

from __future__ import annotations

from collections.abc import Callable

from price_comparator.config import Settings
from price_comparator.scrapers.base import Scraper
from price_comparator.scrapers.falabella import FalabellaScraper
from price_comparator.scrapers.fetch import Fetcher, HttpFetcher
from price_comparator.scrapers.hites import HitesScraper
from price_comparator.scrapers.sodimac import SodimacScraper

SCRAPER_CLASSES: tuple[type[Scraper], ...] = (SodimacScraper, FalabellaScraper, HitesScraper)


def make_fetcher(settings: Settings) -> Fetcher:
    """Crea el fetcher según `settings.mode`."""
    delay = (settings.delay_min_s, settings.delay_max_s)
    if settings.mode == "headless":  # pragma: no cover - requiere navegador real
        from price_comparator.scrapers.headless import HeadlessFetcher

        return HeadlessFetcher(
            user_agent=settings.user_agent, timeout_s=settings.timeout_s, delay_range=delay
        )
    return HttpFetcher(
        user_agent=settings.user_agent,
        timeout_s=settings.timeout_s,
        max_retries=settings.max_retries,
        delay_range=delay,
        # El fetcher debe rendirse ANTES que el orquestador, para no dejar hilos huérfanos.
        total_budget_s=max(5.0, settings.scraper_budget_s - 5.0),
    )


def build_scrapers(
    settings: Settings,
    fetcher_factory: Callable[[Settings], Fetcher] = make_fetcher,
) -> list[Scraper]:
    """Un scraper por tienda, cada uno con su propio fetcher (sesión y límite de concurrencia)."""
    return [
        cls(fetcher_factory(settings), max_offers=settings.max_offers_per_store)
        for cls in SCRAPER_CLASSES
    ]
