"""`generate_fallback_queries`: consultas más simples para la segunda pasada.

Solo transforma texto; no usa la red. Los nombres son ejemplos inventados con las mismas formas
que suelen fallar (cantidad inicial, paréntesis, separadores, códigos de pieza).
"""

import pytest

from price_comparator.comparison.query_cleaner import generate_fallback_queries as gen


def test_leading_quantity_and_unit_is_stripped_first():
    assert gen("2 UN Switch de pared blanco")[0] == "Switch de pared blanco"


@pytest.mark.parametrize("prefix", ["10 KG", "3.5 ML", "2 pack", "1 caja"])
def test_various_quantity_units_are_stripped(prefix):
    assert gen(f"{prefix} Pintura latex blanca")[0] == "Pintura latex blanca"


def test_bare_leading_integer_is_stripped_and_never_remains_first():
    candidates = gen("1 Cortina de baño azul")
    assert candidates[0] == "Cortina de baño azul"
    assert not candidates[0].startswith("1 ")


def test_unclosed_parenthesis_never_bleeds_into_candidates():
    candidates = gen("Taladro percutor 750W (marca Bosch")
    assert "Taladro percutor 750W" in candidates
    assert not any("(" in c for c in candidates)


def test_closed_parentheses_are_removed():
    assert "Martillo carpintero acero" in gen("Martillo carpintero (12 oz) acero")


def test_text_after_spaced_slash_is_dropped():
    assert "Pintura latex blanco" in gen("Pintura latex blanco / balde 4 galones")


def test_slash_without_spaces_is_not_a_separator():
    candidates = gen('Llave 1/8" acero inoxidable reforzada extra larga')
    assert not any(c in ("Llave 1", "Llave") for c in candidates[:2])
    assert any("1/8" in c for c in candidates)


def test_text_after_list_comma_is_dropped():
    assert "Guante nitrilo" in gen("Guante nitrilo, talla M, caja 100")


def test_decimal_comma_is_not_a_list_separator():
    candidates = gen("Cinta adhesiva 2,5 m transparente extra fuerte reforzada")
    assert not any(c.endswith("2") for c in candidates)


def test_long_names_are_truncated_progressively_to_6_4_and_3_tokens():
    candidates = gen("uno dos tres cuatro cinco seis siete ocho")
    assert candidates[-3:] == [
        "uno dos tres cuatro cinco seis",
        "uno dos tres cuatro",
        "uno dos tres",
    ]


def test_single_keyword_fallback_for_dimension_specs():
    assert gen("Rodamiento 22-40-7") == ["Rodamiento"]


def test_pure_part_code_has_no_fallback():
    assert gen("TYM-T-L3110-A") == []


@pytest.mark.parametrize("name", ["", "   ", "\n"])
def test_blank_input_gives_nothing(name):
    assert gen(name) == []


@pytest.mark.parametrize(
    "name",
    [
        "2 UN Switch de pared blanco (modelo X) / caja 10, color blanco",
        "1 Cortina de baño azul (poliéster",
        "Guante nitrilo, talla M, caja 100 unidades reforzado largo",
        'Llave 1/8" acero inoxidable reforzada extra larga',
    ],
)
def test_candidates_are_unique_short_enough_and_never_the_original(name):
    candidates = gen(name)
    assert candidates, "estos nombres sí tienen simplificación posible"
    assert len(candidates) == len({c.lower() for c in candidates})
    assert name.lower() not in [c.lower() for c in candidates]
    assert all(len(c) >= 3 for c in candidates)
    assert all(c == " ".join(c.split()) for c in candidates)  # espacios normalizados


def test_is_deterministic():
    name = "2 UN Switch de pared blanco (modelo X) / caja 10"
    assert gen(name) == gen(name)


# --- strip_noise: el nombre original sin el ruido que no describe al producto ------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("2 UN Switch de pared blanco", "Switch de pared blanco"),
        ("Taladro percutor 13mm (marca X) especial", "Taladro percutor 13mm especial"),
        ("Taladro percutor 750W (marca Bosch", "Taladro percutor 750W"),
        ("Martillo carpintero", "Martillo carpintero"),
        ("55 pulgadas TV Samsung", "55 pulgadas TV Samsung"),  # el 55 es la medida
    ],
)
def test_strip_noise_removes_quantity_and_parentheses_only(name, expected):
    from price_comparator.comparison.query_cleaner import strip_noise

    assert strip_noise(name) == expected


@pytest.mark.parametrize("name", ["(F 123) ", "  ", "(solo paréntesis)"])
def test_strip_noise_never_returns_an_empty_reference(name):
    from price_comparator.comparison.query_cleaner import strip_noise

    assert strip_noise(name) == " ".join(name.split())
