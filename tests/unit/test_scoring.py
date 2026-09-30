import pytest

from price_comparator.comparison.scoring import score


def test_identical_text_scores_near_one():
    assert score("Taladro percutor 750W", "Taladro percutor 750W") > 0.95


def test_word_order_does_not_hurt():
    assert score("percutor taladro 13mm", "Taladro percutor 13mm") > 0.9


def test_accents_and_case_are_ignored():
    assert score("bateria litio", "BATERÍA LITIO") > 0.95


def test_different_screen_size_is_penalized():
    same = score('Smart TV 55" Samsung', 'Smart TV 55" Samsung 4K')
    other = score('Smart TV 55" Samsung', 'Smart TV 65" Samsung 4K')
    assert other < same
    assert other < 0.75


def test_different_capacity_is_penalized():
    assert score("Notebook 256GB", "Notebook 512GB") < score("Notebook 256GB", "Notebook 256 GB")


def test_glued_and_spaced_units_are_equivalent():
    assert score("Taladro 13 mm 750 W", "Taladro 13mm 750W") > 0.9


def test_model_code_missing_in_title_is_penalized():
    assert score("Televisor 65UR8750", "Televisor LG 65 pulgadas") < 0.6


def test_leading_quantity_is_not_treated_as_a_spec():
    assert score("2 UN Switch pared", "Switch pared blanco") > 0.7


def test_empty_inputs_score_zero():
    assert score("", "Algo") == 0.0
    assert score("Algo", "") == 0.0


def test_score_is_bounded():
    assert 0.0 <= score("a b c", "x y z") <= 1.0


# --- Regresiones encontradas en la corrida real contra las tiendas -----------------------


def test_no_shared_word_never_reaches_the_default_threshold():
    """«Cosa» ~ «Casa» por fuzzy: sin ninguna palabra en común no puede pasar de 0,4."""
    assert score("Cosa inexistente zzqxkjwv", "Casa De Verano Verde") <= 0.4
    assert score("Cosa", "Casa De Verano Verde") <= 0.4


def test_plural_and_extra_words_still_match():
    assert score("Taladro percutor", "Taladros Percutores 13mm Bosch") > 0.6


def test_pulgadas_and_inch_mark_are_the_same_spec():
    with_mark = score("Televisor 55 pulgadas 4K", 'Smart TV LED 55" 4K Ultra HD')
    assert with_mark > 0.6


def test_wrong_screen_size_is_rejected_by_default_threshold():
    assert score("Televisor 55 pulgadas 4K", 'Smart TV LED 50 " 4K Ultra HD') < 0.6


def test_missing_power_spec_is_rejected_but_full_match_is_kept():
    query = "Taladro percutor 13 mm 750W"
    assert score(query, "Taladro Percutor Atornillador 13mm Sin Batería") < 0.6
    assert score(query, "Bosch Taladro percutor eléctrico 13 mm 750W GSB 13 RE") > 0.85


def test_unit_aliases_are_canonical():
    assert score("Pintura 1 galón", "Pintura 1 gl") > 0.85
    assert score("Manguera 20 metros", "Manguera 20 mts") > 0.85
    assert score("Aceite 5 litros", "Aceite 5 lts") > 0.85


@pytest.mark.parametrize(
    ("query", "title"),
    [
        ("Cable 3 x 2.5 mm", "Cable 3x2.5mm THHN"),
        ("Cable 3x2.5mm", "Cable 3 x 2.5 mm THHN"),
        ("Vidrio 100 x 50 cm", "Vidrio 100x50 cm"),
        ("Tabla pino 2 X 4", "Tabla pino 2x4"),
        ("Tabla pino 2x4", "Tabla pino 2\u00d74 cepillada"),
    ],
)
def test_dimension_spacing_does_not_change_the_match(query, title):
    assert score(query, title) > 0.85


def test_different_dimensions_are_still_penalized():
    assert score("Cable 3 x 2.5 mm", "Cable 3x1.5mm THHN") < 0.6
    assert score("Tabla pino 2x4", "Tabla pino 2x6") < 0.6


# --- Corpus de casos reales (auditoría en vivo: bicicletas, computadores y zapatos) -----------

REAL_MATCHES = [
    ("Bicicleta infantil aro 16 niña", "Bicicleta Infantil Plegable Aro 16 Color Rosado"),
    ("Casco ciclista adulto", "Casco Deportivo Sport Ciclismo Ajustable Unisex Adulto"),
    ("Candado bicicleta U-lock", "Candado Bicicleta U Lock Bike K1800 18x186mm Llave Disco"),
    (
        "Notebook HP 15 Intel Core i5 16GB 512GB",
        'HP Notebook 15,6" HP 15-FD0059LA / Intel Core I5 / 16 GB RAM / 512 GB',
    ),
    ("Monitor 27 pulgadas 144Hz", 'Monitor PRO MP271 E14A 27" IPS 144hz FHD'),
    (
        "Monitor 27 pulgadas 144Hz",
        "Monitor A27i 2026 de 27 Pulgadas Full HD IPS 144Hz HDMI DisplayPort",
    ),
    ("Mouse inalámbrico Logitech", "Logitech Mouse Inalámbrico Logitech M185"),
    ("Teclado mecánico gamer", "Teclado Gamer NovaBlade TKL Red Switch Mecánico ESP RGB"),
    ("Zapatilla Adidas Ultraboost", "ADIDAS Zapatillas Ultraboost 5"),
    ("Martillo carpintero", "Martillo carpintero 12 Oz acero"),
    ("Pintura látex blanco 1 galón", "Pintura látex blanco 1 gl"),
    ("Sandalias mujer playa", "Sandalias Antideslizantes Playa Verano Mujer Hawaiana Chalas"),
    ("Zapatos de seguridad punta de acero talla 41", "Zapato de Seguridad Unisex Talla 41 108C"),
]
REAL_MISMATCHES = [
    (
        "Computador all in one 24 pulgadas",
        "Repuesto de sierra para jardín 24 pulgadas de acero Cobre",
    ),
    ("Computador all in one 24 pulgadas", "Machete 24 pulgadas"),
    ("Botas de trabajo cuero", "Pechera de cuero para parrilla café"),
    ("Botas de trabajo cuero", "Zapato de trabajo N° 41"),
    ("Candado bicicleta U-lock", "Candado Cuadrado 80mm Seguridad Blindado Color Plateado"),
    ("Zapatos escolares negros niño talla 34", "Zapato Escolar Niña Cuero Negro (34 a 39)"),
    ("Zapatillas running hombre Nike talla 42", "Zueco Hombre Talla 42 Riverbound Sr"),
    ("Bicicleta ruta aro 700 Shimano", "Bicicleta madera rojo Riders aro 12"),
    ("PC gamer RTX 4060 Ryzen 5", "Audífonos Gamer Profesional Kotion Rojo G4000 Ps4 Xbox Pc"),
    ("Televisor 55 pulgadas 4K", 'Smart TV LED 50 " 4K Ultra HD'),
    ("Bicicleta eléctrica plegable 250W", "Scooter Electrico Plegable Digital 25 km.500w"),
]


@pytest.mark.parametrize(("query", "title"), REAL_MATCHES)
def test_real_world_true_matches_reach_the_default_threshold(query, title):
    assert score(query, title) >= 0.6


@pytest.mark.parametrize(("query", "title"), REAL_MISMATCHES)
def test_real_world_false_positives_stay_below_the_default_threshold(query, title):
    assert score(query, title) < 0.6


def test_the_distinguishing_model_word_outranks_a_same_brand_generic_match():
    query = "Zapatilla Adidas Ultraboost"
    right = score(query, "ADIDAS Zapatillas Ultraboost 5")
    wrong = score(query, "ADIDAS Zapatilla Adidas Hoops Mid Classic Hombre Blanco")
    assert right - wrong >= 0.10


def test_gender_or_age_contradiction_is_not_a_match():
    assert score("Zapatos escolares negros niño", "Zapato Escolar Niña Cuero Negro") < 0.6


def test_plural_forms_are_matched_word_by_word():
    assert score("Botas de trabajo", "Bota de trabajo reforzada") >= 0.85
    assert score("Zapatillas", "Zapatilla") >= 0.85


def test_a_lookalike_brand_is_a_counterfeit_signal_not_a_match():
    """Regresión real: «iPhone 17 Pro Max» ganaba con un «Hotwav Hiphone 17 Pro Max» de $199.990."""
    query = "iPhone 17 Pro Max 256GB"
    fake = score(query, "Hotwav Hiphone 17 Pro Max 4g Celular 16gb 256gb 120hz")
    real = score(query, "Apple iPhone 17 Pro Max 5G 256 GB Naranjo Liberado")
    assert fake < 0.6
    assert real >= 0.85


def test_typos_are_not_forgiven_by_fuzzy_matching_anymore():
    assert score("Bicicleta mountain", "Bicicleta Monuntain aro 29") < 0.6


@pytest.mark.xfail(
    strict=True,
    reason="Limitación conocida: «Ryzen 5» y «Ryzen 3» puntúan igual por texto.",
)
def test_known_limitation_neighbouring_cpu_models_are_not_told_apart():
    query = "Notebook Lenovo IdeaPad 15 Ryzen 5 8GB 512GB"
    right = score(query, "Lenovo Notebook IdeaPad Slim 3 8va Gen AMD Ryzen 5 8GB RAM 512GB SSD")
    wrong = score(query, 'Lenovo Notebook Ideapad Slim 3 AMD Ryzen 3 7320U 8GB 512GB SSD 15,6" FHD')
    assert right - wrong >= 0.10


# --- Contradicciones de género / edad (niño vs niña, hombre vs mujer, adulto vs infantil) -------


@pytest.mark.parametrize(
    ("query", "title"),
    [
        ("Zapatillas running hombre Nike", "Zapatilla Nike Running Mujer Blanca"),
        ("Zapatos escolares niño", "Zapato Escolar Niña Cuero Negro"),
        ("Casco ciclista adulto", "Casco Ciclista Infantil Ajustable"),
        ("Polera mujer algodón", "Polera Hombre Algodón"),
    ],
)
def test_explicit_gender_or_age_contradiction_halves_the_score(query, title):
    same_title = title
    for a, b in (
        ("Mujer", "hombre"),
        ("Niña", "niño"),
        ("Infantil", "adulto"),
        ("Hombre", "mujer"),
    ):
        same_title = same_title.replace(a, b)
    assert score(query, title) < score(query, same_title) * 0.6
    assert score(query, title) < 0.6


def test_unisex_or_missing_gender_in_the_title_is_not_a_contradiction():
    assert score("Zapatillas hombre Nike", "Zapatilla Nike Unisex") >= 0.6
    assert score("Zapatillas hombre Nike", "Zapatilla Nike Running") >= 0.6


def test_same_gender_with_different_wording_is_not_a_contradiction():
    assert score("Zapato niña escolar", "Zapato Escolar Niñas Negro") >= 0.6
    assert score("Zapatilla caballero Nike", "Zapatilla Nike Hombre") >= 0.6


# --- Condición (nuevo vs reacondicionado) y variantes (Pro vs Pro Max), auditoría iPhone ---


def test_refurbished_is_not_a_match_for_a_plain_search():
    """Regresión real: «iPhone 16 Pro Max» devolvía como mejor precio uno Reacondicionado."""
    query = "iPhone 16 Pro Max 256GB"
    assert score(query, "IPhone 16 Pro Max 256GB Reacondicionado Excelente") < 0.6
    assert score(query, "Apple iPhone 16 Pro Max 256GB Usado") < 0.6
    assert score(query, "Apple iPhone 16 Pro Max 256GB Titanio Negro") >= 0.85


def test_asking_for_refurbished_explicitly_is_allowed():
    assert (
        score("iPhone 16 Pro Max reacondicionado", "iPhone 16 Pro Max Reacondicionado 256GB") >= 0.6
    )


def test_missing_variant_word_is_a_different_product():
    """Regresión real: «iPhone 16 Pro Max 1TB» ganaba con un «iPhone 16 Pro 1TB»."""
    assert score("iPhone 16 Pro Max 1TB", "IPhone 16 Pro 1TB Blanco") < 0.6
    assert score("Galaxy S25 Ultra 256GB", "Samsung Galaxy S25 256GB") < 0.6
    assert score("Galaxy S25 Ultra 256GB", "Samsung Galaxy S25 Ultra 256GB Negro") >= 0.85


def test_a_variant_word_only_in_the_title_is_not_penalized():
    assert score("Casco bicicleta", "Casco De Bicicleta Pro-Bike USA Con Luz") >= 0.85


# --- Accesorios: «iPhone 17 Pro Max» devolvía una carcasa de $27.990 con 97 % de confianza -------


def test_an_accessory_for_the_product_is_not_the_product():
    query = "iPhone 17 Pro Max"
    assert score(query, "Para Iphone 17 Pro Max - Carcasa Magsafe Con Soporte") < 0.6
    assert score(query, "Lámina Protectora De Hidrogel Iphone 17 Pro Max") < 0.6
    assert score(query, "Mica Antigolpe Iphone 17 Pro Max") < 0.6
    assert score(query, "IPhone 17 Pro Max") >= 0.85


def test_asking_for_the_accessory_is_allowed():
    assert score("funda iPhone 17 Pro Max", "Funda Silicona iPhone 17 Pro Max Negro") >= 0.85
    assert score("repuesto sierra circular", "Repuesto Hoja Sierra Circular 7 1/4") >= 0.6


def test_words_like_case_or_charger_in_a_real_product_title_are_not_penalized():
    assert score("Taladro percutor", "Taladro percutor con estuche") >= 0.85
    assert score("Notebook 15", "Notebook 15 con cargador") >= 0.85
