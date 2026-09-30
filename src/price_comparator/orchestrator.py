"""Orquestación: busca en todas las tiendas, tolera fallos y elige el mejor precio."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass
from typing import Protocol

from price_comparator.comparison.query_cleaner import generate_fallback_queries, strip_noise
from price_comparator.comparison.scoring import score
from price_comparator.comparison.selection import SelectionConfig, select_best
from price_comparator.comparison.text import normalize_name
from price_comparator.comparison.validation import ValidationRules, sanitize_offer, validate_offer
from price_comparator.models import (
    Comparison,
    ComparisonStatus,
    ScoredOffer,
    ScrapeResult,
    ScrapeStatus,
    StoreOutcome,
)

log = logging.getLogger("price_comparator")

_FAILED = {
    ScrapeStatus.BLOCKED,
    ScrapeStatus.TIMEOUT,
    ScrapeStatus.ERROR,
    ScrapeStatus.LAYOUT_CHANGED,
}


class ScraperLike(Protocol):
    """Lo que el orquestador necesita de un scraper."""

    @property
    def store(self) -> str:
        """Nombre de la tienda."""
        ...

    def search(self, query: str) -> ScrapeResult:
        """Busca `query` y devuelve ofertas con un estado."""
        ...

    def close(self) -> None:
        """Libera recursos."""
        ...


@dataclass
class RunReport:
    """Resultado de una corrida completa."""

    comparisons: list[Comparison]
    unique: int = 0
    source_broken: bool = False
    interrupted: bool = False


class Comparator:
    """Compara productos entre tiendas."""

    def __init__(
        self,
        scrapers: Sequence[ScraperLike],
        *,
        rules: ValidationRules | None = None,
        selection: SelectionConfig | None = None,
        workers: int = 4,
        scraper_budget_s: float = 45.0,
        cleaner: Callable[[str], list[str]] = generate_fallback_queries,
        max_alt_queries: int = 3,
    ):
        self._scrapers = list(scrapers)
        self._rules = rules or ValidationRules()
        self._selection = selection or SelectionConfig()
        self._workers = max(1, workers)
        self._budget = scraper_budget_s
        self._cleaner = cleaner
        self._max_alt = max_alt_queries

    # ------------------------------------------------------------------ un producto

    def compare_one(self, product: str) -> Comparison:
        """Busca un producto; si no hay coincidencia confiable, reintenta con consultas simples."""
        name = normalize_name(product)
        if not name:
            return Comparison(product="", status=ComparisonStatus.NO_NAME)

        first = self._attempt(name, name)
        if first.status in (ComparisonStatus.FOUND, ComparisonStatus.NO_DATA):
            return first
        for alt in self._cleaner(name)[: self._max_alt]:
            retry = self._attempt(name, alt)
            if retry.status is ComparisonStatus.FOUND:
                retry.notes.append("encontrado con consulta simplificada")
                return retry
        return first

    def _attempt(self, product: str, query: str) -> Comparison:
        results = self._search_all(query)
        reference = strip_noise(product)  # sin cantidad ni paréntesis: no describen al producto
        scored = [
            ScoredOffer(
                offer, score(reference, offer.search_text), validate_offer(offer, self._rules)
            )
            for res in results.values()
            for offer in map(sanitize_offer, res.offers)
        ]
        sel = select_best(scored, self._selection)

        stores: dict[str, StoreOutcome] = {}
        for store, res in results.items():
            mine = [i for i in sel.annotated if i.offer.store == store and not i.discard_reason]
            best = min(mine, key=lambda i: (i.offer.price_clp or 0, -i.score)) if mine else None
            stores[store] = StoreOutcome(res.status, best, res.detail)

        notes = list(sel.notes)
        notes += [f"{s}: {o.status.value}" for s, o in stores.items() if o.status in _FAILED]

        if sel.best_price is not None:
            status = ComparisonStatus.FOUND
        elif results and all(r.status in _FAILED for r in results.values()):
            status = ComparisonStatus.NO_DATA
        elif sel.best_match is not None and sel.best_match.score < self._selection.min_score:
            status = ComparisonStatus.LOW_CONFIDENCE
        else:
            status = ComparisonStatus.NO_RESULTS
            if sel.best_match is not None:
                notes.append("solo hay ofertas sin stock")

        return Comparison(
            product=product,
            status=status,
            query_used=query,
            best_price=sel.best_price,
            best_match=sel.best_match,
            stores=stores,
            offers=sel.annotated,
            notes=notes,
        )

    def _search_all(self, query: str) -> dict[str, ScrapeResult]:
        """Consulta todas las tiendas en paralelo, con tope de tiempo por tienda."""
        if not self._scrapers:
            return {}
        pool = ThreadPoolExecutor(max_workers=len(self._scrapers))
        futures: dict[Future[ScrapeResult], ScraperLike] = {
            pool.submit(self._safe_search, sc, query): sc for sc in self._scrapers
        }
        done, pending = wait(futures, timeout=self._budget)
        results: dict[str, ScrapeResult] = {}
        for fut, sc in futures.items():
            if fut in done:
                results[sc.store] = fut.result()
            else:
                results[sc.store] = ScrapeResult(
                    sc.store, ScrapeStatus.TIMEOUT, detail=f"excedió {self._budget:.0f}s"
                )
        pool.shutdown(wait=False, cancel_futures=True)
        return results

    @staticmethod
    def _safe_search(scraper: ScraperLike, query: str) -> ScrapeResult:
        try:
            return scraper.search(query)
        except Exception as exc:  # noqa: BLE001 - un scraper nunca debe tumbar la corrida
            log.exception("[%s] falló inesperadamente", scraper.store)
            return ScrapeResult(scraper.store, ScrapeStatus.ERROR, detail=type(exc).__name__)

    # ----------------------------------------------------------------- lista completa

    def run(
        self,
        products: Sequence[str],
        on_progress: Callable[[int, int, Comparison], None] | None = None,
    ) -> RunReport:
        """Compara una lista. Busca una vez por nombre único y conserva el orden de entrada."""
        keys = [normalize_name(p).casefold() for p in products]
        unique: dict[str, str] = {}
        for key, product in zip(keys, products, strict=True):
            if key and key not in unique:
                unique[key] = normalize_name(product)

        resolved: dict[str, Comparison] = {}
        interrupted = False
        pool = ThreadPoolExecutor(max_workers=self._workers)
        try:
            futures = {pool.submit(self.compare_one, name): key for key, name in unique.items()}
            for done, fut in enumerate(as_completed(futures), start=1):
                comp = fut.result()
                resolved[futures[fut]] = comp
                if on_progress is not None:
                    on_progress(done, len(unique), comp)
        except KeyboardInterrupt:
            interrupted = True
        finally:
            pool.shutdown(wait=not interrupted, cancel_futures=True)

        no_name = Comparison(product="", status=ComparisonStatus.NO_NAME)
        comparisons: list[Comparison] = []
        for key in keys:
            if not key:
                comparisons.append(no_name)
            elif key in resolved:
                comparisons.append(resolved[key])
            else:
                comparisons.append(
                    Comparison(
                        product=unique[key],
                        status=ComparisonStatus.NO_DATA,
                        notes=["interrumpido antes de buscar"],
                    )
                )

        searched = list(resolved.values())
        broken = (
            bool(searched)
            and not interrupted
            and all(c.status is ComparisonStatus.NO_DATA for c in searched)
        )
        return RunReport(
            comparisons, unique=len(unique), source_broken=broken, interrupted=interrupted
        )
