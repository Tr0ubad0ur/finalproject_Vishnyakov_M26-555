import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def setup_logging(name: str = "actions") -> logging.Logger:
    """Возвращает логгер, пишущий в logs/<name>.log с ротацией."""
    settings = SettingsLoader()
    logger = logging.getLogger(f"valutatrade.{name}")
    if logger.handlers:  # повторный вызов не дублирует хендлеры
        return logger
    log_dir = Path(settings.get("LOG_DIR"))
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / f"{name}.log",
        maxBytes=settings.get("LOG_MAX_BYTES"),
        backupCount=settings.get("LOG_BACKUP_COUNT"),
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(settings.get("LOG_FORMAT"), settings.get("LOG_DATE_FORMAT"))
    )
    logger.addHandler(handler)
    logger.setLevel(settings.get("LOG_LEVEL"))
    logger.propagate = False
    return logger
