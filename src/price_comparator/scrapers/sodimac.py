"""Sodimac Chile (www.sodimac.cl).

La búsqueda es una página Next.js: los resultados vienen en `__NEXT_DATA__`
(`props.pageProps.searchProps.searchData.results`). Cuando no hay resultados, Sodimac redirige a
la home (ruta `/[...uri]`). Los resultados no traen URL de producto; se enlaza la búsqueda por SKU.
"""

from __future__ import annotations

from typing import Any, ClassVar

from price_comparator.models import Offer, ScrapeStatus
from price_comparator.scrapers.base import ParseOutcome, Scraper, extract_next_data
from price_comparator.scrapers.prices import choose_prices, entries_from

_HOME_ROUTE = "/[...uri]"


class SodimacScraper(Scraper):
    """Scraper de Sodimac."""

    store: ClassVar[str] = "Sodimac"
    search_url: ClassVar[str] = "https://www.sodimac.cl/sodimac-cl/search"
    query_param: ClassVar[str] = "Ntt"

    def parse(self, text: str, final_url: str) -> ParseOutcome:
        """Extrae ofertas de la página de búsqueda."""
        data = extract_next_data(text)
        if data is None:
            return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED)

        page_props = (data.get("props") or {}).get("pageProps") or {}
        search_props = page_props.get("searchProps")
        if search_props is None:
            status = (
                ScrapeStatus.EMPTY
                if data.get("page") == _HOME_ROUTE
                else ScrapeStatus.LAYOUT_CHANGED
            )
            return ParseOutcome(status)

        results = (search_props.get("searchData") or {}).get("results")
        if not isinstance(results, list):
            return ParseOutcome(ScrapeStatus.LAYOUT_CHANGED)
        if not results:
            return ParseOutcome(ScrapeStatus.EMPTY)

        return self.collect(results, self._offer)

    def _offer(self, item: dict[str, Any]) -> Offer | None:
        title = str(item.get("displayName") or "").strip()
        price, list_price, card_price = choose_prices(
            entries_from(item.get("prices"), ("priceWithoutFormatting", "price"))
        )
        product_id = str(item.get("productId") or item.get("skuId") or "")
        if not title or price is None or not product_id:
            return None
        return Offer(
            store=self.store,
            title=title,
            price_clp=price,
            url=f"{self.search_url}?{self.query_param}={product_id}",
            list_price_clp=list_price,
            card_price_clp=card_price,
            brand=str(item.get("brand") or ""),
            model=str(item.get("model") or ""),
        )
