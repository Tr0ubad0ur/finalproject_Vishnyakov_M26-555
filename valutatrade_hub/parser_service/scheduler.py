import threading

from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater, create_updater


def run_periodically(
    updater: RatesUpdater,
    interval_seconds: int,
    stop_event: threading.Event | None = None,
) -> None:
    """Обновляет курсы каждые interval_seconds, пока не сработает stop_event."""
    stop = stop_event or threading.Event()
    while not stop.is_set():
        updater.run_update()
        stop.wait(interval_seconds)


def main() -> None:
    """Запуск: uv run python -m valutatrade_hub.parser_service.scheduler"""
    config = ParserConfig()
    print(
        f"Автообновление каждые {config.UPDATE_INTERVAL_SECONDS} с. Остановка: Ctrl+C"
    )
    try:
        run_periodically(create_updater(config), config.UPDATE_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("Остановлено")


if __name__ == "__main__":
    main()
