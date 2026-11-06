import argparse
import shlex
from collections.abc import Callable
from dataclasses import dataclass

from prettytable import PrettyTable

from valutatrade_hub.core import usecases
from valutatrade_hub.core.currencies import supported_codes
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.utils import format_balance, format_rate, format_timestamp
from valutatrade_hub.logging_config import setup_logging

PROMPT = "> "
SEPARATOR = "-" * 33
PARSER_LOG = "logs/parser.log"
PARSER_SOURCES = ("coingecko", "exchangerate")

CREDENTIAL_ARGS = (
    ("--username", {"required": True}),
    ("--password", {"required": True}),
)
TRADE_ARGS = (
    ("--currency", {"required": True}),
    ("--amount", {"required": True, "type": float}),
)

HELP_TEXT = """Команды:
  register --username <имя> --password <пароль>
  login --username <имя> --password <пароль>
  show-portfolio [--base <валюта>]
  deposit --currency <код> --amount <число>
  buy --currency <код> --amount <число>
  sell --currency <код> --amount <число>
  get-rate --from <код> --to <код>
  update-rates [--source coingecko|exchangerate]
  show-rates [--currency <код>] [--top <N>] [--base <код>]
  help, exit"""


@dataclass
class Session:
    """Текущая сессия пользователя."""

    user_id: int | None = None
    username: str | None = None


session = Session()


class _ArgumentParser(argparse.ArgumentParser):
    """Парсер, который бросает ValueError вместо завершения программы."""

    def error(self, message: str):
        """Превращает ошибку разбора аргументов в ValueError."""
        raise ValueError(f"Ошибка аргументов: {message}")


def _parse(name: str, argv: list[str], *arguments: tuple[str, dict]):
    """Разбирает аргументы команды по списку (флаг, параметры)."""
    parser = _ArgumentParser(prog=name, add_help=False)
    for flag, options in arguments:
        parser.add_argument(flag, **options)
    return parser.parse_args(argv)


def _require_login() -> int:
    """Возвращает id текущего пользователя или требует выполнить login."""
    if session.user_id is None:
        raise PermissionError("Сначала выполните login")
    return session.user_id


def _print_trade(title: str, result: dict, total_label: str, total: float) -> None:
    """Общий вывод итога сделки для buy и sell."""
    code = result["code"]
    print(
        f"{title}: {format_balance(code, result['amount'])} {code} "
        f"по курсу {result['rate']:,.2f} USD/{code}\n"
        "Изменения в портфеле:\n"
        f"- {code}: было {format_balance(code, result['before'])} "
        f"→ стало {format_balance(code, result['after'])}\n"
        f"{total_label}: {total:,.2f} USD"
    )


# ---------- команды ----------
def cmd_register(argv: list[str]) -> None:
    """Команда register: регистрация нового пользователя."""
    args = _parse("register", argv, *CREDENTIAL_ARGS)
    user_id = usecases.register(args.username, args.password)
    print(
        f"Пользователь '{args.username}' зарегистрирован (id={user_id}). "
        f"Войдите: login --username {args.username} --password ****"
    )


def cmd_login(argv: list[str]) -> None:
    """Команда login: вход и фиксация текущей сессии."""
    args = _parse("login", argv, *CREDENTIAL_ARGS)
    user = usecases.login(args.username, args.password)
    session.user_id, session.username = user.user_id, user.username
    print(f"Вы вошли как '{user.username}'")


def cmd_show_portfolio(argv: list[str]) -> None:
    """Команда show-portfolio: кошельки и итоговая стоимость в базовой валюте."""
    user_id = _require_login()
    args = _parse(
        "show-portfolio", argv, ("--base", {"default": usecases.BASE_CURRENCY})
    )
    result = usecases.show_portfolio(user_id, args.base)
    base = result["base"]
    if not result["rows"]:
        print("Портфель пуст. Пополните счёт: deposit --currency USD --amount 1000")
        return
    print(f"Портфель пользователя '{session.username}' (база: {base}):")
    for code, balance, value in result["rows"]:
        print(f"- {code}: {format_balance(code, balance)}  → {value:,.2f} {base}")
    print(SEPARATOR)
    print(f"ИТОГО: {result['total']:,.2f} {base}")


def cmd_deposit(argv: list[str]) -> None:
    """Команда deposit: пополнение кошелька (служебная)."""
    user_id = _require_login()
    args = _parse("deposit", argv, *TRADE_ARGS)
    balance = usecases.deposit(user_id, args.currency, args.amount)
    code = args.currency.strip().upper()
    print(f"Баланс {code}: {format_balance(code, balance)}")


def cmd_buy(argv: list[str]) -> None:
    """Команда buy: покупка валюты за USD."""
    user_id = _require_login()
    args = _parse("buy", argv, *TRADE_ARGS)
    result = usecases.buy(user_id, args.currency, args.amount)
    _print_trade(
        "Покупка выполнена", result, "Оценочная стоимость покупки", result["cost"]
    )


def cmd_sell(argv: list[str]) -> None:
    """Команда sell: продажа валюты за USD."""
    user_id = _require_login()
    args = _parse("sell", argv, *TRADE_ARGS)
    result = usecases.sell(user_id, args.currency, args.amount)
    _print_trade("Продажа выполнена", result, "Оценочная выручка", result["proceeds"])


def cmd_get_rate(argv: list[str]) -> None:
    """Команда get-rate: курс одной валюты к другой и обратный курс."""
    args = _parse(
        "get-rate",
        argv,
        ("--from", {"required": True, "dest": "from_code"}),
        ("--to", {"required": True, "dest": "to_code"}),
    )
    source, target = args.from_code.strip().upper(), args.to_code.strip().upper()
    rate, updated_at = usecases.get_rate(source, target)
    reverse, _ = usecases.get_rate(target, source)
    print(
        f"Курс {source}→{target}: {format_rate(rate)} "
        f"(обновлено: {format_timestamp(updated_at)})\n"
        f"Обратный курс {target}→{source}: {format_rate(reverse)}"
    )


def cmd_update_rates(argv: list[str]) -> None:
    """Команда update-rates: немедленное обновление курсов через Parser Service."""
    args = _parse("update-rates", argv, ("--source", {"choices": PARSER_SOURCES}))
    print("INFO: Starting rates update...")
    result = usecases.update_rates(args.source)
    for name, count, error in result.results:
        if error:
            print(f"ERROR: Failed to fetch from {name}: {error}")
        else:
            print(f"INFO: Fetching from {name}... OK ({count} rates)")
    if result.total:
        print(f"INFO: Writing {result.total} rates to {result.rates_path}...")
    if result.errors:
        print(f"Update completed with errors. Check {PARSER_LOG} for details.")
    else:
        print(
            f"Update successful. Total rates updated: {result.total}. "
            f"Last refresh: {result.last_refresh}"
        )


def cmd_show_rates(argv: list[str]) -> None:
    """Команда show-rates: курсы из локального кеша с фильтрами."""
    args = _parse(
        "show-rates",
        argv,
        ("--currency", {}),
        ("--top", {"type": int}),
        ("--base", {"default": usecases.BASE_CURRENCY}),
    )
    result = usecases.show_rates(args.currency, args.top, args.base)
    print(f"Rates from cache (updated at {result['updated_at']}):")
    table = PrettyTable(["Пара", "Курс"])
    table.align["Пара"], table.align["Курс"] = "l", "r"
    for pair, rate in result["rows"]:
        table.add_row([pair, format_rate(rate)])
    print(table)


COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "register": cmd_register,
    "login": cmd_login,
    "show-portfolio": cmd_show_portfolio,
    "deposit": cmd_deposit,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "get-rate": cmd_get_rate,
    "update-rates": cmd_update_rates,
    "show-rates": cmd_show_rates,
}


def handle(line: str) -> bool:
    """Выполняет одну команду. Возвращает False, если нужно выйти."""
    try:
        parts = shlex.split(line)
    except ValueError as exc:
        print(f"Не удалось разобрать команду: {exc}")
        return True
    if not parts:
        return True
    name, argv = parts[0], parts[1:]
    if name in ("exit", "quit"):
        return False
    if name == "help":
        print(HELP_TEXT)
        return True
    command = COMMANDS.get(name)
    if command is None:
        print(f"Неизвестная команда '{name}'. Введите help")
        return True
    try:
        command(argv)
    except InsufficientFundsError as exc:
        print(exc)
    except CurrencyNotFoundError as exc:
        print(f"{exc}. Поддерживаемые валюты: {', '.join(supported_codes())}")
    except ApiRequestError as exc:
        print(f"{exc}\nПовторите попытку позже или проверьте подключение к сети.")
    except (ValueError, PermissionError) as exc:
        print(exc)
    return True


def main() -> None:
    """Интерактивный цикл CLI."""
    setup_logging()
    print("ValutaTrade Hub. Введите help для списка команд.")
    while True:
        try:
            if not handle(input(PROMPT)):
                break
        except (EOFError, KeyboardInterrupt):
            print()
            break
