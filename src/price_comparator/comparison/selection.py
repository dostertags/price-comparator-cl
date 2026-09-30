"""Regla del «mejor precio».

1. Solo compiten ofertas válidas con coincidencia >= `min_score`.
2. Sin stock queda fuera (salvo `include_out_of_stock`); stock desconocido cuenta como disponible.
3. Un precio absurdamente bajo frente a las demás ofertas necesita coincidencia alta.
4. Un precio «desde» solo gana si es la única opción.
5. Solo compiten las ofertas dentro de una banda del mejor puntaje disponible: una coincidencia
   mucho mejor no pierde contra una más barata pero peor.
6. Gana el menor precio; empate -> mayor coincidencia -> orden fijo de tiendas.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field, replace

from price_comparator.models import PriceKind, ScoredOffer
from price_comparator.stores import STORES as STORE_ORDER

_BELOW_BAND = "coincidencia inferior a la mejor"


@dataclass(frozen=True)
class SelectionConfig:
    """Parámetros de selección."""

    min_score: float = 0.60
    include_out_of_stock: bool = False
    outlier_ratio: float = 0.20  # precio < ratio * mediana(demás) => sospechoso
    outlier_min_score: float = 0.80
    band: float = 0.10  # cuánto puede quedar bajo la mejor coincidencia y aún competir por precio


@dataclass
class Selection:
    """Resultado de `select_best`."""

    best_price: ScoredOffer | None
    best_match: ScoredOffer | None
    annotated: list[ScoredOffer]
    notes: list[str] = field(default_factory=list)


def _store_rank(store: str) -> int:
    return STORE_ORDER.index(store) if store in STORE_ORDER else len(STORE_ORDER)


def _price(item: ScoredOffer) -> int:
    return item.offer.price_clp or 0


def _sort_key(item: ScoredOffer) -> tuple[int, float, int]:
    return (_price(item), -item.score, _store_rank(item.offer.store))


def select_best(offers: list[ScoredOffer], cfg: SelectionConfig) -> Selection:
    """Aplica la regla del mejor precio y anota el motivo de cada descarte."""
    annotated: list[ScoredOffer] = []
    notes: list[str] = []

    for item in offers:
        reason = item.discard_reason
        if not reason and item.score < cfg.min_score:
            reason = "coincidencia baja"
        if not reason and item.offer.in_stock is False and not cfg.include_out_of_stock:
            reason = "sin stock"
        if reason != item.discard_reason:
            item = replace(item, discard_reason=reason)
        annotated.append(item)

    eligible_idx = [i for i, item in enumerate(annotated) if not item.discard_reason]
    for idx in eligible_idx:
        item = annotated[idx]
        others = [_price(annotated[j]) for j in eligible_idx if j != idx]
        if not others:
            continue
        cheap = _price(item) < cfg.outlier_ratio * statistics.median(others)
        if cheap and item.score < cfg.outlier_min_score:
            annotated[idx] = replace(item, discard_reason="posible error de precio")

    still_eligible = [i for i in annotated if not i.discard_reason]
    if still_eligible:
        floor = max(i.score for i in still_eligible) - cfg.band - 1e-9
        for idx, item in enumerate(annotated):
            if not item.discard_reason and item.score < floor:
                annotated[idx] = replace(item, discard_reason=_BELOW_BAND)

    eligible = [i for i in annotated if not i.discard_reason]
    exact = [i for i in eligible if i.offer.price_kind != PriceKind.FROM]
    pool = exact or eligible
    best_price = min(pool, key=_sort_key) if pool else None

    if best_price is not None:
        if best_price.offer.price_kind == PriceKind.FROM:
            notes.append("precio «desde»: no es el precio exacto del producto")
        if best_price.offer.in_stock is None:
            notes.append("stock no verificado")

    valid = [
        i
        for i in annotated
        if i.discard_reason in ("", "coincidencia baja", "sin stock", _BELOW_BAND)
    ]
    best_match = (
        max(valid, key=lambda i: (i.score, -_price(i), -_store_rank(i.offer.store)))
        if valid
        else None
    )
    return Selection(best_price=best_price, best_match=best_match, annotated=annotated, notes=notes)
