import math
from datetime import datetime, timezone

from valutatrade_hub.core.currencies import CryptoCurrency, get_currency

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CRYPTO_DECIMALS = 4
FIAT_DECIMALS = 2
AMOUNT_ERROR = "'amount' должен быть положительным числом"

# Стоимость 1 единицы валюты в USD (заглушка до подключения Parser Service)
EXCHANGE_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0786,
    "GBP": 1.2358,
    "RUB": 0.01016,
    "BTC": 59337.21,
    "ETH": 3720.0,
    "SOL": 145.12,
}


def convert(
    amount: float,
    from_code: str,
    to_code: str,
    rates: dict[str, float] = EXCHANGE_RATES,
) -> float:
    """Конвертирует сумму из одной валюты в другую через USD."""
    try:
        return amount * rates[from_code] / rates[to_code]
    except KeyError as exc:
        raise ValueError(f"Нет курса для '{exc.args[0]}'") from None


# ---------- время ----------
def utc_now_iso() -> str:
    """Текущее время UTC в формате 2025-10-09T12:00:00Z."""
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def age_seconds(timestamp: str) -> float:
    """Сколько секунд прошло с момента timestamp."""
    moment = datetime.strptime(timestamp, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds()


# ---------- валидация ----------
def normalize_code(code: str) -> str:
    """Приводит код к верхнему регистру и проверяет его по реестру валют."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Код валюты не может быть пустым")
    return get_currency(code.strip().upper()).code


def validate_amount(amount: object) -> float:
    """Сумма должна быть конечным числом больше нуля."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise ValueError(AMOUNT_ERROR) from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(AMOUNT_ERROR)
    return value


# ---------- форматирование ----------
def format_balance(code: str, value: float) -> str:
    """Баланс: 4 знака для крипты, 2 для фиата."""
    is_crypto = isinstance(get_currency(code), CryptoCurrency)
    return f"{value:.{CRYPTO_DECIMALS if is_crypto else FIAT_DECIMALS}f}"


def format_rate(rate: float) -> str:
    """Курс без хвостовых нулей: 0.00001685, 59337.21."""
    return f"{rate:.8f}".rstrip("0").rstrip(".")


def format_timestamp(timestamp: str) -> str:
    """2025-10-09T00:03:22Z -> 2025-10-09 00:03:22."""
    return timestamp.replace("T", " ").rstrip("Z")
