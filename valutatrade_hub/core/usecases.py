from valutatrade_hub.core.currencies import CryptoCurrency, get_currency
from valutatrade_hub.core.exceptions import ApiRequestError, CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    age_seconds,
    convert,
    format_timestamp,
    normalize_code,
    utc_now_iso,
    validate_amount,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.database import DatabaseManager
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.updater import UpdateResult, create_updater

settings = SettingsLoader()
db = DatabaseManager()

BASE_CURRENCY = settings.get("DEFAULT_BASE_CURRENCY")
EMPTY_CACHE_MESSAGE = (
    "Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные."
)


def _read(key: str, default):
    return db.load(settings.get(key), default)


def _write(key: str, data) -> None:
    db.save(settings.get(key), data)


# ---------- курсы ----------
def update_rates(source: str | None = None) -> UpdateResult:
    """Запускает Parser Service (все источники или один)."""
    return create_updater().run_update(source)


def _refresh_or_raise() -> None:
    result = update_rates()
    if result.total == 0:
        raise ApiRequestError("; ".join(result.errors) or "нет данных от источников")


def _cached_pair(code: str) -> dict | None:
    pairs = _read("RATES_FILE", {}).get("pairs", {})
    return pairs.get(f"{code}_{BASE_CURRENCY}")


def _is_stale(item: dict) -> bool:
    return age_seconds(item["updated_at"]) > settings.get("RATES_TTL_SECONDS")


def _usd_rate(code: str) -> tuple[float, str]:
    """Стоимость 1 единицы валюты в USD и время обновления (с учётом TTL)."""
    if code == BASE_CURRENCY:
        return 1.0, utc_now_iso()
    item = _cached_pair(code)
    if item is None or _is_stale(item):
        try:
            _refresh_or_raise()
        except ApiRequestError as exc:
            if item is None:
                raise
            raise ApiRequestError(
                f"курсы устарели (обновлены {format_timestamp(item['updated_at'])}), "
                "обновить не удалось. Повторите позже: update-rates"
            ) from exc
        item = _cached_pair(code)
    if item is None:
        raise ApiRequestError(f"курс {code}→{BASE_CURRENCY} недоступен")
    return item["rate"], item["updated_at"]


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Курс from -> to и время обновления (по более старому из двух курсов)."""
    source, target = normalize_code(from_code), normalize_code(to_code)
    rate_from, updated_from = _usd_rate(source)
    rate_to, updated_to = _usd_rate(target)
    return rate_from / rate_to, min(updated_from, updated_to)


def _is_crypto(code: str) -> bool:
    try:
        return isinstance(get_currency(code), CryptoCurrency)
    except CurrencyNotFoundError:
        return False


def show_rates(
    currency: str | None = None,
    top: int | None = None,
    base: str = BASE_CURRENCY,
) -> dict:
    """Курсы из локального кеша с фильтрами (--currency, --top, --base)."""
    cache = _read("RATES_FILE", {})
    pairs = cache.get("pairs", {})
    if not pairs:
        raise ValueError(EMPTY_CACHE_MESSAGE)
    in_usd = {BASE_CURRENCY: 1.0}
    in_usd.update({pair.split("_")[0]: item["rate"] for pair, item in pairs.items()})
    base = base.strip().upper()
    if base not in in_usd:
        raise ValueError(f"Курс для '{base}' не найден в кеше.")
    rates = {
        code: value / in_usd[base] for code, value in in_usd.items() if code != base
    }
    if currency:
        code = currency.strip().upper()
        if code not in rates:
            raise ValueError(f"Курс для '{code}' не найден в кеше.")
        rates = {code: rates[code]}
    if top is not None:
        if top <= 0:
            raise ValueError("'--top' должен быть положительным числом")
        crypto = [(c, v) for c, v in rates.items() if _is_crypto(c)]
        ordered = sorted(crypto, key=lambda item: item[1], reverse=True)[:top]
    else:
        ordered = sorted(rates.items())
    if not ordered:
        raise ValueError("Нет данных по заданным фильтрам.")
    return {
        "updated_at": cache.get("last_refresh"),
        "rows": [(f"{code}_{base}", value) for code, value in ordered],
    }


# ---------- пользователи ----------
@log_action("REGISTER")
def register(username: str, password: str) -> int:
    """Регистрирует пользователя и создаёт пустой портфель. Возвращает user_id."""
    username = username.strip()
    if not username:
        raise ValueError("Имя не может быть пустым")
    users = _read("USERS_FILE", [])
    if any(u["username"] == username for u in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")
    user_id = max((u["user_id"] for u in users), default=0) + 1
    user = User.create(user_id, username, password)
    users.append(user.to_dict())
    _write("USERS_FILE", users)
    portfolios = _read("PORTFOLIOS_FILE", [])
    portfolios.append(Portfolio(user_id).to_dict())
    _write("PORTFOLIOS_FILE", portfolios)
    return user_id


@log_action("LOGIN")
def login(username: str, password: str) -> User:
    """Проверяет логин и пароль, возвращает пользователя."""
    for record in _read("USERS_FILE", []):
        if record["username"] == username:
            user = User.from_dict(record)
            if not user.verify_password(password):
                raise ValueError("Неверный пароль")
            return user
    raise ValueError(f"Пользователь '{username}' не найден")


# ---------- портфель ----------
def _load_portfolio(user_id: int) -> Portfolio:
    for record in _read("PORTFOLIOS_FILE", []):
        if record["user_id"] == user_id:
            return Portfolio.from_dict(record)
    return Portfolio(user_id)


def _save_portfolio(portfolio: Portfolio) -> None:
    records = [
        r for r in _read("PORTFOLIOS_FILE", []) if r["user_id"] != portfolio.user_id
    ]
    records.append(portfolio.to_dict())
    _write("PORTFOLIOS_FILE", records)


def _get_or_create_wallet(portfolio: Portfolio, code: str) -> Wallet:
    return portfolio.get_wallet(code) or portfolio.add_currency(code)


def show_portfolio(user_id: int, base: str = BASE_CURRENCY) -> dict:
    """Кошельки пользователя и итоговая стоимость в базовой валюте."""
    try:
        base_code = normalize_code(base)
    except CurrencyNotFoundError:
        raise ValueError(
            f"Неизвестная базовая валюта '{base.strip().upper()}'"
        ) from None
    portfolio = _load_portfolio(user_id)
    rates = {code: _usd_rate(code)[0] for code in {*portfolio.wallets, base_code}}
    rows = [
        (code, wallet.balance, convert(wallet.balance, code, base_code, rates))
        for code, wallet in portfolio.wallets.items()
    ]
    return {
        "base": base_code,
        "rows": rows,
        "total": portfolio.get_total_value(base_code, rates),
    }


@log_action("DEPOSIT")
def deposit(user_id: int, currency_code: str, amount: float) -> float:
    """Пополняет кошелёк (служебная команда). Возвращает новый баланс."""
    code, amount = normalize_code(currency_code), validate_amount(amount)
    portfolio = _load_portfolio(user_id)
    wallet = _get_or_create_wallet(portfolio, code)
    wallet.deposit(amount)
    _save_portfolio(portfolio)
    return wallet.balance


def _prepare_trade(currency_code: str, amount: float) -> tuple[str, float]:
    code, amount = normalize_code(currency_code), validate_amount(amount)
    if code == BASE_CURRENCY:
        raise ValueError(f"{BASE_CURRENCY} - базовая валюта: используйте deposit")
    return code, amount


@log_action("BUY", verbose=True)
def buy(user_id: int, currency_code: str, amount: float) -> dict:
    """Покупка: списывает USD, начисляет купленную валюту."""
    code, amount = _prepare_trade(currency_code, amount)
    rate, _ = get_rate(code, BASE_CURRENCY)
    portfolio = _load_portfolio(user_id)
    base_wallet = _get_or_create_wallet(portfolio, BASE_CURRENCY)
    wallet = _get_or_create_wallet(portfolio, code)
    before, cost = wallet.balance, amount * rate
    base_wallet.withdraw(cost)  # InsufficientFundsError, если не хватает USD
    wallet.deposit(amount)
    _save_portfolio(portfolio)
    return {
        "code": code,
        "amount": amount,
        "rate": rate,
        "base": BASE_CURRENCY,
        "before": before,
        "after": wallet.balance,
        "cost": cost,
    }


@log_action("SELL", verbose=True)
def sell(user_id: int, currency_code: str, amount: float) -> dict:
    """Продажа: списывает валюту, начисляет USD."""
    code, amount = _prepare_trade(currency_code, amount)
    portfolio = _load_portfolio(user_id)
    wallet = portfolio.get_wallet(code)
    if wallet is None:
        raise ValueError(
            f"У вас нет кошелька '{code}'. Добавьте валюту: "
            "она создаётся автоматически при первой покупке."
        )
    rate, _ = get_rate(code, BASE_CURRENCY)
    before, proceeds = wallet.balance, amount * rate
    wallet.withdraw(amount)  # InsufficientFundsError
    _get_or_create_wallet(portfolio, BASE_CURRENCY).deposit(proceeds)
    _save_portfolio(portfolio)
    return {
        "code": code,
        "amount": amount,
        "rate": rate,
        "base": BASE_CURRENCY,
        "before": before,
        "after": wallet.balance,
        "proceeds": proceeds,
    }
