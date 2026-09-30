"""Configuración de logging. Se llama desde la CLI; ningún módulo la ejecuta al importarse."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

HANDLER_NAME = "price_comparator_cli"
_FORMAT = "%(asctime)s [%(levelname)-7s] %(message)s"


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configura el logger `price_comparator` (idempotente; no toca el logger raíz)."""
    logger = logging.getLogger("price_comparator")
    for handler in list(logger.handlers):
        if handler.get_name() == HANDLER_NAME:
            logger.removeHandler(handler)

    reconfigure = getattr(sys.stderr, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")  # consolas de Windows que no soportan todo Unicode

    formatter = logging.Formatter(_FORMAT, datefmt="%H:%M:%S")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file is not None:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for handler in handlers:
        handler.set_name(HANDLER_NAME)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
