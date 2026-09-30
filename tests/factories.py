"""Constructores de datos de prueba."""

from __future__ import annotations

from price_comparator.models import Offer, PriceKind, ScoredOffer


def make_offer(
    store: str = "Sodimac",
    title: str = "Taladro percutor 750W",
    price: int | None = 50_000,
    *,
    url: str | None = None,
    kind: PriceKind = PriceKind.EXACT,
    in_stock: bool | None = None,
    **kwargs,
) -> Offer:
    hosts = {
        "Sodimac": "www.sodimac.cl",
        "Falabella": "www.falabella.com",
        "Hites": "www.hites.com",
    }
    return Offer(
        store=store,
        title=title,
        price_clp=price,
        url=url if url is not None else f"https://{hosts.get(store, 'x.test')}/p/1",
        price_kind=kind,
        in_stock=in_stock,
        **kwargs,
    )


def scored(offer: Offer, score: float = 0.9, reason: str = "") -> ScoredOffer:
    return ScoredOffer(offer=offer, score=score, discard_reason=reason)
