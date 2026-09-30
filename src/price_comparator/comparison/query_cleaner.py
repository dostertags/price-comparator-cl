"""Genera consultas más simples para reintentar productos sin coincidencia.

Estrategia (en orden; cada paso solo aporta una consulta si difiere de las anteriores):
  1. Quitar prefijo de cantidad+unidad ("2 UN Switch…" -> "Switch…").
  2. Quitar entero inicial sin unidad ("1 PVC…" -> "PVC…").
  3. Quitar paréntesis (cerrados o sin cerrar).
  4. Quitar todo lo que sigue a " / ".
  5. Quitar todo desde la primera coma separadora (no decimal).
  6. Truncar a los primeros 6, 4 y 3 tokens.
  7. Último recurso: solo la primera palabra.
"""

import re

# Leading "2 UN", "10 KG", "3.5 ML", etc.
_UNIT_PREFIX = re.compile(
    r"^\s*\d+[\.,]?\d*\s*"
    r"(un|und|unid|unidad|unidades|kg|gr|g|mg|lt|lts|l|ml|m|mt|mts|cm|mm"
    r"|pcs|pza|pz|cj|caja|cajas|par|rollo|rollos|gl|gln|set|sets|pack)\b\s*",
    re.IGNORECASE,
)
# Bare leading integer NOT followed by a unit (e.g. "1 PVC …")
_BARE_LEADING_INT = re.compile(r"^\s*\d+\s+")

# Closed parens: "(…)"
_CLOSED_PARENS = re.compile(r"\([^)]*\)")
# Unclosed paren to end of string: "(…<no close>"
_UNCLOSED_PAREN = re.compile(r"\s*\([^)]*$")

# Hard " / " or " // " separator (spaces required on both sides) — take only the left side
# This avoids splitting fractions (1/8", P/PLASMA) and product codes (ROJ/BL)
_SLASH_SEP = re.compile(r"\s+//?\s+.*$")

# Comma that is a list separator — not a decimal comma (i.e., NOT between digits)
_LIST_COMMA = re.compile(r"(?<!\d),(?!\d).*$")

_WHITESPACE = re.compile(r"\s+")


def _normalise(s: str) -> str:
    return _WHITESPACE.sub(" ", s).strip()


def generate_fallback_queries(name: str) -> list[str]:
    """Devuelve consultas más simples para reintentar cuando `name` no tuvo coincidencia confiable.

    Va de la simplificación más leve a la más agresiva; quien llama debe detenerse en el primer
    acierto. Ver el docstring del módulo para los pasos.

    Args:
        name: nombre original del producto.

    Returns:
        Lista ordenada y sin duplicados; vacía si no hay una simplificación razonable (por
        ejemplo, un código de pieza sin ninguna palabra legible).
    """
    candidates: list[str] = []
    seen = {name.lower().strip()}

    def _add(s: str) -> str:
        s = _normalise(s)
        if s and s.lower() not in seen and len(s) >= 3:
            seen.add(s.lower())
            candidates.append(s)
        return s

    # 1. Strip leading quantity+unit  ("2 UN Switch …" → "Switch …")
    step1 = _add(_UNIT_PREFIX.sub("", name))

    # 2. Strip bare leading integer when unit-strip didn't fire
    #    ("1 PVC Coupling …" → "PVC Coupling …")
    base2 = step1 if step1 else name
    step2 = base2
    if _BARE_LEADING_INT.match(base2):
        step2 = _add(_BARE_LEADING_INT.sub("", base2))
    if not step2:
        step2 = base2

    # 3. Strip unclosed paren then closed parens
    base3 = step2
    # unclosed first (avoids regex leaving a dangling open-paren fragment)
    after_unclosed = _UNCLOSED_PAREN.sub("", base3)
    step3a = _add(after_unclosed)
    base3b = step3a if step3a else after_unclosed
    step3 = _add(_CLOSED_PARENS.sub("", base3b))
    if not step3:
        step3 = base3b

    # 4. Split at hard " / " separator — keep only left side
    base4 = step3
    step4 = _add(_SLASH_SEP.sub("", base4))
    if not step4:
        step4 = base4

    # 5. Strip after list-separator comma (guards decimal commas like "2,50 KG")
    base5 = step4
    step5 = _add(_LIST_COMMA.sub("", base5))
    if not step5:
        step5 = base5

    # 6. Progressive token truncation (6 → 4 → 3 tokens)
    base6 = step5
    tokens = base6.split()
    for limit in (6, 4, 3):
        if len(tokens) > limit:
            _add(" ".join(tokens[:limit]))

    # 7. Last resort: first word only, when the name is very short and
    #    nothing above produced a candidate (catches "Rodamiento 22-40-7" → "Rodamiento")
    if not candidates:
        first_word = name.strip().split()[0] if name.strip() else ""
        if len(first_word) >= 4 and re.search(r"[A-Za-z]", first_word):
            _add(first_word)

    return candidates


def strip_noise(name: str) -> str:
    """Devuelve `name` sin cantidad+unidad inicial ni paréntesis: lo que no describe al producto.

    Sirve de referencia para puntuar las coincidencias: un código de pieza entre paréntesis no
    debe hundir el puntaje de una oferta que sí corresponde. No quita un entero inicial suelto
    porque puede ser una medida («55 pulgadas TV»). Nunca devuelve una cadena vacía.
    """
    text = _UNIT_PREFIX.sub("", name)
    text = _UNCLOSED_PAREN.sub("", text)
    text = _CLOSED_PARENS.sub("", text)
    return _normalise(text) or _normalise(name)
