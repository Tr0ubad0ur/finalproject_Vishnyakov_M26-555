import tomllib
from pathlib import Path
from typing import Any

PYPROJECT_PATH = Path("pyproject.toml")


class SettingsLoader:
    """Ровно один экземпляр на приложение.

    Singleton реализован через __new__: это проще и читабельнее метакласса,
    а повторные импорты модуля не создают новых экземпляров.
    """

    _instance = None
    _DEFAULTS: dict[str, Any] = {
        "USERS_FILE": "data/users.json",
        "PORTFOLIOS_FILE": "data/portfolios.json",
        "RATES_FILE": "data/rates.json",
        "HISTORY_FILE": "data/exchange_rates.json",
        "RATES_TTL_SECONDS": 300,
        "DEFAULT_BASE_CURRENCY": "USD",
        "LOG_DIR": "logs",
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "%(levelname)s %(asctime)s %(message)s",
        "LOG_DATE_FORMAT": "%Y-%m-%dT%H:%M:%S",
        "LOG_MAX_BYTES": 1_000_000,
        "LOG_BACKUP_COUNT": 3,
    }

    def __new__(cls):
        """Возвращает единственный экземпляр класса (Singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reload()
        return cls._instance

    def reload(self) -> None:
        """Перечитывает настройки: значения по умолчанию + [tool.valutatrade]."""
        self._data = dict(self._DEFAULTS)
        try:
            with PYPROJECT_PATH.open("rb") as file:
                section = tomllib.load(file).get("tool", {}).get("valutatrade", {})
        except (FileNotFoundError, tomllib.TOMLDecodeError):
            section = {}
        self._data.update(section)

    def get(self, key: str, default: Any = None) -> Any:
        """Значение настройки по ключу."""
        return self._data.get(key, default)
