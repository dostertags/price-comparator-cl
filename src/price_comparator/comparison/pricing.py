"""Lectura de precios en formato chileno."""

from __future__ import annotations

import math
import re
from typing import Any

_NUMBER = re.compile(r"\d[\d.,]*")
_EXPONENT = re.compile(r"\d[eE][+-]?\d")
_THOUSANDS_DOT = re.compile(r"^\d{1,3}(\.\d{3})+$")
MAX_PRICE_DIGITS = 15  # cualquier cosa mayor no es un precio: es basura o un ataque


def parse_price(raw: Any) -> int | None:
    """Convierte un precio publicado a pesos enteros.

    Acepta `int`, `float`, `str` («$1.299.990», «12.990», «1299990.0», «59.990 c/u») o una
    lista (se usa el primer elemento). En CLP el punto separa miles y la coma los decimales.

    Returns:
        El precio como entero positivo, o `None` si no hay un precio válido.
    """
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else None
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        if not math.isfinite(raw) or not 0 < raw < 10**MAX_PRICE_DIGITS:
            return None
        return int(round(raw))
    if not isinstance(raw, str) or raw.strip().startswith("-"):
        return None

    if _EXPONENT.search(raw):
        return None  # notación científica: no es un precio publicado
    match = _NUMBER.search(raw)
    if not match:
        return None
    token = match.group().rstrip(".,")

    if "," in token:
        integer, _, _decimals = token.replace(".", "").partition(",")
        digits = integer
    elif _THOUSANDS_DOT.match(token):
        digits = token.replace(".", "")
    else:
        digits = token.split(".", 1)[0]

    if not digits.isdigit() or len(digits) > MAX_PRICE_DIGITS:
        return None  # sin int() de cadenas gigantes (en Python >= 3.11 lanza ValueError)
    value = int(digits)
    return value if value > 0 else None
