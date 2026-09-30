# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y [SemVer](https://semver.org/lang/es/).

## [0.1.0] - 2026-09-30

Primera versión.

### Agregado
- Lectura de un Excel (`.xlsx`) con productos: detecta la columna (`Producto`, `Nombre`, `Descripción`…),
  acepta duplicados, filas vacías y la columna opcional `Cantidad` (valores no válidos o absurdos se ignoran con una nota).
- Scrapers de **Sodimac**, **Falabella** y **Hites** (HTTP, sin navegador). Modo `--mode headless`
  experimental con Playwright.
- Estado explícito por tienda: `ok`, `empty`, `blocked`, `timeout`, `layout_changed`, `error`.
- Regla del mejor precio: menor precio entre coincidencias confiables; informa aparte la mejor coincidencia.
- Coincidencia por texto (rapidfuzz) con penalización si faltan modelo, medida o capacidad
  (`55"` ≠ `50"`, `750W` ≠ sin dato de potencia) y con alias de unidades (`pulgadas`, `lts`, `galón`…).
- Segunda pasada con consultas simplificadas para productos sin coincidencia (se puntúa contra el nombre
  original sin ruido, para no aceptar cualquier cosa).
- Distingue nuevo de reacondicionado, variantes (Pro vs Pro Max, S25 vs S25 Ultra), accesorios (carcasas,
  micas, repuestos) e imitaciones de marca (`Hiphone` vs `iPhone`); mira 15 ofertas por tienda en vez de 5.
- Falabella: soporte de la ficha de producto a la que redirige cuando la búsqueda tiene un único resultado.
- Una página no reconocida se reintenta una vez y deja un diagnóstico (título, tamaño, ruta).
- Puntaje por cobertura de palabras + banda de selección (0,10) + contradicción de género/edad,
  calibrados con casos reales de bicicletas, computadores y zapatos.
- Endurecimiento: `defusedxml` (bombas de entidades XML), límites de zip, redirecciones solo dentro del
  dominio de la tienda, plazo total real por tienda (incluida la lectura de la respuesta), precios y textos
  acotados, archivos temporales no predecibles y protección contra fórmulas también al exportar a CSV.
- Excel de salida con 3 hojas (`Resultados`, `Ofertas`, `Resumen`); nunca modifica el archivo de entrada.
- Validaciones: precio realista, URL `https` de las tiendas, texto sano; protección contra fórmulas en Excel.
- CLI con códigos de salida `0/1/2`, `Ctrl+C` con resultados parciales, configuración por variables `PC_*`.
- Tests unitarios y de integración sin red (cobertura > 90 %), tests `live` opt-in.

### Limitaciones conocidas
- El enlace de Sodimac abre la búsqueda por SKU (los resultados no traen URL directa del producto).
- No incluye envío ni precios exclusivos con tarjeta en el ranking.
- Los sitios pueden cambiar su HTML: el scraper afectado informa `layout_changed`.
- Modelos vecinos con el mismo texto («Ryzen 5» vs «Ryzen 3») no se distinguen por puntaje.
