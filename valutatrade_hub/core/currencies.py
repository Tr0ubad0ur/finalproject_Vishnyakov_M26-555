from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError

CODE_MIN_LENGTH = 2
CODE_MAX_LENGTH = 5


class Currency(ABC):
    """Базовая валюта."""

    def __init__(self, name: str, code: str):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Название валюты не может быть пустым")
        if (
            not isinstance(code, str)
            or not CODE_MIN_LENGTH <= len(code) <= CODE_MAX_LENGTH
            or " " in code
            or code != code.upper()
        ):
            raise ValueError("Код валюты: верхний регистр, 2-5 символов, без пробелов")
        self.name = name.strip()
        self.code = code

    @abstractmethod
    def get_display_info(self) -> str:
        """Строковое представление для UI и логов."""


class FiatCurrency(Currency):
    """Фиатная валюта."""

    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self) -> str:
        """Строка вида '[FIAT] USD — US Dollar (Issuing: United States)'."""
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    """Криптовалюта."""

    def __init__(self, name: str, code: str, algorithm: str, market_cap: float):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    def get_display_info(self) -> str:
        """Строка вида '[CRYPTO] BTC — Bitcoin (Algo: SHA-256, MCAP: 1.12e12)'."""
        mcap = f"{self.market_cap:.2e}".replace("e+", "e")  # 1.12e12, как в ТЗ
        return (
            f"[CRYPTO] {self.code} — {self.name} (Algo: {self.algorithm}, MCAP: {mcap})"
        )


_REGISTRY: dict[str, Currency] = {
    c.code: c
    for c in (
        FiatCurrency("US Dollar", "USD", "United States"),
        FiatCurrency("Euro", "EUR", "Eurozone"),
        FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
        FiatCurrency("Russian Ruble", "RUB", "Russia"),
        CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
        CryptoCurrency("Ethereum", "ETH", "Ethash", 4.5e11),
        CryptoCurrency("Solana", "SOL", "Proof of History", 7.0e10),
    )
}


def get_currency(code: str) -> Currency:
    """Возвращает валюту по коду или бросает CurrencyNotFoundError."""
    try:
        return _REGISTRY[code]
    except KeyError:
        raise CurrencyNotFoundError(code) from None


def supported_codes() -> list[str]:
    """Список поддерживаемых кодов валют."""
    return sorted(_REGISTRY)
