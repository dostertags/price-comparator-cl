"""Hites Chile (www.hites.com), Salesforce Commerce Cloud.

Fuente primaria: JSON-LD `ItemList` (sin JS). Trampa conocida: el JSON-LD siempre declara
`InStock` y cada tarjeta HTML contiene la insignia «SIN STOCK» oculta con `d-none`; por eso el
stock se toma del JSON-LD y solo se corrige si la insignia es VISIBLE.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from price_comparator.comparison.pricing import parse_price
from price_comparator.models import Offer, PriceKind, ScrapeStatus
from price_comparator.scrapers.base import ParseOutcome, Scraper

_BASE = "https://www.hites.com"
_OUT = ("outofstock", "soldout", "discontinued")


def _item_lists(soup: BeautifulSoup) -> list[list[Any]] | None:
    """Todas las `ItemList` de JSON-LD; `None` si no hay ninguna."""
    found: list[list[Any]] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict) and obj.get("@type") == "ItemList":
                found.append(obj.get("itemListElement") or [])
    return found or None


def _visible_out_of_stock(tile: Tag) -> bool:
    return any(
        not any("d-none" in (a.get("class") or []) for a in badge.parents if isinstance(a, Tag))
        for badge in tile.select(".outofstock")
    )


def _availability(value: Any) -> bool | None:
    if not isinstance(value, str):
        return None
    tail = value.rsplit("/", 1)[-1].lower()
    if tail == "instock":
        return True
    return False if tail in _OUT else None


class HitesScraper(Scraper):
    """Scraper de Hites."""

    store: ClassVar[str] = "Hites"
    search_url: ClassVar[str] = "https://www.hites.com/busqueda"
    query_param: ClassVar[str] = "q"

    def parse(self, text: str, final_url: str) -> ParseOutcome:
        """Extrae ofertas del JSON-LD de la página de búsqueda."""
        soup = BeautifulSoup(text, "lxml")
        lists = _item_lists(soup)
        if lists is None:
            return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED)
        entries = [e for lst in lists for e in lst]
        if not entries:
            return ParseOutcome(ScrapeStatus.EMPTY)

        tiles = {str(t.get("data-pid")): t for t in soup.select(".product-tile[data-pid]")}
        return self.collect(entries, lambda entry: self._offer(entry, tiles))

    def _offer(self, entry: dict[str, Any], tiles: dict[str, Tag]) -> Offer | None:
        item: dict[str, Any] = entry["item"] if isinstance(entry.get("item"), dict) else entry
        title = str(item.get("name") or entry.get("name") or "").strip()
        offers = item.get("offers")
        offers = offers[0] if isinstance(offers, list) and offers else offers
        if not title or not isinstance(offers, dict):
            return None

        kind = PriceKind.EXACT
        if offers.get("@type") == "AggregateOffer" or "lowPrice" in offers:
            price, kind = parse_price(offers.get("lowPrice")), PriceKind.FROM
        else:
            price = parse_price(offers.get("price"))
        url = urljoin(_BASE, str(item.get("url") or offers.get("url") or ""))
        if price is None or url == _BASE:
            return None

        in_stock = _availability(offers.get("availability"))
        sku = str(item.get("identifier") or item.get("sku") or "")
        tile = next((t for pid, t in tiles.items() if sku and pid.startswith(sku)), None)
        if tile is not None and _visible_out_of_stock(tile):
            in_stock = False

        brand = item.get("brand")
        brand = brand.get("name") if isinstance(brand, dict) else brand
        return Offer(
            store=self.store,
            title=title,
            price_clp=price,
            url=url,
            price_kind=kind,
            in_stock=in_stock,
            brand=str(brand or ""),
        )
