import os
from dataclasses import dataclass, field
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

ENV_FILE = Path(".env")


def load_env(path: Path = ENV_FILE) -> None:
    """Подгружает KEY=VALUE из .env в os.environ (уже заданные не перезаписывает)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _api_key() -> str | None:
    load_env()
    return os.getenv("EXCHANGERATE_API_KEY")


def _setting(key: str):
    return lambda: SettingsLoader().get(key)


@dataclass
class ParserConfig:
    """Параметры Parser Service."""

    EXCHANGERATE_API_KEY: str | None = field(default_factory=_api_key)

    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    BASE_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple = ("BTC", "ETH", "SOL")
    CRYPTO_ID_MAP: dict = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    RATES_FILE_PATH: str = field(default_factory=_setting("RATES_FILE"))
    HISTORY_FILE_PATH: str = field(default_factory=_setting("HISTORY_FILE"))

    REQUEST_TIMEOUT: int = 10
    UPDATE_INTERVAL_SECONDS: int = 300
