import os
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from price_comparator.excel.reader import ProductRow
from price_comparator.excel.writer import (
    RESULT_COLUMNS,
    ReportInfo,
    is_formula_like,
    resolve_output_path,
    safe_url,
    write_report,
)
from price_comparator.models import (
    Comparison,
    ComparisonStatus,
    ScoredOffer,
    ScrapeStatus,
    StoreOutcome,
)
from tests.factories import make_offer

NOW = datetime(2026, 9, 30, 14, 5)
INFO = ReportInfo(
    started_at=NOW, elapsed_s=12.3, version="0.1.0", params={"min_score": 0.6}, unique=2
)


def row(name="Taladro percutor 750W", qty=None, n=2):
    return ProductRow(row_number=n, original=name, name=name, quantity=qty)


def found(price=60_000, store="Falabella", extra=()):
    best = ScoredOffer(make_offer(store, "Taladro percutor 750W", price), 0.92)
    stores = {
        "Sodimac": StoreOutcome(
            ScrapeStatus.OK, ScoredOffer(make_offer("Sodimac", price=80_000), 0.9)
        ),
        "Falabella": StoreOutcome(ScrapeStatus.OK, best if store == "Falabella" else None),
        "Hites": StoreOutcome(ScrapeStatus.BLOCKED),
    }
    return Comparison(
        product="Taladro percutor 750W",
        status=ComparisonStatus.FOUND,
        query_used="Taladro percutor 750W",
        best_price=best,
        best_match=best,
        stores=stores,
        offers=[ScoredOffer(make_offer("Sodimac", price=80_000), 0.9), best, *extra],
        notes=["Hites: blocked"],
    )


def not_found():
    return Comparison(
        product="Cosa rara",
        status=ComparisonStatus.NO_RESULTS,
        stores={"Sodimac": StoreOutcome(ScrapeStatus.EMPTY)},
    )


def low_conf():
    off = ScoredOffer(make_offer("Sodimac", "Cortina", 9_990), 0.3, "coincidencia baja")
    return Comparison(
        product="Taladro", status=ComparisonStatus.LOW_CONFIDENCE, best_match=off, offers=[off]
    )


def out(tmp_path, rows, comps, info=INFO):
    path = write_report(rows, comps, tmp_path / "out.xlsx", info)
    return load_workbook(path)


def test_resolve_output_path_default_is_next_to_input_with_timestamp(tmp_path):
    p = resolve_output_path(tmp_path / "lista.xlsx", None, NOW)
    assert p == tmp_path / "lista_resultado_20260930_1405.xlsx"


def test_resolve_output_path_respects_explicit_output_and_never_overwrites(tmp_path):
    explicit = tmp_path / "salida.xlsx"
    assert resolve_output_path(tmp_path / "lista.xlsx", explicit, NOW) == explicit
    explicit.write_bytes(b"x")
    assert resolve_output_path(tmp_path / "lista.xlsx", explicit, NOW) == tmp_path / "salida_2.xlsx"


def test_report_has_three_sheets_and_column_order(tmp_path):
    wb = out(tmp_path, [row()], [found()])
    assert wb.sheetnames == ["Resultados", "Ofertas", "Resumen"]
    headers = [c.value for c in wb["Resultados"][1]]
    assert headers == list(RESULT_COLUMNS)
    assert headers[:4] == ["Producto", "Cantidad", "Mejor precio (CLP)", "Tienda ganadora"]


def test_result_row_values(tmp_path):
    ws = out(tmp_path, [row(qty=3)], [found()])["Resultados"]
    r = {h: c.value for h, c in zip(RESULT_COLUMNS, ws[2], strict=True)}
    assert r["Mejor precio (CLP)"] == 60_000
    assert r["Tienda ganadora"] == "Falabella"
    assert r["Total (CLP)"] == 180_000
    assert r["Sodimac (CLP)"] == 80_000
    assert r["Falabella (CLP)"] == 60_000
    assert r["Hites (CLP)"] == "bloqueado"
    assert r["Ahorro vs. la más cara (CLP)"] == 20_000
    assert r["Confianza"] == pytest.approx(0.92)
    assert r["Estado"] == "Encontrado"
    assert "Hites: blocked" in r["Notas"]


def test_no_total_without_quantity(tmp_path):
    ws = out(tmp_path, [row()], [found()])["Resultados"]
    assert ws.cell(2, RESULT_COLUMNS.index("Total (CLP)") + 1).value is None


def test_winner_link_is_a_hyperlink(tmp_path):
    ws = out(tmp_path, [row()], [found()])["Resultados"]
    cell = ws.cell(2, RESULT_COLUMNS.index("Enlace") + 1)
    assert cell.hyperlink is not None and cell.hyperlink.target.startswith(
        "https://www.falabella.com"
    )


def test_row_colors_follow_status(tmp_path):
    wb = out(
        tmp_path,
        [row(), row("Cosa rara", n=3), row("Taladro", n=4)],
        [found(), not_found(), low_conf()],
    )
    ws = wb["Resultados"]
    colors = [ws.cell(i, 1).fill.start_color.rgb[-6:] for i in (2, 3, 4)]
    assert colors == ["E2EFDA", "FFE0E0", "FFF2CC"]


def test_winner_price_cell_is_bold(tmp_path):
    ws = out(tmp_path, [row()], [found()])["Resultados"]
    assert ws.cell(2, 3).font.bold is True


def test_not_found_and_low_confidence_rows(tmp_path):
    ws = out(tmp_path, [row("Cosa rara"), row("Taladro", n=3)], [not_found(), low_conf()])[
        "Resultados"
    ]
    assert ws.cell(2, RESULT_COLUMNS.index("Estado") + 1).value == "Sin resultados"
    assert ws.cell(2, 3).value is None
    assert ws.cell(3, RESULT_COLUMNS.index("Estado") + 1).value == "Baja confianza"
    assert ws.cell(3, 3).value is None
    assert "Cortina" in ws.cell(3, RESULT_COLUMNS.index("Producto encontrado") + 1).value


def test_duplicate_input_rows_reuse_the_same_comparison(tmp_path):
    c = found()
    ws = out(tmp_path, [row(n=2), row(n=3)], [c, c])["Resultados"]
    assert ws.max_row == 3
    assert ws.cell(3, 3).value == 60_000


def test_offers_sheet_lists_every_offer_with_discard_reason_once_per_comparison(tmp_path):
    bad = ScoredOffer(make_offer("Hites", "Broca", None), 0.5, "sin precio")
    c = found(extra=[bad])
    ws = out(tmp_path, [row(n=2), row(n=3)], [c, c])["Ofertas"]
    assert ws.max_row == 1 + 3
    assert "sin precio" in [cell.value for cell in ws[4]]


def test_summary_sheet_has_counts_params_and_disclaimer(tmp_path):
    ws = out(tmp_path, [row(), row("Cosa rara", n=3)], [found(), not_found()])["Resumen"]
    text = "\n".join(str(c.value) for r in ws.iter_rows() for c in r if c.value is not None)
    assert "0.1.0" in text
    assert "Encontrado" in text and "Sin resultados" in text
    assert "min_score" in text
    assert "sin envío" in text.lower()


def test_interrupted_run_is_flagged_in_summary(tmp_path):
    info = ReportInfo(NOW, 1.0, "0.1.0", {}, 1, interrupted=True)
    ws = out(tmp_path, [row()], [found()], info)["Resumen"]
    text = "\n".join(str(c.value) for r in ws.iter_rows() for c in r if c.value is not None)
    assert "interrumpid" in text.lower()


@pytest.mark.parametrize("value", ["=SUMA(1)", "+cmd", "-2+3", "@SUM(A1)"])
def test_formula_injection_is_neutralized(tmp_path, value):
    c = found()
    c.offers[1] = ScoredOffer(make_offer("Falabella", value, 60_000), 0.9)
    wb = out(tmp_path, [ProductRow(2, value, value, None)], [c])
    cell = wb["Resultados"].cell(2, 1)
    assert cell.data_type == "s"
    assert cell.value == value
    offer_titles = [r[2] for r in wb["Ofertas"].iter_rows(min_row=2, values_only=True)]
    assert value in offer_titles
    assert all(x.data_type != "f" for r in wb["Ofertas"].iter_rows() for x in r)


def test_is_formula_like_flags_only_dangerous_strings():
    assert is_formula_like("=SUMA(1)") and is_formula_like("+1") and is_formula_like("@x")
    assert not is_formula_like("Taladro")
    assert not is_formula_like(5)
    assert not is_formula_like(None)


def test_safe_url_only_allows_known_stores():
    assert safe_url("https://www.sodimac.cl/x") is True
    assert safe_url("https://evil.example.com/x") is False
    assert safe_url("http://www.sodimac.cl/x") is False
    assert safe_url("javascript:alert(1)") is False


def test_original_input_file_is_never_modified(tmp_path):
    original = tmp_path / "lista.xlsx"
    original.write_bytes(b"contenido original")
    write_report([row()], [found()], resolve_output_path(original, None, NOW), INFO)
    assert original.read_bytes() == b"contenido original"


def test_no_temp_files_are_left_behind(tmp_path):
    write_report([row()], [found()], tmp_path / "o.xlsx", INFO)
    assert [p.name for p in tmp_path.iterdir()] == ["o.xlsx"]


def test_locked_destination_falls_back_to_a_suffixed_name(tmp_path, monkeypatch):
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("abierto en Excel")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    path = write_report([row()], [found()], tmp_path / "o.xlsx", INFO)
    assert Path(path).name == "o_2.xlsx"
    assert path.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["o_2.xlsx"]


@pytest.mark.parametrize("field", ["title", "seller", "brand", "model", "url"])
def test_control_characters_from_stores_never_crash_the_report(tmp_path, field):
    """Regresión: openpyxl lanza IllegalCharacterError y se perdía todo el informe."""
    dirty = "x\x07y\x0bz"
    kwargs = {"seller": "V", "brand": "B", "model": "M"}
    title, url = "Taladro", None
    if field == "title":
        title = dirty
    elif field == "url":
        url = "https://www.sodimac.cl/p\x07"
    else:
        kwargs[field] = dirty
    bad = ScoredOffer(
        make_offer("Sodimac", title, 60_000, url=url, **kwargs),
        0.9,
        "nombre con caracteres de control",
    )
    comp = Comparison(product="Taladro", status=ComparisonStatus.NO_RESULTS, offers=[bad])
    wb = out(tmp_path, [row()], [comp])
    texts = [
        c.value for r in wb["Ofertas"].iter_rows(min_row=2) for c in r if isinstance(c.value, str)
    ]
    if field not in ("url", "model"):  # `model` no se escribe en ninguna columna
        assert any("xyz" in t for t in texts)
    assert not any(ch in t for t in texts for ch in ("\x07", "\x0b"))


def test_huge_quantity_never_breaks_the_total(tmp_path):
    best = ScoredOffer(make_offer("Sodimac", "Taladro", 60_000), 0.9)
    comp = Comparison(
        product="Taladro",
        status=ComparisonStatus.FOUND,
        best_price=best,
        best_match=best,
        offers=[best],
    )
    ws = out(tmp_path, [ProductRow(2, "Taladro", "Taladro", float("inf"))], [comp])["Resultados"]
    assert ws.cell(2, RESULT_COLUMNS.index("Total (CLP)") + 1).value is None


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2", "@x", "\t=cmd", "\r=cmd"])
def test_formula_like_values_are_text_and_quote_prefixed(tmp_path, value):
    """Sobrevive a un «Guardar como CSV»: con quotePrefix Excel no la reinterpreta como fórmula."""
    wb = out(tmp_path, [ProductRow(2, value, value, None)], [not_found()])
    cell = wb["Resultados"].cell(2, 1)
    assert cell.data_type == "s"
    assert cell.quotePrefix is True


def test_temp_file_name_is_unpredictable_and_in_the_same_directory(tmp_path, monkeypatch):
    seen = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append(Path(src))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    target = tmp_path / "o.xlsx"
    write_report([row()], [found()], target, INFO)
    (tmp_src,) = seen
    assert tmp_src.parent == target.parent
    assert tmp_src.name != "o.xlsx.tmp"  # un nombre fijo permite un ataque de enlace simbólico
