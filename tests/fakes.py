"""Dobles de prueba: un fetcher que sirve fixtures y una sesión HTTP falsa."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace

from price_comparator.models import Offer, ScrapeResult, ScrapeStatus
from price_comparator.scrapers.fetch import FetchError, FetchResponse


class FakeFetcher:
    """Devuelve respuestas programadas, sin red. `routes` mapea subcadena de URL -> respuesta."""

    def __init__(self, routes: Mapping[str, FetchResponse | Exception] | None = None):
        self.routes = dict(routes or {})
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.closed = False

    def get(self, url: str, params: Mapping[str, str] | None = None) -> FetchResponse:
        self.calls.append((url, dict(params or {})))
        for needle, result in self.routes.items():
            if needle in url:
                if isinstance(result, list):  # respuestas en secuencia; la última se repite
                    result = result.pop(0) if len(result) > 1 else result[0]
                if isinstance(result, Exception):
                    raise result
                if result.url == DEFAULT_URL:  # la respuesta viene de la URL pedida
                    result = replace(result, url=url)
                return result
        raise FetchError(ScrapeStatus.ERROR, f"sin ruta falsa para {url}")

    def close(self) -> None:
        self.closed = True


DEFAULT_URL = "https://example.test/"


def ok(text: str, url: str = DEFAULT_URL) -> FetchResponse:
    return FetchResponse(status_code=200, text=text, url=url)


class FakeScraper:
    """Scraper programable para probar el orquestador."""

    def __init__(
        self,
        store: str,
        behaviour: Callable[[str], ScrapeResult] | ScrapeResult | Exception,
    ):
        self.store = store
        self.behaviour = behaviour
        self.queries: list[str] = []

    def search(self, query: str) -> ScrapeResult:
        self.queries.append(query)
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        if callable(self.behaviour):
            return self.behaviour(query)
        return self.behaviour

    def close(self) -> None:
        pass


def result(store: str, *offers: Offer, status: ScrapeStatus = ScrapeStatus.OK) -> ScrapeResult:
    return ScrapeResult(store=store, status=status, offers=list(offers))


class FakeResponse:
    """Imita `requests.Response` en modo stream."""

    def __init__(self, status_code=200, body=b"", url="https://example.test/", headers=None):
        self.status_code = status_code
        self._body = body
        self.url = url
        self.headers = headers or {}
        self.encoding = None

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self):
        pass


class FakeSession:
    """Imita `requests.Session`: consume una cola de respuestas o excepciones."""

    def __init__(self, *queue):
        self.queue = list(queue)
        self.calls: list[dict] = []

    def get(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        item = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass
