import re
from pathlib import Path

import pytest
from openpyxl import Workbook

from price_comparator.excel.reader import InputError, read_products


def make_xlsx(path, rows, sheet="Hoja1", extra_sheets=()):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    for name in extra_sheets:
        wb.create_sheet(name)
    wb.save(path)
    return path


def test_reads_products_with_row_numbers(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["Taladro 750W"], ["Sierra circular"]])
    rows = read_products(f)
    assert [r.name for r in rows] == ["Taladro 750W", "Sierra circular"]
    assert [r.row_number for r in rows] == [2, 3]


@pytest.mark.parametrize("header", ["Nombre", "DESCRIPCIÓN", "product", " Name "])
def test_accepts_header_aliases_ignoring_case_and_accents(tmp_path, header):
    f = make_xlsx(tmp_path / "in.xlsx", [[header], ["Taladro"]])
    assert read_products(f)[0].name == "Taladro"


def test_column_can_be_forced(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Código", "Detalle"], ["A1", "Taladro"]])
    assert read_products(f, column="Detalle")[0].name == "Taladro"


def test_missing_column_lists_what_was_found(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Código", "Detalle"], ["A1", "Taladro"]])
    with pytest.raises(InputError) as err:
        read_products(f)
    assert "Código" in str(err.value) and "Detalle" in str(err.value)
    assert "Producto" in str(err.value)


def test_duplicates_are_kept(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["Taladro"], ["Taladro"]])
    assert len(read_products(f)) == 2


def test_blank_rows_are_skipped_but_blank_product_in_a_used_row_is_kept(tmp_path):
    f = make_xlsx(
        tmp_path / "in.xlsx", [["Producto", "Cantidad"], [None, None], [None, 3], ["Taladro", 1]]
    )
    rows = read_products(f)
    assert [(r.name, r.quantity) for r in rows] == [("", 3.0), ("Taladro", 1.0)]


def test_header_may_follow_blank_rows(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [[None], [None], ["Producto"], ["Taladro"]])
    assert read_products(f)[0].name == "Taladro"


def test_numbers_in_product_cells_become_text(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], [12345]])
    assert read_products(f)[0].name == "12345"


def test_name_is_sanitized_but_original_is_preserved(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["  Taladro \n  percutor  "]])
    row = read_products(f)[0]
    assert row.name == "Taladro percutor"
    assert row.original == "  Taladro \n  percutor  "


def test_long_names_are_truncated_with_a_note(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["x" * 300]])
    row = read_products(f)[0]
    assert len(row.name) == 200
    assert any("recortado" in n for n in row.notes)


@pytest.mark.parametrize(
    ("cell", "expected"), [("2,5", 2.5), (3, 3.0), ("4", 4.0), ("abc", None), (-1, None), (0, None)]
)
def test_quantity_parsing(tmp_path, cell, expected):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto", "Cantidad"], ["Taladro", cell]])
    assert read_products(f)[0].quantity == expected


def test_extra_columns_are_ignored(tmp_path):
    f = make_xlsx(
        tmp_path / "in.xlsx", [["Producto", "Marca", "SKU"], ["Taladro", "Bosch", "GSB13"]]
    )
    row = read_products(f)[0]
    assert row.name == "Taladro"
    assert not hasattr(row, "brand") and not hasattr(row, "sku")


@pytest.mark.parametrize("cell", ["inf", "-inf", "nan", 1e308, 10_000_001, "1e400"])
def test_non_finite_or_absurd_quantities_are_ignored_with_a_note(tmp_path, cell):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto", "Cantidad"], ["Taladro", cell]])
    row = read_products(f)[0]
    assert row.quantity is None
    assert any("cantidad" in n for n in row.notes)


def test_quantity_upper_bound_is_inclusive(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto", "Cantidad"], ["Taladro", 10_000_000]])
    assert read_products(f)[0].quantity == 10_000_000


def test_unparseable_quantity_gets_a_note_but_blank_does_not(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto", "Cantidad"], ["A", "abc"], ["B", None]])
    a, b = read_products(f)
    assert any("cantidad" in n for n in a.notes)
    assert b.notes == ()


def test_max_rows_is_enforced_not_truncated_silently(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"]] + [[f"p{i}"] for i in range(11)])
    with pytest.raises(InputError, match="10"):
        read_products(f, max_rows=10)


def test_hard_cap_on_max_rows(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["a"]])
    with pytest.raises(InputError, match="2000"):
        read_products(f, max_rows=5000)


def test_sheet_selection_and_unknown_sheet(tmp_path):
    f = make_xlsx(
        tmp_path / "in.xlsx", [["Producto"], ["Taladro"]], sheet="Datos", extra_sheets=["Otra"]
    )
    assert read_products(f, sheet="Datos")[0].name == "Taladro"
    with pytest.raises(InputError) as err:
        read_products(f, sheet="Nada")
    assert "Datos" in str(err.value) and "Otra" in str(err.value)


def test_header_only_file_has_no_products(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"]])
    with pytest.raises(InputError, match="no hay productos"):
        read_products(f)


def test_empty_workbook(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [])
    with pytest.raises(InputError):
        read_products(f)


def test_missing_file(tmp_path):
    with pytest.raises(InputError, match="no existe"):
        read_products(tmp_path / "nada.xlsx")


@pytest.mark.parametrize("name", ["datos.xls", "datos.csv", "datos.txt"])
def test_unsupported_extensions(tmp_path, name):
    f = tmp_path / name
    f.write_bytes(b"x")
    with pytest.raises(InputError, match=r"\.xlsx"):
        read_products(f)


def test_excel_temp_lock_files_are_rejected_with_a_hint(tmp_path):
    f = tmp_path / "~$datos.xlsx"
    f.write_bytes(b"x")
    with pytest.raises(InputError, match="temporal"):
        read_products(f)


def test_corrupt_file(tmp_path):
    f = tmp_path / "roto.xlsx"
    f.write_bytes(b"esto no es un zip")
    with pytest.raises(InputError, match="no parece un .xlsx"):
        read_products(f)


def test_password_protected_file_is_detected(tmp_path):
    f = tmp_path / "cifrado.xlsx"
    f.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64)
    with pytest.raises(InputError, match="contraseña"):
        read_products(f)


def test_oversized_file_is_rejected(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["Taladro"]])
    with pytest.raises(InputError, match="MB"):
        read_products(f, max_bytes=100)


# --- Seguridad: el Excel de entrada es una entrada NO confiable ---------------------------------


def _rewrite_member(src, dst, member, data):
    import zipfile

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, data if item.filename == member else zin.read(item.filename))
    return dst


def test_sheet_with_broken_xml_is_a_friendly_error_not_a_traceback(tmp_path):
    good = make_xlsx(tmp_path / "ok.xlsx", [["Producto"], ["Taladro"]])
    bad = _rewrite_member(
        good, tmp_path / "bad.xlsx", "xl/worksheets/sheet1.xml", b"<worksheet><sheetData><row>"
    )
    with pytest.raises(InputError, match="no parece un .xlsx"):
        read_products(bad)


def test_workbook_with_broken_xml_is_a_friendly_error(tmp_path):
    good = make_xlsx(tmp_path / "ok.xlsx", [["Producto"], ["Taladro"]])
    bad = _rewrite_member(good, tmp_path / "bad.xlsx", "xl/workbook.xml", b"esto no es xml")
    with pytest.raises(InputError, match="no parece un .xlsx"):
        read_products(bad)


def test_nested_xml_entities_are_rejected_not_expanded(tmp_path):
    """«Billion laughs»: 10 caracteres se expandían a 1.000.000 sin `defusedxml`."""
    good = make_xlsx(tmp_path / "ok.xlsx", [["Producto"], ["Taladro"]])
    ents = "".join(
        f'<!ENTITY e{i} "{f"&e{i - 1};" * 10 if i else "AAAAAAAAAA"}">' for i in range(6)
    )
    sheet = (
        f'<?xml version="1.0"?><!DOCTYPE w [{ents}]>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>Producto</t></is></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>&e5;</t></is></c></row></sheetData></worksheet>'
    ).encode()
    bad = _rewrite_member(good, tmp_path / "bomba.xlsx", "xl/worksheets/sheet1.xml", sheet)
    with pytest.raises(InputError):
        read_products(bad)


def _declared(text: str) -> set[str]:
    """Nombres de paquete (en minúsculas) de las líneas de un requirements o de pyproject."""
    names = re.findall(r'^\s*"?([A-Za-z0-9_.-]+)\s*(?:[<>=~!\[;]|"|,|$)', text, re.M)
    return {n.lower() for n in names}


def test_defusedxml_is_a_declared_runtime_dependency():
    """Sin él, openpyxl no bloquea bombas de entidades (el venv de desarrollo lo trae)."""
    root = Path(__file__).resolve().parents[2]
    assert "defusedxml" in _declared((root / "requirements.txt").read_text(encoding="utf-8"))
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"defusedxml' in pyproject


def test_zip_with_absurd_uncompressed_size_is_rejected(tmp_path):
    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["Taladro"]])
    with pytest.raises(InputError, match="descomprimido"):
        read_products(f, max_uncompressed_bytes=10)


def test_zip_with_too_many_entries_is_rejected(tmp_path):
    import zipfile

    f = make_xlsx(tmp_path / "in.xlsx", [["Producto"], ["Taladro"]])
    with zipfile.ZipFile(f, "a") as z:
        for i in range(1100):
            z.writestr(f"relleno/{i}.txt", b"x")
    with pytest.raises(InputError, match="archivos internos"):
        read_products(f)
