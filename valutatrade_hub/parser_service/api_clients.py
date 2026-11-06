import math
import time
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig

HTTP_OK = 200
STATUS_MESSAGES = {
    401: "неверный API-ключ (401)",
    403: "доступ запрещён, проверьте API-ключ (403)",
    429: "превышен лимит запросов (429), повторите позже",
}


def _get_json(url: str, params: dict | None, timeout: int) -> tuple[dict, dict]:
    """GET-запрос: возвращает (json, мета-данные запроса) или ApiRequestError."""
    started = time.monotonic()
    try:
        response = requests.get(url, params=params, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise ApiRequestError("таймаут ожидания ответа") from exc
    except requests.exceptions.RequestException as exc:
        raise ApiRequestError(f"сетевая ошибка ({type(exc).__name__})") from exc
    if response.status_code != HTTP_OK:
        raise ApiRequestError(
            STATUS_MESSAGES.get(response.status_code, f"HTTP {response.status_code}")
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise ApiRequestError("некорректный JSON в ответе") from exc
    if not isinstance(data, dict):
        raise ApiRequestError("неожиданный формат ответа")
    meta = {
        "status_code": response.status_code,
        "request_ms": int((time.monotonic() - started) * 1000),
        "etag": response.headers.get("ETag"),
    }
    return data, meta


def _to_rate(value: object, label: str) -> float:
    """Проверяет, что курс - конечное положительное число."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        raise ApiRequestError(f"некорректный курс для {label}") from None
    if not math.isfinite(rate) or rate <= 0:
        raise ApiRequestError(f"некорректный курс для {label}")
    return rate


class BaseApiClient(ABC):
    """Единый интерфейс клиентов: fetch_rates() -> {'BTC_USD': 59337.21, ...}."""

    name: str

    def __init__(self, config: ParserConfig):
        self.config = config
        self.meta: dict = {}

    @abstractmethod
    def fetch_rates(self) -> dict[str, float]:
        """Запрашивает курсы и возвращает их в стандартном формате."""

    def meta_for(self, pair: str) -> dict:
        """Мета-данные для записи истории по паре."""
        return dict(self.meta)


class CoinGeckoClient(BaseApiClient):
    """Курсы криптовалют к USD."""

    name = "CoinGecko"

    def fetch_rates(self) -> dict[str, float]:
        """Курсы BTC, ETH, SOL к USD в формате {'BTC_USD': 59337.21, ...}."""
        ids = {
            code: self.config.CRYPTO_ID_MAP[code]
            for code in self.config.CRYPTO_CURRENCIES
        }
        params = {
            "ids": ",".join(ids.values()),
            "vs_currencies": self.config.BASE_CURRENCY.lower(),
        }
        data, self.meta = _get_json(
            self.config.COINGECKO_URL, params, self.config.REQUEST_TIMEOUT
        )
        quote = self.config.BASE_CURRENCY.lower()
        return {
            f"{code}_{self.config.BASE_CURRENCY}": _to_rate(
                (data.get(raw_id) or {}).get(quote), code
            )
            for code, raw_id in ids.items()
        }

    def meta_for(self, pair: str) -> dict:
        """Мета-данные записи истории: id монеты в CoinGecko и параметры запроса."""
        code = pair.split("_")[0]
        return {"raw_id": self.config.CRYPTO_ID_MAP[code], **self.meta}


class ExchangeRateApiClient(BaseApiClient):
    """Курсы фиатных валют к USD."""

    name = "ExchangeRate-API"

    def fetch_rates(self) -> dict[str, float]:
        """Курсы фиатных валют к USD (инвертированные: EUR_USD = 1 / курс API)."""
        key = self.config.EXCHANGERATE_API_KEY
        if not key:
            raise ApiRequestError("не задан EXCHANGERATE_API_KEY (см. .env)")
        base = self.config.BASE_CURRENCY
        url = f"{self.config.EXCHANGERATE_API_URL}/{key}/latest/{base}"
        data, self.meta = _get_json(url, None, self.config.REQUEST_TIMEOUT)
        if data.get("result") != "success":
            raise ApiRequestError(
                f"API вернул ошибку: {data.get('error-type', 'unknown')}"
            )
        rates = data.get("conversion_rates") or data.get("rates")
        if not isinstance(rates, dict):
            raise ApiRequestError("в ответе нет блока с курсами")
        # API: 1 USD = X EUR, а в кэше нужна пара EUR_USD, поэтому 1 / X
        return {
            f"{code}_{base}": 1 / _to_rate(rates.get(code), code)
            for code in self.config.FIAT_CURRENCIES
        }
