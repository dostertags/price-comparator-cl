"""Fetcher con navegador headless (Playwright). EXPERIMENTAL: no se prueba en CI.

Úsalo solo si una tienda deja de servir HTML útil por HTTP. Requiere:
    pip install playwright && playwright install chromium
Los objetos de la API síncrona de Playwright solo pueden usarse desde el hilo que los creó, así
que todo el trabajo corre en un único hilo dedicado (también evita lanzar varios Chromium).
"""

from __future__ import annotations

import random
import time
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlencode

from price_comparator.models import ScrapeStatus
from price_comparator.scrapers.fetch import FetchError, FetchResponse


class HeadlessFetcher:  # pragma: no cover - requiere navegador real
    """Fetcher que renderiza la página con Chromium sin interfaz."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_s: float = 30.0,
        delay_range: tuple[float, float] = (1.2, 3.0),
    ):
        self._user_agent = user_agent
        self._timeout_ms = int(timeout_s * 1000)
        self._delay = delay_range
        self._rng = random.Random()  # noqa: S311  # nosec B311 - jitter, no criptografía
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="headless")
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None

    def get(self, url: str, params: Mapping[str, str] | None = None) -> FetchResponse:
        """Renderiza `url` y devuelve el HTML resultante."""
        full = f"{url}?{urlencode(params)}" if params else url
        return self._pool.submit(self._fetch, full).result()

    def _ensure(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise FetchError(
                ScrapeStatus.ERROR,
                "falta playwright: pip install playwright && playwright install chromium",
            ) from exc
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = self._browser.new_context(user_agent=self._user_agent, locale="es-CL")

    def _fetch(self, url: str) -> FetchResponse:
        self._ensure()
        time.sleep(self._rng.uniform(*self._delay))
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            page.wait_for_timeout(1500)
            return FetchResponse(200, page.content(), page.url)
        except Exception as exc:
            kind = ScrapeStatus.TIMEOUT if "Timeout" in type(exc).__name__ else ScrapeStatus.ERROR
            raise FetchError(kind, f"navegador headless: {type(exc).__name__}") from exc
        finally:
            page.close()

    def close(self) -> None:
        """Cierra el navegador y el hilo dedicado."""
        if self._context is not None:
            self._pool.submit(self._shutdown).result()
        self._pool.shutdown(wait=False)

    def _shutdown(self) -> None:
        self._context.close()
        self._browser.close()
        self._pw.stop()
