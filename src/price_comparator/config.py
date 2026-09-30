"""Configuración desde variables de entorno (prefijo `PC_`). No tiene efectos al importarse."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path

from price_comparator.scrapers.fetch import DEFAULT_USER_AGENT

_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
MAX_WORKERS = 8


class ConfigError(ValueError):
    """Un valor de configuración no es válido."""


def load_env_file(path: Path, environ: MutableMapping[str, str] | None = None) -> None:
    """Lee un `.env` sencillo (`CLAVE=valor`) sin pisar variables que ya existan."""
    env = os.environ if environ is None else environ
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        key = key.strip()
        if key.startswith("PC_"):  # un .env ajeno no puede tocar PATH, proxies, etc.
            env.setdefault(key, value)


def _number(
    env: MutableMapping[str, str] | dict[str, str], key: str, default: float, cast: type
) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)  # type: ignore[no-any-return]
    except ValueError as exc:
        raise ConfigError(f"{key} debe ser un número, recibí {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Parámetros de una corrida."""

    user_agent: str = DEFAULT_USER_AGENT
    timeout_s: float = 15.0
    max_retries: int = 3
    delay_min_s: float = 1.2
    delay_max_s: float = 3.0
    scraper_budget_s: float = 45.0
    max_offers_per_store: int = 15
    workers: int = 4
    min_score: float = 0.60
    price_min_clp: int = 500
    price_max_clp: int = 50_000_000
    mode: str = "http"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: MutableMapping[str, str] | dict[str, str] | None = None) -> Settings:
        """Construye y valida la configuración. Lanza `ConfigError` si algo no es válido."""
        env = os.environ if env is None else env
        d = cls()
        s = cls(
            user_agent=env.get("PC_USER_AGENT") or d.user_agent,
            timeout_s=_number(env, "PC_TIMEOUT_S", d.timeout_s, float),
            max_retries=int(_number(env, "PC_MAX_RETRIES", d.max_retries, int)),
            delay_min_s=_number(env, "PC_DELAY_MIN_S", d.delay_min_s, float),
            delay_max_s=_number(env, "PC_DELAY_MAX_S", d.delay_max_s, float),
            scraper_budget_s=_number(env, "PC_SCRAPER_BUDGET_S", d.scraper_budget_s, float),
            max_offers_per_store=int(
                _number(env, "PC_MAX_OFFERS_PER_STORE", d.max_offers_per_store, int)
            ),
            workers=int(_number(env, "PC_WORKERS", d.workers, int)),
            min_score=_number(env, "PC_MIN_SCORE", d.min_score, float),
            price_min_clp=int(_number(env, "PC_PRICE_MIN_CLP", d.price_min_clp, int)),
            price_max_clp=int(_number(env, "PC_PRICE_MAX_CLP", d.price_max_clp, int)),
            mode=(env.get("PC_MODE") or d.mode).strip().lower(),
            log_level=(env.get("PC_LOG_LEVEL") or d.log_level).strip().upper(),
        )
        s.validate()
        return s

    def validate(self) -> None:
        """Comprueba rangos y coherencia entre valores."""
        if any(ord(c) < 32 or ord(c) == 127 for c in self.user_agent):
            raise ConfigError("PC_USER_AGENT no puede llevar caracteres de control")
        if not 1 <= self.workers <= MAX_WORKERS:
            raise ConfigError(f"PC_WORKERS debe estar entre 1 y {MAX_WORKERS}")
        if not 0.0 <= self.min_score <= 1.0:
            raise ConfigError("PC_MIN_SCORE debe estar entre 0 y 1")
        if self.mode not in ("http", "headless"):
            raise ConfigError("PC_MODE debe ser 'http' o 'headless'")
        if self.delay_min_s < 0 or self.delay_min_s > self.delay_max_s:
            raise ConfigError("PC_DELAY_MIN_S no puede ser mayor que PC_DELAY_MAX_S")
        if not 0 < self.price_min_clp < self.price_max_clp:
            raise ConfigError("PC_PRICE_MIN_CLP debe ser positivo y menor que PC_PRICE_MAX_CLP")
        if self.log_level not in _LOG_LEVELS:
            raise ConfigError(f"PC_LOG_LEVEL debe ser uno de {', '.join(_LOG_LEVELS)}")
        if self.max_retries < 1 or self.timeout_s <= 0 or self.max_offers_per_store < 1:
            raise ConfigError(
                "PC_MAX_RETRIES, PC_TIMEOUT_S y PC_MAX_OFFERS_PER_STORE deben ser positivos"
            )
