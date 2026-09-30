"""Línea de comandos. Es el único módulo que imprime y decide códigos de salida.

Códigos de salida: 0 = corrida completa (aunque haya productos sin precio);
1 = ninguna tienda respondió, corrida interrumpida o error inesperado;
2 = uso incorrecto (archivo, columna, configuración).
"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys
import time
from collections.abc import Callable, MutableMapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TextIO

from price_comparator import __version__
from price_comparator.comparison.selection import SelectionConfig
from price_comparator.comparison.validation import ValidationRules
from price_comparator.config import ConfigError, Settings, load_env_file
from price_comparator.excel.reader import DEFAULT_MAX_ROWS, InputError, read_products
from price_comparator.excel.writer import ReportInfo, resolve_output_path, write_report
from price_comparator.logging_setup import configure_logging
from price_comparator.models import Comparison
from price_comparator.orchestrator import Comparator, ScraperLike

log = logging.getLogger("price_comparator")

ScrapersFactory = Callable[[Settings], Sequence[ScraperLike]]


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="price-comparator",
        description=(
            "Busca cada producto de un Excel en Sodimac, Falabella y Hites "
            "y devuelve el mejor precio."
        ),
        epilog="Salida: 0 ok · 1 tiendas caídas/interrumpido/error · 2 uso incorrecto.",
    )
    p.add_argument("input", type=Path, help="archivo .xlsx con la lista de productos")
    p.add_argument(
        "--column", help="columna con el nombre del producto (por defecto: Producto/Nombre/…)"
    )
    p.add_argument("--sheet", help="hoja a leer (por defecto la primera)")
    p.add_argument(
        "--output", type=Path, help="archivo de salida (por defecto junto al de entrada)"
    )
    p.add_argument(
        "--max-rows", type=int, default=DEFAULT_MAX_ROWS, help="máximo de productos (tope 2000)"
    )
    p.add_argument("--workers", type=int, help="productos en paralelo (1-8)")
    p.add_argument("--min-score", type=float, help="coincidencia mínima 0-1 para poder ganar")
    p.add_argument("--mode", choices=("http", "headless"), help="cómo obtener las páginas")
    p.add_argument(
        "--include-out-of-stock", action="store_true", help="considerar productos sin stock"
    )
    p.add_argument("--log-file", type=Path, help="además, guardar el log en este archivo")
    p.add_argument("--verbose", "-v", action="store_true", help="log detallado (DEBUG)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _default_scrapers(settings: Settings) -> Sequence[ScraperLike]:
    from price_comparator.scrapers.registry import build_scrapers

    return build_scrapers(settings)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: MutableMapping[str, str] | None = None,
    scrapers_factory: ScrapersFactory = _default_scrapers,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Punto de entrada. Devuelve el código de salida."""
    out, err = stdout or sys.stdout, stderr or sys.stderr
    args = _parser().parse_args(argv)

    env: MutableMapping[str, str]
    if environ is None:
        env = dict(os.environ)
        load_env_file(Path(".env"), env)
    else:
        env = environ

    try:
        settings = Settings.from_env(env)
        overrides = {
            k: v
            for k, v in {
                "workers": args.workers,
                "min_score": args.min_score,
                "mode": args.mode,
            }.items()
            if v is not None
        }
        if args.verbose:
            overrides["log_level"] = "DEBUG"
        settings = dataclasses.replace(settings, **overrides)
        settings.validate()
    except ConfigError as exc:
        print(f"Configuración inválida: {exc}", file=err)
        return 2

    if args.max_rows < 1:
        print("Error: --max-rows debe ser al menos 1.", file=err)
        return 2

    try:
        configure_logging(settings.log_level, args.log_file)
    except OSError as exc:
        print(f"No pude abrir el archivo de log {args.log_file}: {exc.strerror or exc}", file=err)
        return 2

    try:
        rows = read_products(
            args.input, column=args.column, sheet=args.sheet, max_rows=args.max_rows
        )
    except InputError as exc:
        print(f"Error: {exc}", file=err)
        return 2

    started = datetime.now()
    t0 = time.monotonic()
    scrapers: Sequence[ScraperLike] = []
    try:
        scrapers = scrapers_factory(settings)
        comparator = Comparator(
            scrapers,
            rules=ValidationRules(
                min_price=settings.price_min_clp, max_price=settings.price_max_clp
            ),
            selection=SelectionConfig(
                min_score=settings.min_score, include_out_of_stock=args.include_out_of_stock
            ),
            workers=settings.workers,
            scraper_budget_s=settings.scraper_budget_s,
        )

        def progress(done: int, total: int, comp: Comparison) -> None:
            print(f"[{done}/{total}] {comp.status.value}: {comp.product[:60]}", file=err)

        report = comparator.run([r.name for r in rows], on_progress=progress)

        if report.source_broken:
            print(
                "Ninguna tienda respondió con datos utilizables (bloqueo, caída o cambio de "
                "diseño). No se generó ningún Excel. Revisa tu conexión o ejecuta con --verbose.",
                file=err,
            )
            return 1

        info = ReportInfo(
            started_at=started,
            elapsed_s=time.monotonic() - t0,
            version=__version__,
            params={
                "min_score": settings.min_score,
                "workers": settings.workers,
                "mode": settings.mode,
                "incluye_sin_stock": args.include_out_of_stock,
                "rango_precio_clp": f"{settings.price_min_clp}-{settings.price_max_clp}",
            },
            unique=report.unique,
            interrupted=report.interrupted,
        )
        output = resolve_output_path(args.input, args.output, started)
        try:
            written = write_report(rows, report.comparisons, output, info)
        except OSError as exc:
            print(f"No pude escribir el resultado: {exc}. Prueba con --output.", file=err)
            return 2
    except Exception as exc:  # noqa: BLE001 - la CLI no muestra trazas crudas
        log.debug("error inesperado", exc_info=True)
        print(
            f"Error inesperado ({type(exc).__name__}): {exc}. "
            "Ejecuta con --verbose para más detalle.",
            file=err,
        )
        return 1
    finally:
        for scraper in scrapers:
            scraper.close()

    print(f"Listo: {written}", file=out)
    if report.interrupted:
        print("La corrida se interrumpió: el archivo tiene resultados parciales.", file=err)
        return 1
    return 0
