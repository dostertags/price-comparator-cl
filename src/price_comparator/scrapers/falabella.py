"""Falabella Chile (www.falabella.com).

Misma tecnología que Sodimac (Next.js), pero los resultados están en
`props.pageProps.results`. Es un marketplace: cada resultado trae `sellerName`, y los patrocinados
aparecen duplicados. La búsqueda es difusa, así que casi nunca devuelve «sin resultados»; la
relevancia se decide después, con el score.
"""

from __future__ import annotations

from typing import Any, ClassVar

from price_comparator.models import Offer, ScrapeStatus
from price_comparator.scrapers.base import ParseOutcome, Scraper, extract_next_data
from price_comparator.scrapers.prices import choose_prices, entries_from

_FIRST_PARTY = {"falabella", "sodimac"}


class FalabellaScraper(Scraper):
    """Scraper de Falabella."""

    store: ClassVar[str] = "Falabella"
    search_url: ClassVar[str] = "https://www.falabella.com/falabella-cl/search"
    query_param: ClassVar[str] = "Ntt"

    def parse(self, text: str, final_url: str) -> ParseOutcome:
        """Extrae ofertas de la página de búsqueda."""
        data = extract_next_data(text)
        if data is None:
            return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED)

        page_props = (data.get("props") or {}).get("pageProps") or {}
        if data.get("page") == "/product":
            # Con un único resultado, Falabella redirige directo a la ficha del producto.
            return self._parse_product_page(page_props.get("productData"), final_url)
        results = page_props.get("results")
        if not isinstance(results, list):
            return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED)
        if not results:
            return ParseOutcome(ScrapeStatus.EMPTY)

        # los patrocinados repiten el producto: se cuentan una sola vez, por URL
        return self.collect(results, self._offer, dedupe_key=lambda o: o.url)

    def _parse_product_page(self, product: Any, url: str) -> ParseOutcome:
        """Lee la ficha de un producto (precios en sus variantes) como una única oferta."""
        if not isinstance(product, dict):
            return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED)
        title = str(product.get("name") or "").strip()
        for variant in product.get("variants") or []:
            prices = entries_from(variant.get("prices"), ("price",), "crossed")
            price, list_price, card_price = choose_prices(prices)
            if title and price is not None:
                offer = Offer(
                    store=self.store,
                    title=title,
                    price_clp=price,
                    url=url,
                    list_price_clp=list_price,
                    card_price_clp=card_price,
                    brand=str(product.get("brandName") or ""),
                )
                return ParseOutcome(ScrapeStatus.OK, [offer])
        return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED)

    def _offer(self, item: dict[str, Any]) -> Offer | None:
        title = str(item.get("displayName") or "").strip()
        url = str(item.get("url") or "")
        price, list_price, card_price = choose_prices(
            entries_from(item.get("prices"), ("price",), "crossed")
        )
        if not title or price is None or not url:
            return None
        seller = str(item.get("sellerName") or "").strip()
        return Offer(
            store=self.store,
            title=title,
            price_clp=price,
            url=url,
            list_price_clp=list_price,
            card_price_clp=card_price,
            brand=str(item.get("brand") or ""),
            seller=seller,
            is_marketplace=bool(seller) and seller.lower() not in _FIRST_PARTY,
        )
