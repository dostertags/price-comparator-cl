# price-comparator-cl

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

> **EN:** Reads a list of products from an Excel file, looks each one up on three Chilean retailers
> (Sodimac, Falabella, Hites) and writes a new Excel with the cheapest reliable match per product.
> Python CLI, no accounts or API keys needed.

Lee una lista de productos desde un Excel, los busca en **Sodimac**, **Falabella** y **Hites**, y te
entrega otro Excel con el **mejor precio** de cada uno y la tienda donde conviene comprar.

Sirve para quien arma cotizaciones o compras seguido (pymes, maestros, oficinas de compras) y no quiere
abrir tres sitios por cada producto. No necesitas cuentas ni claves.

> **Aviso:** herramienta informativa, de uso personal/educativo. Los precios son los publicados por cada
> tienda en el momento de la consulta (sin envío ni precios exclusivos con tarjeta) y pueden cambiar.
> Respeta los términos de uso de cada sitio y no la uses para consultas masivas.

## Contenido

- [Requisitos](#requisitos) · [Instalación](#instalación) · [Uso rápido](#uso-rápido)
- [Ejemplo](#ejemplo-de-entrada-y-salida) · [Opciones](#opciones) · [Configuración](#configuración)
- [Cómo decide el mejor precio](#cómo-decide-el-mejor-precio) · [Módulos](#módulos)
- [Limitaciones](#limitaciones-conocidas) · [Problemas comunes](#problemas-comunes)
- [Tests](#tests) · [Contribuir](#contribuir) · [Licencia](#licencia) · [Changelog](#changelog)

## Requisitos

- Python **3.10 o superior** (Windows, macOS o Linux).
- Conexión a internet.
- Un navegador **solo** si usas `--mode headless` (experimental): `pip install playwright && playwright install chromium`.

## Instalación

```bash
git clone https://github.com/dostertags/price-comparator-cl.git
cd price-comparator-cl
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip   # pip antiguo (<21.3) no instala este proyecto
pip install -r requirements.txt
pip install -e .
```

Opcional: `cp .env.example .env` si quieres cambiar algún parámetro (ver [Configuración](#configuración)).

## Uso rápido

Prepara un `.xlsx` con una columna **Producto** (ver `examples/productos_ejemplo.xlsx`) y ejecuta:

```bash
python -m price_comparator productos.xlsx
```

Crea `productos_resultado_AAAAMMDD_HHMM.xlsx` junto al original. **Nunca modifica tu archivo.**
Con 7 productos distintos tarda ~30 segundos; 100 productos, unos minutos.

## Ejemplo de entrada y salida

Entrada (`productos.xlsx`):

| Producto | Cantidad |
|---|---|
| Taladro percutor 13 mm 750W | 2 |
| Martillo carpintero | 5 |
| Cosa inexistente zzqxkjwv | 1 |

Hoja **Resultados** de la salida (valores reales de una corrida del 30-09-2026; hoy pueden ser otros):

| Producto | Mejor precio (CLP) | Tienda | Producto encontrado | Total (CLP) | Sodimac | Falabella | Hites | Estado |
|---|---:|---|---|---:|---:|---:|---|---|
| Taladro percutor 13 mm 750W | 51.990 | Sodimac | Taladro percutor eléctrico 13 mm 750W | 103.980 | 51.990 | 79.990 | sin coincidencia | Encontrado |
| Martillo carpintero | 3.791 | Sodimac | Martillo carpintero 12 Oz acero | 18.955 | 3.791 | 4.990 | 11.992 | Encontrado |
| Cosa inexistente zzqxkjwv | — | — | — | — | sin resultados | sin coincidencia | sin coincidencia | Baja confianza |

Además trae la hoja **Ofertas** (todas las ofertas vistas y *por qué* se descartó cada una) y la hoja
**Resumen** (parámetros, estado de cada tienda, aviso). Colores: verde = encontrado, amarillo = baja
confianza, rojo = sin resultados o tiendas caídas.

## Opciones

| Opción | Qué hace |
|---|---|
| `--column NOMBRE` | Columna con el producto (por defecto: `Producto`, `Nombre`, `Descripción`, `Product`, `Name`) |
| `--sheet NOMBRE` | Hoja a leer (por defecto la primera) |
| `--output RUTA` | Archivo de salida (por defecto junto al de entrada; nunca sobrescribe) |
| `--max-rows N` | Máximo de productos (500 por defecto; tope 2000) |
| `--workers N` | Productos en paralelo, 1–8 (4 por defecto) |
| `--min-score X` | Coincidencia mínima 0–1 para poder ganar (0,60) |
| `--include-out-of-stock` | Considera también productos sin stock |
| `--mode http\|headless` | Cómo obtener las páginas (`headless` es experimental) |
| `--log-file RUTA`, `-v` | Guardar log / log detallado |

Códigos de salida: `0` listo · `1` ninguna tienda respondió, interrumpido o error inesperado · `2` uso
incorrecto (archivo, columna o configuración).

## Configuración

Variables de entorno con prefijo `PC_` (o en un `.env`). Todas son opcionales:

| Variable | Por defecto | Efecto |
|---|---|---|
| `PC_USER_AGENT` | identificador de la herramienta | User-Agent enviado (único, sin rotación) |
| `PC_TIMEOUT_S` | 15 | Segundos máximos por request |
| `PC_MAX_RETRIES` | 3 | Reintentos (backoff exponencial) |
| `PC_DELAY_MIN_S` / `PC_DELAY_MAX_S` | 1,2 / 3,0 | Pausa cortés entre requests a una tienda |
| `PC_SCRAPER_BUDGET_S` | 45 | Tope de tiempo por tienda y producto |
| `PC_MAX_OFFERS_PER_STORE` | 15 | Ofertas que se leen por tienda |
| `PC_WORKERS` | 4 | Productos en paralelo (máx. 8) |
| `PC_MIN_SCORE` | 0,60 | Coincidencia mínima para ganar |
| `PC_PRICE_MIN_CLP` / `PC_PRICE_MAX_CLP` | 500 / 50.000.000 | Rango de precios considerado realista |
| `PC_MODE` | `http` | `http` o `headless` |
| `PC_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Cómo decide el mejor precio

1. Cada oferta se **valida** (nombre, precio en rango, URL `https` de la tienda) y se **puntúa** contra tu
   texto: cuenta qué fracción de *tus palabras* aparece en el título (con plurales y typos en palabras
   largas) y entiende unidades y medidas (`55 pulgadas` = `55"`, `3 x 2.5 mm` = `3x2.5mm`).
2. Si tu búsqueda trae modelo o medida (`55"`, `750W`, `256GB`) y el título no la tiene, el puntaje cae
   fuerte: `55"` no es `50"`. Una contradicción explícita de género o edad (`niño`/`niña`,
   `hombre`/`mujer`, `adulto`/`infantil`) lo reduce a la mitad.
3. Solo compiten las ofertas con coincidencia ≥ `PC_MIN_SCORE` **y** a menos de 0,10 de la mejor: una
   coincidencia mucho mejor no pierde contra una más barata pero peor.
4. Sin stock queda fuera (salvo `--include-out-of-stock`). Un precio «desde $X» no gana si hay un precio exacto.
5. Un precio absurdamente bajo frente a las demás ofertas necesita coincidencia alta (evita que un accesorio de
   $990 gane contra un producto de $99.990).
6. Gana el **menor precio**; en empate, la mayor coincidencia. Se compara el precio público de internet/oferta:
   **sin envío y sin precio exclusivo con tarjeta** (este último queda en la hoja *Ofertas*).

Si un producto no calza, se reintenta con consultas más simples (quita cantidad, paréntesis, códigos…), pero
**siempre puntuando contra tu nombre original** (sin el ruido), para no aceptar cualquier cosa. Cuando nada
supera el umbral, el estado es **Baja confianza** y se muestra la mejor coincidencia sin dar un «mejor precio».

## Seguridad

- **No usa credenciales ni cuentas.** Consulta las tiendas de forma anónima, con un User-Agent fijo, pausas y
  `bloqueado` ante 403/429 (no intenta esquivar protecciones).
- **Tu Excel y las páginas de las tiendas son entradas no confiables:** se rechazan archivos corruptos, «bombas»
  zip/XML (por eso `defusedxml` es una dependencia), cantidades absurdas y precios malformados; los textos de
  las tiendas se limpian antes de escribirlos y nunca se interpretan como fórmulas de Excel.
- Solo se aceptan URLs `https` de las tiendas; una redirección a otro dominio se descarta.
- Para reportar una vulnerabilidad, abre un issue **sin** datos sensibles o escribe al mantenedor del repo.

## Módulos

| Paquete | Qué hace |
|---|---|
| `price_comparator.cli` | Argumentos, códigos de salida, progreso |
| `price_comparator.orchestrator` | Consulta las 3 tiendas en paralelo, tolera fallos, dedupe, segunda pasada |
| `price_comparator.scrapers` | Un scraper por tienda; `fetch` (HTTP/headless) separado del parseo |
| `price_comparator.comparison` | Precio CLP, score, validación, selección del mejor precio, limpieza de consultas |
| `price_comparator.excel` | Lectura de la entrada y escritura del informe |

## Limitaciones conocidas

- **Los sitios cambian su HTML sin aviso.** Si una tienda cambia, verás `cambió el sitio` para ella y las demás
  siguen funcionando. Abre un issue (ver [CONTRIBUTING](CONTRIBUTING.md)).
- Bloqueos temporales (403/429): la tienda sale como `bloqueado`; baja `--workers` y reintenta más tarde.
- El enlace de **Sodimac** abre la búsqueda por SKU (sus resultados no traen URL directa del producto).
- Falabella es marketplace: puede ganar un vendedor externo (se anota en la hoja *Ofertas*).
- Si el título de la tienda omite la capacidad (p. ej. Falabella publica «iPhone 17 Pro Max» sin GB), una búsqueda
  con «256GB» puede no encontrarlo: prueba también sin la capacidad.
- La coincidencia es por texto: con nombres muy genéricos puede equivocarse. Revisa la columna *Confianza*.
  Modelos vecinos con el mismo texto (p. ej. «Ryzen 5» vs «Ryzen 3») puntúan igual y gana el más barato.
- Si una tienda responde una página que no reconoce, se reintenta una vez; si persiste, sale `cambió el sitio`.
- Solo pesos chilenos. Sin envío, sin cupones, sin precios con tarjeta en el ranking.
- El modo `headless` es experimental y no se prueba en CI.

## Problemas comunes

| Síntoma | Qué hacer |
|---|---|
| `No encontré la columna del producto` | Renombra la columna a `Producto` o usa `--column "Tu columna"` |
| Todas las tiendas `bloqueado` / código de salida 1 | Espera unos minutos, usa `--workers 1` y sube `PC_DELAY_MIN_S` |
| Una tienda siempre `cambió el sitio` | El sitio cambió su HTML: abre un issue con `--verbose` |
| `El archivo no parece un .xlsx válido` | Ábrelo en Excel y guárdalo de nuevo como `.xlsx` (no vale `.xls` ni `.csv`) |
| El resultado sale con `_2` al final | Ya existía el archivo, o estaba abierto en Excel: nunca se sobrescribe |
| Letras raras en la consola de Windows | `chcp 65001` antes de ejecutar |
| `Directory cannot be installed in editable mode` | Actualiza pip: `python -m pip install --upgrade pip` |

## Tests

```bash
pip install -r requirements-dev.txt
pytest                                  # sin red
pytest --cov=price_comparator           # con reporte; exige cobertura >= 80 %
pytest -m live tests/integration -rs    # consulta las tiendas reales (opt-in)
ruff check . && ruff format --check . && mypy
```

## Contribuir

Haz fork, crea una rama, escribe el test primero y abre un PR. Detalles en [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

[MIT](LICENSE).

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md). **0.1.0**: lectura de Excel, scrapers de Sodimac/Falabella/Hites, comparación con
coincidencia por texto, informe de 3 hojas.
