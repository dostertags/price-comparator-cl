"""Chequeos de sanidad sobre lo que devuelven las tiendas."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from price_comparator.comparison.text import fix_mojibake
from price_comparator.models import Offer
from price_comparator.stores import STORE_HOSTS, host_matches

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
MAX_TITLE_LEN = 300
MAX_URL_LEN = 2048
MAX_SHORT_FIELD_LEN = 100

DEFAULT_HOSTS = STORE_HOSTS


@dataclass(frozen=True)
class ValidationRules:
    """Parámetros de validación; los rangos de precio son configurables."""

    min_price: int = 500
    max_price: int = 50_000_000
    allowed_hosts: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_HOSTS))


def _url_problem(url: str, store: str, rules: ValidationRules) -> str:
    if not url or len(url) > MAX_URL_LEN:
        return "url inválida (vacía o demasiado larga)"
    if not host_matches(url, rules.allowed_hosts.get(store, ())):
        return "url inválida (dominio no permitido o formato inseguro)"
    return ""


def validate_offer(offer: Offer, rules: ValidationRules) -> str:
    """Devuelve el motivo de descarte, o cadena vacía si la oferta es válida."""
    title = offer.title or ""
    if not title.strip():
        return "sin nombre"
    if len(title) > MAX_TITLE_LEN:
        return "nombre demasiado largo"
    if _CONTROL.search(title):
        return "nombre con caracteres de control"
    if offer.price_clp is None:
        return "sin precio"
    if offer.price_clp <= 0:
        return "precio no positivo"
    if not rules.min_price <= offer.price_clp <= rules.max_price:
        return "precio fuera de rango realista"
    return _url_problem(offer.url, offer.store, rules)


def sanitize_offer(offer: Offer) -> Offer:
    """Corrige datos corruptos (precios secundarios, mojibake) sin descartar la oferta."""
    offer = replace(
        offer,
        title=fix_mojibake(offer.title[: MAX_TITLE_LEN + 1]),  # +1: sigue marcándose «largo»
        brand=fix_mojibake(offer.brand[:MAX_SHORT_FIELD_LEN]),
        model=fix_mojibake(offer.model[:MAX_SHORT_FIELD_LEN]),
        seller=fix_mojibake(offer.seller[:MAX_SHORT_FIELD_LEN]),
    )
    list_price = offer.list_price_clp
    card_price = offer.card_price_clp
    price = offer.price_clp or 0
    if list_price is not None and (list_price <= 0 or list_price < price):
        list_price = None
    if card_price is not None and card_price <= 0:
        card_price = None
    if list_price == offer.list_price_clp and card_price == offer.card_price_clp:
        return offer
    return replace(offer, list_price_clp=list_price, card_price_clp=card_price)
