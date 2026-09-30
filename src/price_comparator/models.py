"""Tipos de datos compartidos por toda la herramienta."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PriceKind(str, Enum):
    """Qué representa el precio publicado."""

    EXACT = "exact"
    FROM = "from"  # «desde $X»: mínimo de un rango, no el precio de ese producto


class ScrapeStatus(str, Enum):
    """Resultado de consultar una tienda."""

    OK = "ok"
    EMPTY = "empty"  # la tienda respondió y no hay resultados
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    LAYOUT_CHANGED = "layout_changed"  # respondió, pero no reconocemos la página
    ERROR = "error"


class ComparisonStatus(str, Enum):
    """Estado final de un producto."""

    FOUND = "Encontrado"
    LOW_CONFIDENCE = "Baja confianza"
    NO_RESULTS = "Sin resultados"
    NO_DATA = "Sin datos (tiendas caídas)"
    NO_NAME = "Sin nombre"


@dataclass(frozen=True)
class Offer:
    """Un producto tal como lo publica una tienda."""

    store: str
    title: str
    price_clp: int | None
    url: str
    price_kind: PriceKind = PriceKind.EXACT
    list_price_clp: int | None = None  # precio tachado / normal
    card_price_clp: int | None = None  # precio exclusivo con tarjeta (informativo)
    in_stock: bool | None = None  # None = no se pudo saber
    brand: str = ""
    model: str = ""
    seller: str = ""
    is_marketplace: bool = False

    @property
    def search_text(self) -> str:
        """Texto contra el que se compara la consulta."""
        return " ".join(p for p in (self.brand, self.title, self.model) if p)


@dataclass
class ScrapeResult:
    """Salida de `Scraper.search`."""

    store: str
    status: ScrapeStatus
    offers: list[Offer] = field(default_factory=list)
    elapsed_s: float = 0.0
    detail: str = ""


@dataclass(frozen=True)
class ScoredOffer:
    """Oferta con su coincidencia; `discard_reason` vacío = elegible."""

    offer: Offer
    score: float
    discard_reason: str = ""


@dataclass(frozen=True)
class StoreOutcome:
    """Qué pasó con una tienda para un producto."""

    status: ScrapeStatus
    best: ScoredOffer | None = None
    detail: str = ""


@dataclass
class Comparison:
    """Resultado completo para un producto."""

    product: str
    status: ComparisonStatus
    query_used: str = ""
    best_price: ScoredOffer | None = None
    best_match: ScoredOffer | None = None
    stores: dict[str, StoreOutcome] = field(default_factory=dict)
    offers: list[ScoredOffer] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
