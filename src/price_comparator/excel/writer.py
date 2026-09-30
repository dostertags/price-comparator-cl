"""Escritura del Excel de resultados (3 hojas). Nunca modifica el archivo de entrada."""

from __future__ import annotations

import math
import os
import re
import tempfile
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from price_comparator.excel.reader import ProductRow
from price_comparator.models import Comparison, ComparisonStatus, ScrapeStatus
from price_comparator.stores import STORE_HOSTS, STORES, host_matches

RESULT_COLUMNS = (
    "Producto",
    "Cantidad",
    "Mejor precio (CLP)",
    "Tienda ganadora",
    "Producto encontrado",
    "Total (CLP)",
    *(f"{s} (CLP)" for s in STORES),
    "Ahorro vs. la más cara (CLP)",
    "Confianza",
    "Enlace",
    "Estado",
    "Consulta usada",
    "Notas",
)
_WIDTHS = (36, 9, 16, 14, 44, 14, 14, 14, 14, 16, 11, 40, 22, 28, 40)
OFFER_COLUMNS = (
    "Producto",
    "Tienda",
    "Título",
    "Marca",
    "Precio (CLP)",
    "Tipo de precio",
    "Precio lista (CLP)",
    "Precio tarjeta (CLP)",
    "Coincidencia",
    "En stock",
    "Vendedor",
    "URL",
    "Motivo de descarte",
)

HEADER_BLUE, GREEN, GREEN_STRONG, YELLOW, RED = "1F3663", "E2EFDA", "C6E0B4", "FFF2CC", "FFE0E0"
_ROW_FILL = {
    ComparisonStatus.FOUND: GREEN,
    ComparisonStatus.LOW_CONFIDENCE: YELLOW,
}
_STORE_TEXT = {
    ScrapeStatus.OK: "sin coincidencia",
    ScrapeStatus.EMPTY: "sin resultados",
    ScrapeStatus.BLOCKED: "bloqueado",
    ScrapeStatus.TIMEOUT: "timeout",
    ScrapeStatus.LAYOUT_CHANGED: "cambió el sitio",
    ScrapeStatus.ERROR: "error",
}
_BORDER = Border(*(Side(style="thin", color="BFBFBF"),) * 4)
_DISCLAIMER = (
    "Precios informativos publicados por cada tienda, sin envío ni precios exclusivos con tarjeta; "
    "pueden cambiar en cualquier momento. Verifica en el sitio antes de comprar."
)


@dataclass
class ReportInfo:
    """Datos de la corrida para la hoja «Resumen»."""

    started_at: datetime
    elapsed_s: float
    version: str
    params: dict[str, object] = field(default_factory=dict)
    unique: int = 0
    interrupted: bool = False
    source_broken: bool = False


# openpyxl lanza IllegalCharacterError con estos caracteres y se perdería todo el informe.
_ILLEGAL_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(value: Any) -> Any:
    """Quita los caracteres de control que Excel no admite (vienen de sitios de terceros)."""
    return _ILLEGAL_XML.sub("", value) if isinstance(value, str) else value


def is_formula_like(value: object) -> bool:
    """¿Excel interpretaría este texto como fórmula? (empieza con `=`, `+`, `-`, `@`, tab o CR)."""
    return isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r")


def safe_url(url: str) -> bool:
    """Solo se enlazan URLs https de las tiendas conocidas."""
    return any(host_matches(url, hosts) for hosts in STORE_HOSTS.values())


def resolve_output_path(input_path: Path, output: Path | None, now: datetime) -> Path:
    """Elige un nombre de salida que no exista todavía (nunca sobrescribe)."""
    if output is None:
        output = input_path.with_name(f"{input_path.stem}_resultado_{now:%Y%m%d_%H%M}.xlsx")
    return _first_free(output)


def _first_free(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(2, 100):
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"No pude encontrar un nombre libre cerca de {path}")


# ------------------------------------------------------------------ helpers de celdas


def _put(ws: Worksheet, row: int, col: int, value: Any, *, number_format: str | None = None) -> Any:
    value = _clean(value)
    cell = ws.cell(row=row, column=col, value=value)
    if is_formula_like(value):
        cell.data_type = "s"  # texto literal: jamás fórmula
        cell.quotePrefix = True  # sobrevive a «Guardar como CSV»: Excel no lo reinterpreta
    if number_format:
        cell.number_format = number_format
    cell.border = _BORDER
    return cell


def _header(ws: Worksheet, columns: Sequence[str], widths: Sequence[int]) -> None:
    fill = PatternFill("solid", start_color=HEADER_BLUE)
    for i, name in enumerate(columns, start=1):
        c = ws.cell(row=1, column=i, value=name)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"


def _link(cell: Any, url: str) -> None:
    if safe_url(url):
        cell.hyperlink = url
        cell.font = Font(color="0563C1", underline="single")


# ---------------------------------------------------------------------- hojas


def _store_value(comp: Comparison, store: str) -> Any:
    outcome = comp.stores.get(store)
    if outcome is None:
        return None
    if outcome.best is not None:
        return outcome.best.offer.price_clp
    return _STORE_TEXT.get(outcome.status, "")


def _results_sheet(ws: Worksheet, rows: Sequence[ProductRow], comps: Sequence[Comparison]) -> None:
    _header(ws, RESULT_COLUMNS, _WIDTHS)
    col = {name: i for i, name in enumerate(RESULT_COLUMNS, start=1)}
    for r, (prod, comp) in enumerate(zip(rows, comps, strict=True), start=2):
        fill = PatternFill("solid", start_color=_ROW_FILL.get(comp.status, RED))
        win = comp.best_price
        shown = win or comp.best_match
        prices = [
            o.best.offer.price_clp
            for o in comp.stores.values()
            if o.best and o.best.offer.price_clp
        ]
        notes = [*comp.notes, *prod.notes]
        if comp.status is ComparisonStatus.LOW_CONFIDENCE and shown:
            notes.append(
                f"mejor coincidencia: {shown.offer.title} (${shown.offer.price_clp:,})".replace(
                    ",", "."
                )
            )
        total = None
        if win and win.offer.price_clp and prod.quantity:
            raw_total = prod.quantity * win.offer.price_clp
            total = round(raw_total) if math.isfinite(raw_total) else None
        values: dict[str, Any] = {
            "Producto": prod.original or prod.name,
            "Cantidad": prod.quantity,
            "Mejor precio (CLP)": win.offer.price_clp if win else None,
            "Tienda ganadora": win.offer.store if win else None,
            "Producto encontrado": shown.offer.title if shown else None,
            "Total (CLP)": total,
            "Ahorro vs. la más cara (CLP)": max(prices) - min(prices) if len(prices) >= 2 else None,
            "Confianza": shown.score if shown else None,
            "Enlace": win.offer.url if win else None,
            "Estado": comp.status.value,
            "Consulta usada": comp.query_used
            if comp.query_used and comp.query_used != prod.name
            else None,
            "Notas": "; ".join(notes) or None,
        }
        for store in STORES:
            values[f"{store} (CLP)"] = _store_value(comp, store)
        for name, value in values.items():
            money = name.endswith("(CLP)")
            cell = _put(ws, r, col[name], value, number_format="#,##0" if money else None)
            cell.fill = fill
            cell.alignment = Alignment(
                horizontal="right" if money else "left", vertical="center", wrap_text=not money
            )
        ws.cell(r, col["Confianza"]).number_format = "0%"
        if win:
            ws.cell(r, col["Mejor precio (CLP)"]).font = Font(bold=True)
            ws.cell(r, col["Mejor precio (CLP)"]).fill = PatternFill(
                "solid", start_color=GREEN_STRONG
            )
            _link(ws.cell(r, col["Enlace"]), win.offer.url)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(RESULT_COLUMNS))}{max(ws.max_row, 1)}"


def _offers_sheet(ws: Worksheet, comps: Sequence[Comparison]) -> None:
    _header(ws, OFFER_COLUMNS, (30, 11, 44, 14, 13, 12, 14, 14, 12, 9, 18, 40, 28))
    r = 2
    for comp in {
        id(c): c for c in comps
    }.values():  # una vez por comparación, aunque el producto se repita
        for item in comp.offers:
            o = item.offer
            stock = {True: "sí", False: "no", None: "?"}[o.in_stock]
            row: tuple[Any, ...] = (
                comp.product,
                o.store,
                o.title,
                o.brand,
                o.price_clp,
                o.price_kind.value,
                o.list_price_clp,
                o.card_price_clp,
                item.score,
                stock,
                o.seller,
                o.url,
                item.discard_reason,
            )
            for i, value in enumerate(row, start=1):
                cell = _put(ws, r, i, None if value == "" else value)
                if i in (5, 7, 8):
                    cell.number_format = "#,##0"
                if i == 9:
                    cell.number_format = "0%"
            _link(ws.cell(r, 12), o.url)
            r += 1
    ws.auto_filter.ref = f"A1:{get_column_letter(len(OFFER_COLUMNS))}{max(ws.max_row, 1)}"


def _summary_sheet(
    ws: Worksheet, rows: Sequence[ProductRow], comps: Sequence[Comparison], info: ReportInfo
) -> None:
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 70
    lines: list[tuple[str, Any]] = [
        ("Fecha", info.started_at.strftime("%d/%m/%Y %H:%M")),
        ("Versión", info.version),
        ("Duración", f"{info.elapsed_s:.0f} s"),
        ("Productos en el archivo", len(rows)),
        ("Productos únicos buscados", info.unique),
    ]
    if info.interrupted:
        lines.append(
            ("ATENCIÓN", "Corrida interrumpida: los productos pendientes quedan sin datos.")
        )
    if info.source_broken:
        lines.append(
            (
                "ATENCIÓN",
                "Ninguna tienda respondió con datos utilizables: revisa tu conexión "
                "o abre un issue.",
            )
        )
    lines.append(("", ""))
    lines += [(f"Estado: {s.value}", n) for s, n in Counter(c.status for c in comps).items()]
    lines.append(("", ""))
    wins = Counter(c.best_price.offer.store for c in comps if c.best_price)
    lines += [(f"Tienda ganadora: {s}", wins.get(s, 0)) for s in STORES]
    lines.append(("", ""))
    unique = {id(c): c for c in comps}.values()
    for store in STORES:
        counts = Counter(c.stores[store].status.value for c in unique if store in c.stores)
        lines.append(
            (f"Consultas a {store}", ", ".join(f"{k}: {v}" for k, v in counts.items()) or "—")
        )
    lines.append(("", ""))
    lines += [(f"Parámetro: {k}", v) for k, v in info.params.items()]
    lines += [("", ""), ("Aviso", _DISCLAIMER)]
    for r, (label, value) in enumerate(lines, start=1):
        a = ws.cell(row=r, column=1, value=_clean(label))
        a.font = Font(bold=True)
        value = _clean(value)
        b = ws.cell(row=r, column=2, value=value)
        b.alignment = Alignment(wrap_text=True, vertical="top", horizontal="left")
        if is_formula_like(value):
            b.data_type = "s"


# ----------------------------------------------------------------------- salida


def write_report(
    rows: Sequence[ProductRow],
    comparisons: Sequence[Comparison],
    output: Path,
    info: ReportInfo,
) -> Path:
    """Escribe el informe de forma atómica y devuelve la ruta final.

    Si el destino está bloqueado (p. ej. abierto en Excel) usa un nombre con sufijo `_2`, `_3`…

    Args:
        rows: filas de entrada, en su orden original.
        comparisons: un resultado por fila (los duplicados pueden compartir objeto).
        output: ruta deseada.
        info: datos de la corrida para el resumen.
    """
    wb = Workbook()
    results = wb.active or wb.create_sheet()
    results.title = "Resultados"
    _results_sheet(results, rows, comparisons)
    _offers_sheet(wb.create_sheet("Ofertas"), comparisons)
    _summary_sheet(wb.create_sheet("Resumen"), rows, comparisons, info)

    # Nombre aleatorio y exclusivo (O_EXCL): un nombre fijo permite un ataque de enlace simbólico.
    fd, tmp_name = tempfile.mkstemp(dir=output.parent, prefix=f".{output.name}.", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        wb.save(tmp)
        target = _first_free(output)
        for _ in range(10):
            try:
                os.replace(tmp, target)
                return target
            except PermissionError:
                target = _first_free(target.with_name(f"{target.stem}_2{target.suffix}"))
        raise PermissionError(
            f"No pude escribir el resultado junto a {output}; ¿está abierto en Excel?"
        )
    finally:
        tmp.unlink(missing_ok=True)
