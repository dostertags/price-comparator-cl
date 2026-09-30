"""Normalización de texto."""

from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def strip_accents(text: str) -> str:
    """Quita tildes y diacríticos (`ñ` -> `n`)."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def normalize_name(value: object, max_len: int = 200) -> str:
    """Deja un nombre de producto listo para buscar: NFC, sin control, espacios colapsados.

    Args:
        value: cualquier cosa que venga de una celda; `None` da cadena vacía.
        max_len: largo máximo; recorta si se excede.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = _CONTROL.sub("", text)
    text = _WS.sub(" ", text).strip()
    return text[:max_len].strip()


def fix_mojibake(text: str) -> str:
    """Repara texto UTF-8 que alguien leyó como Latin-1/cp1252 (`CosmÃ©tica` -> `Cosmética`).

    Solo actúa si el texto tiene marcas típicas (`Ã`, `Â`) y la reparación es posible; si no,
    lo devuelve intacto.
    """
    if "Ã" not in text and "Â" not in text:
        return text
    for encoding in ("latin-1", "cp1252"):
        try:
            fixed = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        return fixed
    return text
