import hashlib
import hmac
import secrets
from datetime import datetime

from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import EXCHANGE_RATES, convert

MIN_PASSWORD_LENGTH = 4
SALT_BYTES = 8


def _hash_password(password: str, salt: str) -> str:
    """Односторонний псевдо-хеш: sha256(password + salt)."""
    return hashlib.sha256((password + salt).encode()).hexdigest()


def _check_password_length(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен быть не короче {MIN_PASSWORD_LENGTH} символов")


class User:
    """Пользователь системы."""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = user_id
        self._username = ""
        self.username = username  # проходит через сеттер с проверкой
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Создаёт нового пользователя: генерирует соль и хеширует пароль."""
        _check_password_length(password)
        salt = secrets.token_hex(SALT_BYTES)
        return cls(
            user_id, username, _hash_password(password, salt), salt, datetime.now()
        )

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Имя не может быть пустым")
        self._username = value.strip()

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    def get_user_info(self) -> dict:
        """Информация о пользователе без пароля."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "registration_date": self._registration_date.isoformat(),
        }

    def change_password(self, new_password: str) -> None:
        """Меняет пароль: новая проверка длины, новая соль, новый хеш."""
        _check_password_length(new_password)
        self._salt = secrets.token_hex(SALT_BYTES)
        self._hashed_password = _hash_password(new_password, self._salt)

    def verify_password(self, password: str) -> bool:
        """Проверяет пароль на совпадение."""
        return hmac.compare_digest(
            self._hashed_password, _hash_password(password, self._salt)
        )

    def to_dict(self) -> dict:
        """Формат для users.json."""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        return cls(
            data["user_id"],
            data["username"],
            data["hashed_password"],
            data["salt"],
            datetime.fromisoformat(data["registration_date"]),
        )


class Wallet:
    """Кошелёк пользователя для одной валюты."""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self._balance = 0.0
        self.balance = balance

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    @staticmethod
    def _check_amount(amount: float) -> None:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise TypeError("'amount' должен быть числом")
        if amount <= 0:
            raise ValueError("'amount' должен быть положительным числом")

    def deposit(self, amount: float) -> None:
        """Пополняет баланс."""
        self._check_amount(amount)
        self.balance = self._balance + amount

    def withdraw(self, amount: float) -> None:
        """Снимает средства, если баланс позволяет."""
        self._check_amount(amount)
        if amount > self._balance:
            raise InsufficientFundsError(self._balance, amount, self.currency_code)
        self.balance = self._balance - amount

    def get_balance_info(self) -> str:
        return f"{self.currency_code}: {self._balance:.4f}"


class Portfolio:
    """Все кошельки одного пользователя."""

    def __init__(self, user_id: int, wallets: dict[str, Wallet] | None = None):
        self._user_id = user_id
        self._wallets: dict[str, Wallet] = wallets or {}

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def wallets(self) -> dict[str, Wallet]:
        """Копия словаря: внешний код не может менять состав кошельков."""
        return dict(self._wallets)

    def add_currency(self, currency_code: str) -> Wallet:
        """Добавляет новый кошелёк, если такого ещё нет."""
        if currency_code in self._wallets:
            raise ValueError(f"Кошелёк '{currency_code}' уже существует")
        self._wallets[currency_code] = Wallet(currency_code)
        return self._wallets[currency_code]

    def get_wallet(self, currency_code: str) -> Wallet | None:
        return self._wallets.get(currency_code)

    def get_total_value(
        self,
        base_currency: str = "USD",
        rates: dict[str, float] = EXCHANGE_RATES,
    ) -> float:
        """Общая стоимость всех кошельков в базовой валюте."""
        return sum(
            convert(w.balance, code, base_currency, rates)
            for code, w in self._wallets.items()
        )

    def to_dict(self) -> dict:
        """Формат для portfolios.json."""
        return {
            "user_id": self._user_id,
            "wallets": {
                code: {"balance": w.balance} for code, w in self._wallets.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        wallets = {
            code: Wallet(code, w["balance"]) for code, w in data["wallets"].items()
        }
        return cls(data["user_id"], wallets)
