import argparse
import shlex
from collections.abc import Callable
from dataclasses import dataclass

from valutatrade_hub.core import usecases
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    CurrencyNotFoundError,
    InsufficientFundsError,
)
from valutatrade_hub.core.utils import (
    format_balance,
    format_rate,
    format_timestamp,
)

PROMPT = "> "
SEPARATOR = "-" * 33
HELP_TEXT = """Команды:
  register --username <имя> --password <пароль>
  login --username <имя> --password <пароль>
  show-portfolio [--base <валюта>]
  deposit --currency <код> --amount <число>
  buy --currency <код> --amount <число>
  sell --currency <код> --amount <число>
  get-rate --from <код> --to <код>
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
        raise ValueError(f"Ошибка аргументов: {message}")


def _parse(name: str, argv: list[str], *arguments: tuple[str, dict]):
    parser = _ArgumentParser(prog=name, add_help=False)
    for flag, options in arguments:
        parser.add_argument(flag, **options)
    return parser.parse_args(argv)


def _require_login() -> int:
    if session.user_id is None:
        raise PermissionError("Сначала выполните login")
    return session.user_id


# ---------- команды ----------
def cmd_register(argv: list[str]) -> None:
    args = _parse(
        "register",
        argv,
        ("--username", {"required": True}),
        ("--password", {"required": True}),
    )
    user_id = usecases.register(args.username, args.password)
    print(
        f"Пользователь '{args.username}' зарегистрирован (id={user_id}). "
        f"Войдите: login --username {args.username} --password ****"
    )


def cmd_login(argv: list[str]) -> None:
    args = _parse(
        "login",
        argv,
        ("--username", {"required": True}),
        ("--password", {"required": True}),
    )
    user = usecases.login(args.username, args.password)
    session.user_id, session.username = user.user_id, user.username
    print(f"Вы вошли как '{user.username}'")


def cmd_show_portfolio(argv: list[str]) -> None:
    user_id = _require_login()
    args = _parse("show-portfolio", argv, ("--base", {"default": "USD"}))
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
    user_id = _require_login()
    args = _parse(
        "deposit",
        argv,
        ("--currency", {"required": True}),
        ("--amount", {"required": True, "type": float}),
    )
    balance = usecases.deposit(user_id, args.currency, args.amount)
    code = args.currency.strip().upper()
    print(f"Баланс {code}: {format_balance(code, balance)}")


def cmd_buy(argv: list[str]) -> None:
    user_id = _require_login()
    args = _parse(
        "buy",
        argv,
        ("--currency", {"required": True}),
        ("--amount", {"required": True, "type": float}),
    )
    r = usecases.buy(user_id, args.currency, args.amount)
    code = r["code"]
    print(
        f"Покупка выполнена: {format_balance(code, r['amount'])} {code} "
        f"по курсу {r['rate']:,.2f} USD/{code}\n"
        f"Изменения в портфеле:\n"
        f"- {code}: было {format_balance(code, r['before'])} "
        f"→ стало {format_balance(code, r['after'])}\n"
        f"Оценочная стоимость покупки: {r['cost']:,.2f} USD"
    )


def cmd_sell(argv: list[str]) -> None:
    user_id = _require_login()
    args = _parse(
        "sell",
        argv,
        ("--currency", {"required": True}),
        ("--amount", {"required": True, "type": float}),
    )
    r = usecases.sell(user_id, args.currency, args.amount)
    code = r["code"]
    print(
        f"Продажа выполнена: {format_balance(code, r['amount'])} {code} "
        f"по курсу {r['rate']:,.2f} USD/{code}\n"
        f"Изменения в портфеле:\n"
        f"- {code}: было {format_balance(code, r['before'])} "
        f"→ стало {format_balance(code, r['after'])}\n"
        f"Оценочная выручка: {r['proceeds']:,.2f} USD"
    )


def cmd_get_rate(argv: list[str]) -> None:
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


COMMANDS: dict[str, Callable[[list[str]], None]] = {
    "register": cmd_register,
    "login": cmd_login,
    "show-portfolio": cmd_show_portfolio,
    "deposit": cmd_deposit,
    "buy": cmd_buy,
    "sell": cmd_sell,
    "get-rate": cmd_get_rate,
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
    except (InsufficientFundsError, CurrencyNotFoundError, ApiRequestError) as exc:
        print(exc)
    except (ValueError, PermissionError) as exc:
        print(exc)
    return True


def main() -> None:
    """Интерактивный цикл CLI."""
    print("ValutaTrade Hub. Введите help для списка команд.")
    while True:
        try:
            if not handle(input(PROMPT)):
                break
        except (EOFError, KeyboardInterrupt):
            print()
            break
