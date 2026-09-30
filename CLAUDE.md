# price-comparator-cl

CLI en Python que lee productos de un `.xlsx`, los busca en Sodimac, Falabella y Hites y escribe otro `.xlsx`
con el mejor precio. Sin credenciales. Package `src/price_comparator/`, Python >= 3.10.

## Comandos

- Tests (sin red): `pytest` · con cobertura: `pytest --cov=price_comparator` (mínimo 80 %)
- Tests contra tiendas reales (opt-in): `pytest -m live tests/integration -rs`
- Calidad: `ruff check . && ruff format --check . && mypy` (mypy estricto en `src/`)
- Ejecutar: `python -m price_comparator examples/productos_ejemplo.xlsx`

## Mapa

```
cli.py            único lugar con print / códigos de salida (0 ok, 1 tiendas caídas, 2 uso)
orchestrator.py   3 tiendas en paralelo, timeouts, dedupe, segunda pasada, source_broken
scrapers/         base.py (Scraper: search -> parse puro) · fetch.py (HttpFetcher) · sodimac/falabella/hites.py
comparison/       pricing · scoring · validation · selection · query_cleaner · text
excel/            reader.py · writer.py (3 hojas, escritura atómica)
models.py         Offer, ScrapeResult, ScoredOffer, Comparison, enums
tests/            unit/ integration/ fixtures/html/ · fakes.py (FakeFetcher) · factories.py
```

## Convenciones

- **TDD**: test primero, verlo fallar por la razón correcta, luego implementar.
- Sin efectos al importar (nada de logging ni archivos a nivel de módulo). Config se inyecta desde `cli`.
- Un scraper nunca lanza al llamador: convierte fallos en `ScrapeStatus`. `empty` ≠ `layout_changed`.
- Parsers = funciones puras `html -> ParseOutcome`, probadas con fixtures en `tests/fixtures/html/`.
- Los tests unitarios no pueden usar la red (guardia en `conftest.py`); lo real lleva `@pytest.mark.live`.
- Español en mensajes al usuario y docstrings; identificadores en inglés.
- Sin evasión anti-bot: un User-Agent fijo, pausas, `blocked` ante 403/429.

## Trampas conocidas (descubiertas en vivo)

- Hites: la insignia «SIN STOCK» está en TODAS las tarjetas dentro de `.d-none`; el stock sale del JSON-LD.
- Sodimac: sin resultados redirige a la home (`page == "/[...uri]"`); los resultados no traen URL de producto.
- Falabella: búsqueda difusa (nunca «vacía»), patrocinados duplicados, títulos con mojibake (`fix_mojibake`).
- La segunda pasada puntúa contra el nombre ORIGINAL (si no, «Cosa» encontraba «Casa de verano»).
- `score` = 0,75·cobertura de palabras^1,5 + 0,25·similitud; penaliza specs ausentes (modelo, medida,
  capacidad) y contradicciones de género/edad (×0,5). La similitud sola «satura» con títulos largos.
- Señales de «otro producto» en `score` (×0,5 cada una): reacondicionado/usado no pedido, variante pedida ausente
  (Pro/Max/Ultra…), accesorio no pedido (carcasa, funda, mica…) e imitación de marca (`hiphone`≈`iphone`).
  Sin tolerancia fuzzy a typos (dejaba pasar imitaciones). Sodimac no vende celulares: sale `empty`.
- `select_best` solo deja competir por precio a las ofertas dentro de una banda (0,10) de la mejor.
- Falabella redirige a la ficha del producto (`page == "/product"`) cuando hay un único resultado.
- Una página desconocida se reintenta una vez (`Scraper._search`); `layout_changed` lleva diagnóstico.
- Entradas no confiables: Excel (defusedxml, límites zip, `except` amplio en `read_products`), precios
  (`parse_price` acotado), textos de tiendas (`sanitize_offer`, `_clean` del writer), redirecciones
  (`stores.host_matches`). Cualquier plazo nuevo debe respetar `total_budget_s` del `HttpFetcher`.

## Nunca

Credenciales, `.env`, Excels reales, logs, nombres de clientes ni rutas personales (el hook `forbid-private-terms`
de `.pre-commit-config.yaml` bloquea las rutas absolutas).
