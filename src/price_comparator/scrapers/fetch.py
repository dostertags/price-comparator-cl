"""Obtención de páginas: contrato `Fetcher` y su implementación HTTP.

Separar «traer el HTML» de «entender el HTML» permite probar los parsers con fixtures y cambiar
a un navegador headless sin tocar los scrapers.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import requests

from price_comparator.models import ScrapeStatus

log = logging.getLogger("price_comparator")

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; price-comparator-cl/0.1; uso personal)"
_BLOCK_CODES = (403, 429)


@dataclass(frozen=True)
class FetchResponse:
    """Respuesta ya decodificada."""

    status_code: int
    text: str
    url: str


class FetchError(Exception):
    """Fallo de red o bloqueo tras agotar los reintentos.

    Attributes:
        kind: estado que se le informa al usuario (`blocked`, `timeout` o `error`).
        detail: descripción legible; nunca incluye la consulta del usuario.
    """

    def __init__(self, kind: ScrapeStatus, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


class Fetcher(Protocol):
    """Lo mínimo que un scraper necesita para traer una página."""

    def get(self, url: str, params: Mapping[str, str] | None = None) -> FetchResponse:
        """Descarga `url` con `params` como query string."""
        ...

    def close(self) -> None:
        """Libera recursos."""
        ...


class HttpFetcher:
    """GET con pausa cortés, reintentos con backoff exponencial y tope de tamaño.

    No rota User-Agent ni falsifica cabeceras: ante 403/429 espera y, si persiste, informa
    `blocked` en vez de intentar esquivar la protección del sitio.
    """

    def __init__(
        self,
        *,
        session: Any | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_s: float = 15.0,
        max_retries: int = 3,
        delay_range: tuple[float, float] = (1.2, 3.0),
        retry_wait_s: float = 6.0,
        max_concurrent: int = 2,
        max_bytes: int = 10_000_000,
        total_budget_s: float = 40.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ):
        self._session = session if session is not None else requests.Session()
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.5",
        }
        self._timeout = timeout_s
        self._max_retries = max(1, max_retries)
        self._delay = delay_range
        self._retry_wait = retry_wait_s
        self._max_bytes = max_bytes
        self.total_budget_s = total_budget_s
        self._sleep = sleep
        self._clock = clock
        self._rng = rng or random.Random()  # noqa: S311  # nosec B311 - jitter, no criptografía
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))

    def get(self, url: str, params: Mapping[str, str] | None = None) -> FetchResponse:
        """Descarga `url`. Devuelve 404 y otros 4xx tal cual; lanza `FetchError` si no se pudo.

        `total_budget_s` es un plazo total real: cubre la espera de cupo, las pausas corteses, los
        requests y los backoffs. Al agotarse se abandona sin dormir de más, conservando el tipo del
        último error (`blocked`, `error`…) o `timeout` si ni siquiera hubo un intento.
        """
        host = urlsplit(url).netloc
        deadline = self._clock() + self.total_budget_s
        kind, detail, attempts = ScrapeStatus.TIMEOUT, "presupuesto de tiempo agotado", 0
        for attempt in range(1, self._max_retries + 1):
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            try:
                if not self._slots.acquire(timeout=remaining):
                    break  # otro hilo ocupa los cupos de la tienda y no alcanzamos a esperar
                try:
                    delay = self._rng.uniform(*self._delay)
                    if delay >= deadline - self._clock():
                        break
                    self._sleep(delay)
                    attempts += 1
                    resp = self._session.get(
                        url,
                        params=dict(params) if params else None,
                        headers=self._headers,
                        timeout=min(self._timeout, deadline - self._clock()),
                        stream=True,
                        allow_redirects=True,
                    )
                    status = resp.status_code
                    if status == 200:
                        return FetchResponse(200, self._read(resp, deadline), str(resp.url))
                    resp.close()
                finally:
                    self._slots.release()
                if status in _BLOCK_CODES:
                    kind, detail = ScrapeStatus.BLOCKED, f"HTTP {status}"
                elif status >= 500:
                    kind, detail = ScrapeStatus.ERROR, f"HTTP {status}"
                else:
                    return FetchResponse(status, "", str(resp.url))
            except requests.exceptions.Timeout:
                kind, detail = ScrapeStatus.TIMEOUT, "timeout"
            except requests.exceptions.RequestException as exc:
                kind, detail = ScrapeStatus.ERROR, f"error de conexión: {type(exc).__name__}"

            if attempt < self._max_retries:
                wait = self._retry_wait * 2 ** (attempt - 1) + self._rng.uniform(0, 1)
                if wait >= deadline - self._clock():
                    break  # dormir el backoff nos pasaría del plazo: mejor rendirse ya
                log.warning(
                    "%s en %s (intento %d/%d); reintentando en %.0fs",
                    detail,
                    host,
                    attempt,
                    self._max_retries,
                    wait,
                )
                self._sleep(wait)
        suffix = f"tras {attempts} intentos" if attempts else "sin llegar a intentar"
        raise FetchError(kind, f"{detail} en {host} ({suffix}, plazo {self.total_budget_s:.0f}s)")

    def _read(self, resp: Any, deadline: float) -> str:
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(65536):
            if self._clock() > deadline:  # un servidor que gotea datos no puede retener el hilo
                resp.close()
                raise FetchError(
                    ScrapeStatus.TIMEOUT, "la lectura de la respuesta excedió el plazo"
                )
            total += len(chunk)
            if total > self._max_bytes:
                resp.close()
                raise FetchError(ScrapeStatus.ERROR, "respuesta demasiado grande")
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")

    def close(self) -> None:
        """Cierra la sesión HTTP."""
        self._session.close()
