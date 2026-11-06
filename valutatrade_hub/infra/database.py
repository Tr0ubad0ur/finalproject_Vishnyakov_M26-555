import json
import os
from pathlib import Path
from typing import Any


class DatabaseManager:
    """Чтение и атомарная запись JSON-файлов."""

    _instance = None

    def __new__(cls):
        """Возвращает единственный экземпляр класса (Singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, path: str, default: Any) -> Any:
        """Читает JSON; если файла нет или он повреждён, возвращает default."""
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def save(self, path: str, data: Any) -> None:
        """Атомарная запись: временный файл, затем замена."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
