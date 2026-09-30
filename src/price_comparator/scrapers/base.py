"""Clase base de los scrapers.

Ciclo: `search` -> fetch -> `parse` (función pura sobre el HTML) -> `ScrapeResult`.
Un scraper nunca lanza al llamador por fallos de red o de página: los convierte en `status`.
"""

from __future__ import annotations

import itertools
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, ClassVar
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from price_comparator.models import Offer, ScrapeResult, ScrapeStatus
from price_comparator.scrapers.fetch import Fetcher, FetchError
from price_comparator.stores import STORE_HOSTS, host_matches

log = logging.getLogger("price_comparator")

MAX_ITEMS = 500  # una página real trae < 60; más que esto es basura o un ataque


@dataclass
class ParseOutcome:
    """Lo que un parser entiende de una página."""

    status: ScrapeStatus
    offers: list[Offer] = field(default_factory=list)
    dropped: int = 0  # tarjetas descartadas por no tener título o precio


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _diagnose(text: str, final_url: str) -> str:
    """Pistas para reportar un cambio de diseño: título, tamaño y ruta (nunca la query)."""
    match = _TITLE.search(text)
    title = _CONTROL.sub(" ", match.group(1)).strip()[:60] if match else "sin título"
    path = urlsplit(final_url).path
    return f"página no reconocida (título «{title}», {len(text) // 1024} KB, ruta {path})"


def extract_next_data(text: str) -> dict[str, Any] | None:
    """Devuelve el JSON de `script#__NEXT_DATA__`, o `None` si falta o está roto."""
    script = BeautifulSoup(text, "lxml").find("script", id="__NEXT_DATA__")
    if not isinstance(script, Tag):
        return None
    try:
        data = json.loads(script.string or script.get_text())
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class Scraper(ABC):
    """Contrato de una tienda: dada una consulta, devuelve ofertas y un estado."""

    store: ClassVar[str]
    search_url: ClassVar[str]
    query_param: ClassVar[str]

    def __init__(
        self,
        fetcher: Fetcher,
        max_offers: int = 5,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetcher = fetcher
        self._max_offers = max_offers
        self._clock = clock

    @abstractmethod
    def parse(self, text: str, final_url: str) -> ParseOutcome:
        """Interpreta el HTML de una página de resultados (sin red)."""

    def collect(
        self,
        items: Iterable[Any],
        make_offer: Callable[[dict[str, Any]], Offer | None],
        *,
        dedupe_key: Callable[[Offer], str] | None = None,
    ) -> ParseOutcome:
        """Convierte los items crudos de una página en ofertas, contando los descartes.

        Si ningún item se pudo leer, la página se considera de diseño desconocido
        (`layout_changed`) y no «sin resultados».

        Args:
            items: elementos del JSON de la página; los que no sean `dict` cuentan como descartados.
            make_offer: arma la oferta de un item, o `None` si le falta título o precio.
            dedupe_key: si se da, ofertas con la misma clave se cuentan una sola vez.
        """
        offers: list[Offer] = []
        seen: set[str] = set()
        dropped = 0
        for item in itertools.islice(items, MAX_ITEMS):
            offer = make_offer(item) if isinstance(item, dict) else None
            if offer is None:
                dropped += 1
                continue
            if dedupe_key is not None:
                key = dedupe_key(offer)
                if key in seen:
                    continue
                seen.add(key)
            offers.append(offer)
        if not offers:
            return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED, dropped=dropped)
        return ParseOutcome(ScrapeStatus.OK, offers, dropped)

    def search(self, query: str) -> ScrapeResult:
        """Busca `query` en la tienda."""
        started = self._clock()
        result = self._search(query)
        result.elapsed_s = self._clock() - started
        log.info(
            "[%s] '%s' -> %s (%d ofertas, %.1fs)%s",
            self.store,
            query[:60],
            result.status.value,
            len(result.offers),
            result.elapsed_s,
            f" {result.detail}" if result.detail else "",
        )
        return result

    def _search(self, query: str) -> ScrapeResult:
        result = self._attempt(query)
        if result.status is ScrapeStatus.LAYOUT_CHANGED:
            # Páginas intermedias o transitorias existen: un único reintento antes de alarmar.
            log.warning("[%s] página no reconocida; reintentando una vez", self.store)
            result = self._attempt(query)
        return result

    def _attempt(self, query: str) -> ScrapeResult:
        try:
            resp = self._fetcher.get(self.search_url, {self.query_param: query})
        except FetchError as exc:
            return ScrapeResult(self.store, exc.kind, detail=exc.detail)

        hosts = STORE_HOSTS.get(self.store)
        if hosts and not host_matches(resp.url, hosts):
            # Una redirección a otro dominio no es una página de la tienda: no se interpreta.
            return ScrapeResult(
                self.store, ScrapeStatus.ERROR, detail="redirigió fuera del dominio de la tienda"
            )
        if resp.status_code == 404:
            return ScrapeResult(self.store, ScrapeStatus.EMPTY)
        if resp.status_code != 200:
            return ScrapeResult(self.store, ScrapeStatus.ERROR, detail=f"HTTP {resp.status_code}")

        try:
            outcome = self.parse(resp.text, resp.url)
        except Exception as exc:  # noqa: BLE001 - un bug de parser no debe tumbar la corrida
            log.debug("fallo del parser de %s", self.store, exc_info=True)
            return ScrapeResult(
                self.store, ScrapeStatus.ERROR, detail=f"error al interpretar: {exc}"
            )

        offers = outcome.offers[: self._max_offers]
        status = outcome.status
        if status is ScrapeStatus.OK and not offers:
            status = ScrapeStatus.EMPTY
        detail = f"{outcome.dropped} descartadas" if outcome.dropped else ""
        if status is ScrapeStatus.LAYOUT_CHANGED:
            detail = f"{_diagnose(resp.text, resp.url)} {detail}".strip()
        return ScrapeResult(self.store, status, offers, detail=detail)

    def close(self) -> None:
        """Libera el fetcher."""
        self._fetcher.close()

    def __enter__(self) -> Scraper:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
