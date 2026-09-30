"""Clasificación de los distintos precios que publica una tienda."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from price_comparator.comparison.pricing import parse_price

_CARD_HINTS = ("cmr", "card", "tarjeta")
_PUBLIC_HINTS = ("normal", "internet", "event", "oferta", "offer", "sale")


def entries_from(
    prices: Any,
    value_keys: Sequence[str],
    crossed_key: str | None = None,
) -> list[tuple[str, int, bool]]:
    """Convierte la lista `prices` de una tienda en tuplas `(tipo, valor_clp, tachado)`.

    Args:
        prices: valor crudo del JSON; si no es una lista de dicts devuelve `[]`.
        value_keys: claves donde buscar el valor, en orden de preferencia.
        crossed_key: clave booleana que marca el precio tachado, si la tienda la publica.
    """
    out: list[tuple[str, int, bool]] = []
    for p in prices if isinstance(prices, list) else []:
        if not isinstance(p, dict):
            continue
        value = next((v for k in value_keys if (v := parse_price(p.get(k)))), None)
        if value:
            out.append((str(p.get("type", "")), value, bool(crossed_key and p.get(crossed_key))))
    return out


def choose_prices(
    entries: Iterable[tuple[str, int, bool]],
) -> tuple[int | None, int | None, int | None]:
    """Separa los precios de un producto en (público, lista, tarjeta).

    Args:
        entries: tuplas `(tipo, valor_clp, tachado)` tal como las publica la tienda.

    Returns:
        - público: el menor precio visible para cualquiera (es el que se compara),
        - lista: el precio tachado o de combo (solo informativo),
        - tarjeta: el menor precio exclusivo con tarjeta (solo informativo).
        Los tipos desconocidos se ignoran; cualquier valor puede ser `None`.
    """
    public: list[int] = []
    listed: list[int] = []
    card: list[int] = []
    for kind, value, crossed in entries:
        label = kind.lower()
        if any(h in label for h in _CARD_HINTS):
            card.append(value)
        elif crossed or "combo" in label:
            listed.append(value)
        elif any(h in label for h in _PUBLIC_HINTS):
            public.append(value)
    return (
        min(public) if public else None,
        max(listed) if listed else None,
        min(card) if card else None,
    )
