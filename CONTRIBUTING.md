# Contribuir

¡Gracias por querer ayudar! Es un proyecto chico; estas reglas lo mantienen sano.

## Preparar el entorno

```bash
git clone <tu-fork>
cd price-comparator-cl
python -m venv .venv
.venv/Scripts/activate        # Windows (Git Bash: source .venv/Scripts/activate)  ·  Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -e .
pre-commit install
```

## Flujo de trabajo

1. Crea una rama desde `main`.
2. **Escribe primero el test** y verifica que falla por la razón correcta (rojo), luego implementa (verde) y ordena (refactor).
3. Antes del PR, todo esto debe pasar:

```bash
ruff check . && ruff format --check .
mypy
pytest --cov=price_comparator      # exige >= 80 %
```

4. Abre el PR explicando *qué* y *por qué*. Un cambio por PR.

## Reportar un scraper roto

Los sitios cambian su HTML sin avisar. Si una tienda sale `layout_changed`, abre un issue con:
la versión, el log con `--verbose` y **una búsqueda de ejemplo**. No adjuntes tus Excels ni datos personales.
Si puedes, agrega un fixture nuevo en `tests/fixtures/html/` (solo el mínimo: sin cookies, sesiones ni datos de usuario).

## Reglas del repo

- Nada de credenciales, `.env`, Excels reales ni logs. `.env.example` solo lleva placeholders.
- Sin evasión de protecciones anti-bot: un User-Agent fijo, pausas y `blocked` cuando corresponde.
- Sin efectos al importar módulos (nada de abrir archivos ni configurar logging a nivel de módulo).
- Tests unitarios sin red (hay un guardia que la bloquea). Los que usan sitios reales llevan `@pytest.mark.live`.
