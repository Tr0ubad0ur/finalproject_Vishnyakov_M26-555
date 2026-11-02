# Стоимость 1 единицы валюты в USD (заглушка до подключения Parser Service)
EXCHANGE_RATES: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.0786,
    "BTC": 59337.21,
    "ETH": 3720.0,
    "RUB": 0.01016,
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
