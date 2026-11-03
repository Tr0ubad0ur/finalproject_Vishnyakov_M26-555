from valutatrade_hub.core.exceptions import CurrencyNotFoundError
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    EXCHANGE_RATES,
    PORTFOLIOS_FILE,
    RATES_FILE,
    USERS_FILE,
    age_seconds,
    convert,
    load_json,
    normalize_code,
    save_json,
    utc_now_iso,
    validate_amount,
)

BASE_CURRENCY = "USD"
RATES_TTL_SECONDS = 300
STUB_SOURCE = "stub"


# ---------- курсы ----------
def _refresh_rates_from_stub() -> dict:
    """Заполняет кэш rates.json из заглушки (до подключения Parser Service)."""
    now = utc_now_iso()
    cache = {
        "pairs": {
            f"{code}_{BASE_CURRENCY}": {
                "rate": rate,
                "updated_at": now,
                "source": STUB_SOURCE,
            }
            for code, rate in EXCHANGE_RATES.items()
            if code != BASE_CURRENCY
        },
        "last_refresh": now,
    }
    save_json(RATES_FILE, cache)
    return cache


def _usd_rate(code: str) -> tuple[float, str]:
    """Стоимость 1 единицы валюты в USD и время обновления."""
    if code == BASE_CURRENCY:
        return 1.0, utc_now_iso()
    pair = f"{code}_{BASE_CURRENCY}"
    item = load_json(RATES_FILE, {}).get("pairs", {}).get(pair)
    if item is None or age_seconds(item["updated_at"]) > RATES_TTL_SECONDS:
        item = _refresh_rates_from_stub()["pairs"].get(pair)
    if item is None:
        raise CurrencyNotFoundError(code)
    return item["rate"], item["updated_at"]


def get_rate(from_code: str, to_code: str) -> tuple[float, str]:
    """Курс from -> to и время обновления (по более старому из двух курсов)."""
    source, target = normalize_code(from_code), normalize_code(to_code)
    rate_from, updated_from = _usd_rate(source)
    rate_to, updated_to = _usd_rate(target)
    return rate_from / rate_to, min(updated_from, updated_to)


# ---------- пользователи ----------
def register(username: str, password: str) -> int:
    """Регистрирует пользователя и создаёт пустой портфель. Возвращает user_id."""
    username = username.strip()
    if not username:
        raise ValueError("Имя не может быть пустым")
    users = load_json(USERS_FILE, [])
    if any(u["username"] == username for u in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")
    user_id = max((u["user_id"] for u in users), default=0) + 1
    user = User.create(user_id, username, password)
    users.append(user.to_dict())
    save_json(USERS_FILE, users)
    portfolios = load_json(PORTFOLIOS_FILE, [])
    portfolios.append(Portfolio(user_id).to_dict())
    save_json(PORTFOLIOS_FILE, portfolios)
    return user_id


def login(username: str, password: str) -> User:
    """Проверяет логин и пароль, возвращает пользователя."""
    for record in load_json(USERS_FILE, []):
        if record["username"] == username:
            user = User.from_dict(record)
            if not user.verify_password(password):
                raise ValueError("Неверный пароль")
            return user
    raise ValueError(f"Пользователь '{username}' не найден")


# ---------- портфель ----------
def _load_portfolio(user_id: int) -> Portfolio:
    for record in load_json(PORTFOLIOS_FILE, []):
        if record["user_id"] == user_id:
            return Portfolio.from_dict(record)
    return Portfolio(user_id)


def _save_portfolio(portfolio: Portfolio) -> None:
    records = [
        r for r in load_json(PORTFOLIOS_FILE, []) if r["user_id"] != portfolio.user_id
    ]
    records.append(portfolio.to_dict())
    save_json(PORTFOLIOS_FILE, records)


def _get_or_create_wallet(portfolio: Portfolio, code: str) -> Wallet:
    return portfolio.get_wallet(code) or portfolio.add_currency(code)


def show_portfolio(user_id: int, base: str = BASE_CURRENCY) -> dict:
    """Кошельки пользователя и итоговая стоимость в базовой валюте."""
    base = normalize_code(base)
    try:
        _usd_rate(base)
    except CurrencyNotFoundError:
        raise ValueError(f"Неизвестная базовая валюта '{base}'") from None
    portfolio = _load_portfolio(user_id)
    rates = {code: _usd_rate(code)[0] for code in {*portfolio.wallets, base}}
    rows = [
        (code, wallet.balance, convert(wallet.balance, code, base, rates))
        for code, wallet in portfolio.wallets.items()
    ]
    return {
        "base": base,
        "rows": rows,
        "total": portfolio.get_total_value(base, rates),
    }


def deposit(user_id: int, currency_code: str, amount: float) -> float:
    """Пополняет кошелёк (служебная команда). Возвращает новый баланс."""
    code, amount = normalize_code(currency_code), validate_amount(amount)
    _usd_rate(code)  # проверка, что валюта известна
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
        "before": before,
        "after": wallet.balance,
        "cost": cost,
    }


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
        "before": before,
        "after": wallet.balance,
        "proceeds": proceeds,
    }
