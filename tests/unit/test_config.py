import pytest

from price_comparator.config import ConfigError, Settings, load_env_file
from price_comparator.scrapers.falabella import FalabellaScraper
from price_comparator.scrapers.hites import HitesScraper
from price_comparator.scrapers.registry import build_scrapers
from price_comparator.scrapers.sodimac import SodimacScraper
from tests.fakes import FakeFetcher


def test_defaults():
    s = Settings.from_env({})
    assert s.workers == 4
    assert s.min_score == 0.60
    assert s.mode == "http"
    assert s.price_min_clp == 500
    assert s.max_retries == 3
    assert (s.delay_min_s, s.delay_max_s) == (1.2, 3.0)


def test_overrides_from_environment():
    s = Settings.from_env(
        {"PC_WORKERS": "2", "PC_MIN_SCORE": "0.7", "PC_MODE": "headless", "PC_LOG_LEVEL": "debug"}
    )
    assert (s.workers, s.min_score, s.mode, s.log_level) == (2, 0.7, "headless", "DEBUG")


@pytest.mark.parametrize(
    "env",
    [
        {"PC_WORKERS": "0"},
        {"PC_WORKERS": "99"},
        {"PC_WORKERS": "abc"},
        {"PC_MIN_SCORE": "1.5"},
        {"PC_MODE": "selenium"},
        {"PC_DELAY_MIN_S": "5", "PC_DELAY_MAX_S": "1"},
        {"PC_PRICE_MIN_CLP": "100", "PC_PRICE_MAX_CLP": "50"},
        {"PC_LOG_LEVEL": "LOUD"},
    ],
)
def test_invalid_values_raise_config_error(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_env_file_is_loaded_without_overriding_real_environment(tmp_path):
    f = tmp_path / ".env"
    f.write_text(
        "# comentario\nPC_WORKERS=3\n\nPC_MODE='http'\nPC_MIN_SCORE=\"0.8\"\nPC_LOG_LEVEL=INFO\n",
        encoding="utf-8",
    )
    env = {"PC_LOG_LEVEL": "ERROR"}
    load_env_file(f, env)
    assert env["PC_WORKERS"] == "3"
    assert env["PC_MODE"] == "http"
    assert env["PC_MIN_SCORE"] == "0.8"
    assert env["PC_LOG_LEVEL"] == "ERROR"


def test_missing_env_file_is_ignored(tmp_path):
    env: dict[str, str] = {}
    load_env_file(tmp_path / "nope.env", env)
    assert env == {}


def test_build_scrapers_creates_the_three_stores_in_order():
    made = []

    def factory(settings):
        fetcher = FakeFetcher()
        made.append(fetcher)
        return fetcher

    scrapers = build_scrapers(Settings.from_env({}), fetcher_factory=factory)
    assert [type(s) for s in scrapers] == [SodimacScraper, FalabellaScraper, HitesScraper]
    assert len(made) == 3  # un fetcher (sesión, semáforo) por tienda


@pytest.mark.parametrize("agent", ["Mozilla\r\nX-Injected: 1", "Bot\x00", "Bot\n"])
def test_user_agent_with_control_characters_is_rejected(agent):
    """Inyección de cabeceras HTTP a través de PC_USER_AGENT."""
    with pytest.raises(ConfigError, match="USER_AGENT"):
        Settings.from_env({"PC_USER_AGENT": agent})


def test_env_file_only_loads_pc_variables(tmp_path):
    f = tmp_path / ".env"
    f.write_text("PATH=/tmp/evil\nHTTPS_PROXY=http://evil:8080\nPC_WORKERS=2\n", encoding="utf-8")
    env: dict[str, str] = {}
    load_env_file(f, env)
    assert env == {"PC_WORKERS": "2"}


def test_default_offers_per_store_looks_deep_enough_to_reach_new_products():
    assert Settings.from_env({}).max_offers_per_store >= 15
