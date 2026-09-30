"""Coincidencia entre lo que se busca y lo que la tienda publica.

El puntaje mezcla dos señales:

- **Cobertura de palabras**: qué fracción de las palabras de la consulta aparece en el título
  (con plurales y errores de tipeo en palabras largas). Es la señal dominante porque la similitud
  de texto por sí sola «satura» cuando una consulta corta queda contenida en un título largo:
  «Computador all in one 24 pulgadas» coincidía 85 % con «Repuesto de sierra de 24 pulgadas».
- **Similitud de texto** (`rapidfuzz.WRatio`), que ordena entre candidatos con igual cobertura.

Después se penalizan las especificaciones (modelo, medida, capacidad) que el título no trae.
Los pesos se calibraron con casos reales de bicicletas, computadores y zapatos.
"""

from __future__ import annotations

import os
import re

from rapidfuzz import fuzz

from price_comparator.comparison.query_cleaner import _UNIT_PREFIX
from price_comparator.comparison.text import strip_accents

_COVERAGE_WEIGHT = 0.75
_COVERAGE_EXPONENT = 1.5  # castiga más las palabras que faltan: 2 de 3 no es «casi todo»
_LOOKALIKE_MIN_LEN = 5
_LOOKALIKE_MIN_RATIO = 80  # «iphone» vs «hiphone»: casi igual, pero no es la misma marca
_ROOT_MIN_LEN = 7  # raíz común en palabras largas: ciclista ~ ciclismo, computador ~ computadora

# Penalización por especificaciones de la consulta (modelo, medida, capacidad) ausentes en el
# título: proporcional a las que faltan, más un castigo fijo si falta alguna. Con esto un TV de
# 50" no pasa por uno de 55" ni un taladro sin «750W» por uno de 750W.
_SPEC_PENALTY_PER_MISSING = 0.4
_SPEC_PENALTY_ANY_MISSING = 0.15

_UNIT_CANON = {
    **{u: u for u in ("mm", "cm", "w", "v", "kw", "gb", "tb", "mb", "ah", "hz", "ml", "oz", "kg")},
    **dict.fromkeys(("pulgadas", "pulgada", "in"), "in"),
    **dict.fromkeys(("litros", "litro", "lts", "lt", "l"), "l"),
    **dict.fromkeys(("metros", "metro", "mts", "mt", "m"), "m"),
    **dict.fromkeys(("galones", "galon", "gln", "gl"), "gl"),
    **dict.fromkeys(("gramos", "grs", "gr", "g"), "g"),
    **dict.fromkeys(("kilos", "kilo"), "kg"),
}
_UNIT_RE = re.compile(r"(\d)\s*(" + "|".join(sorted(_UNIT_CANON, key=len, reverse=True)) + r")\b")
_INCH_MARK = re.compile(r"(\d)\s*(?:\"|”|″|'')")
_DIMENSION = re.compile(r"(\d)\s*[x\u00d7]\s*(?=\d)")  # 3 x 2.5 = 3x2.5 = 3\u00d72.5
_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {"de", "del", "la", "el", "los", "las", "un", "una", "uno", "y", "o", "e", "con", "sin"}
    | {"para", "por", "en", "a", "the", "and"}
)


def _normalize(text: str) -> str:
    """Minúsculas, sin tildes y unidades canónicas (`55 pulgadas` = `55"` = `55in`)."""
    text = strip_accents(text).lower()
    text = _INCH_MARK.sub(r"\1in ", text)
    text = _UNIT_RE.sub(lambda m: m.group(1) + _UNIT_CANON[m.group(2)], text)
    text = _DIMENSION.sub(r"\1x", text)
    return re.sub(r"\s+", " ", text).strip()


def _spec_tokens(text: str) -> set[str]:
    """Tokens que identifican modelo, medida o capacidad: los que llevan algún dígito."""
    return {t for t in _TOKEN.findall(text) if any(c.isdigit() for c in t)}


def _forms(token: str) -> frozenset[str]:
    """La palabra y sus posibles singulares: botas -> bota, percutores -> percutor."""
    forms = {token}
    if len(token) > 3 and token.endswith("s"):
        forms.add(token[:-1])
        if len(token) > 4 and token.endswith("es"):
            forms.add(token[:-2])
    return frozenset(forms)


# Ejes donde dos valores se excluyen: pedir «hombre» y recibir «mujer» es otro producto.
# Se compara sobre formas ya normalizadas (sin tildes ni plural): niño -> nino, niñas -> nina.
_EXCLUSIVE_AXES: tuple[tuple[frozenset[str], ...], ...] = (
    (
        frozenset({"hombre", "caballero", "varon", "masculino"}),
        frozenset({"mujer", "dama", "femenino"}),
    ),
    (frozenset({"nino"}), frozenset({"nina"})),
    (frozenset({"adulto"}), frozenset({"nino", "nina", "bebe", "infantil"})),
)
_AXIS_WORDS = frozenset().union(*(group for axis in _EXCLUSIVE_AXES for group in axis))
_CONTRADICTION_FACTOR = 0.5

# Condición: quien busca «iPhone 16 Pro Max» espera uno NUEVO; un «Reacondicionado» es otro producto
# (y otro precio). Solo se acepta si la consulta lo pide.
_USED_WORDS = frozenset(
    {"reacondicionado", "usado", "seminuevo", "refurbished", "renovado", "reacondicionados"}
)
# Variantes de un mismo modelo: «Pro» ≠ «Pro Max», «S25» ≠ «S25 Ultra». Si la consulta pide una y el
# título no la trae, es otro producto. (La inversa no se castiga: «Pro-Bike» en un casco es ruido.)
_VARIANT_WORDS = frozenset({"max", "plus", "mini", "ultra", "lite", "pro"})
_CONDITION_FACTOR = 0.5
# Accesorios: «Carcasa … iPhone 17 Pro Max» trae todas las palabras del celular pero es otro
# producto. Solo palabras inequívocas (no «cable» ni «cargador», que sí vienen en las cajas).
_ACCESSORY_WORDS = frozenset(
    {"carcasa", "funda", "mica", "lamina", "hidrogel", "case", "repuesto", "protector"}
)


def _axis_hits(words: set[str], axis: tuple[frozenset[str], ...]) -> set[int]:
    return {i for i, group in enumerate(axis) if any(_forms(w) & group for w in words)}


def _contradicts(query_words: set[str], title_words: set[str]) -> bool:
    """¿Consulta y título piden valores opuestos en algún eje (género, edad)?"""
    if "unisex" in title_words:
        return False
    for axis in _EXCLUSIVE_AXES:
        wanted, offered = _axis_hits(query_words, axis), _axis_hits(title_words, axis)
        if wanted and offered and not wanted & offered:
            return True
    return False


def _has(words: set[str], vocabulary: frozenset[str]) -> bool:
    return any(_forms(w) & vocabulary for w in words)


def _missing_variant(query_words: set[str], title_words: set[str]) -> bool:
    return bool({w for w in query_words if w in _VARIANT_WORDS} - title_words)


def _has_lookalike(words: list[str], title_forms: set[str], title_words: set[str]) -> bool:
    """¿Falta una palabra de la consulta pero hay otra casi idéntica en el título (imitación)?"""
    for word in words:
        if len(word) < _LOOKALIKE_MIN_LEN or any(c.isdigit() for c in word):
            continue
        if _word_found(word, title_forms, title_words):
            continue
        if any(
            len(t) >= _LOOKALIKE_MIN_LEN and fuzz.ratio(word, t) >= _LOOKALIKE_MIN_RATIO
            for t in title_words
        ):
            return True
    return False


def _query_words(query: str) -> list[str]:
    """Palabras que cuentan para la cobertura: sin conectores ni palabras de género/edad.

    Las de género/edad no suman cobertura porque los títulos suelen omitirlas; solo restan si hay
    una contradicción explícita (ver `_contradicts`).
    """
    words = []
    for token in _TOKEN.findall(query):
        if token in _STOPWORDS or (len(token) < 2 and not token.isdigit()):
            continue
        if any(_forms(token) & _AXIS_WORDS):
            continue
        words.append(token)
    return words


def _same_family(a: str, b: str) -> bool:
    """Misma raíz larga («ciclista» ~ «ciclismo», «computador» ~ «computadora»)."""
    root = len(os.path.commonprefix([a, b]))
    return min(len(a), len(b)) >= _ROOT_MIN_LEN and root >= max(5, len(a) - 3)


def _word_found(word: str, title_forms: set[str], title_words: set[str]) -> bool:
    if _forms(word) & title_forms:
        return True
    if len(word) < _ROOT_MIN_LEN or any(c.isdigit() for c in word):
        return False  # números y palabras cortas deben coincidir exactamente
    return any(_same_family(word, t) for t in title_words)


def score(query: str, title: str) -> float:
    """Puntúa de 0 a 1 qué tan bien `title` corresponde a `query`.

    Insensible a tildes, mayúsculas, orden de palabras, plurales y alias de unidades. Sin ninguna
    palabra en común el puntaje no supera ~0,25; una contradicción explícita de género o edad
    (niño/niña, hombre/mujer, adulto/infantil) lo reduce a la mitad.
    """
    if not query.strip() or not title.strip():
        return 0.0

    query = _UNIT_PREFIX.sub("", query)  # «2 UN Switch» -> «Switch»
    q, t = _normalize(query), _normalize(title)
    if not q or not t:
        return 0.0

    similarity: float = fuzz.WRatio(q, t) / 100.0
    words = _query_words(q)
    title_words = set(_TOKEN.findall(t))
    title_forms: set[str] = set().union(*(_forms(w) for w in title_words))
    if words:
        coverage = sum(_word_found(w, title_forms, title_words) for w in words) / len(words)
        result: float = (
            _COVERAGE_WEIGHT * coverage**_COVERAGE_EXPONENT + (1 - _COVERAGE_WEIGHT) * similarity
        )
    else:
        result = similarity

    specs = _spec_tokens(q)
    if specs:
        missing = len(specs - _spec_tokens(t)) / len(specs)
        if missing:
            result *= 1.0 - _SPEC_PENALTY_PER_MISSING * missing - _SPEC_PENALTY_ANY_MISSING
    query_words = set(_TOKEN.findall(q))
    if _contradicts(query_words, title_words):
        result *= _CONTRADICTION_FACTOR
    if _has(title_words, _USED_WORDS) and not _has(query_words, _USED_WORDS):
        result *= _CONDITION_FACTOR
    if _missing_variant(query_words, title_words):
        result *= _CONDITION_FACTOR
    if _has(title_words, _ACCESSORY_WORDS) and not _has(query_words, _ACCESSORY_WORDS):
        result *= _CONDITION_FACTOR
    if words and _has_lookalike(words, title_forms, title_words):
        result *= _CONDITION_FACTOR
    return round(max(0.0, min(1.0, result)), 4)
