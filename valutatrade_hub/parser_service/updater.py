from dataclasses import dataclass, field

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import utc_now_iso
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.parser_service.api_clients import (
    BaseApiClient,
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage


@dataclass
class UpdateResult:
    """Итог обновления: сколько курсов получено и что с каждым источником."""

    total: int = 0
    last_refresh: str = ""
    rates_path: str = ""
    # (название источника, число курсов, текст ошибки или None)
    results: list[tuple[str, int, str | None]] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        """Тексты ошибок по источникам, которые не ответили."""
        return [f"{name}: {error}" for name, _, error in self.results if error]


class RatesUpdater:
    """Точка входа логики парсинга."""

    def __init__(self, clients: dict[str, BaseApiClient], storage: RatesStorage):
        self.clients = clients
        self.storage = storage
        self.log = setup_logging("parser")

    def run_update(self, source: str | None = None) -> UpdateResult:
        """Опрашивает клиентов (всех или один), объединяет и сохраняет курсы."""
        if source is not None and source not in self.clients:
            raise ValueError(
                f"Неизвестный источник '{source}'. Доступно: {', '.join(self.clients)}"
            )
        self.log.info("Starting rates update...")
        now = utc_now_iso()
        result = UpdateResult(last_refresh=now, rates_path=self.storage.rates_path)
        pairs: dict[str, dict] = {}
        history: list[dict] = []

        for key, client in self.clients.items():
            if source is not None and key != source:
                continue
            try:
                rates = client.fetch_rates()
            except (
                ApiRequestError
            ) as exc:  # падение одного клиента не стопорит остальных
                self.log.error("Failed to fetch from %s: %s", client.name, exc.reason)
                result.results.append((client.name, 0, exc.reason))
                continue
            self.log.info("Fetching from %s... OK (%d rates)", client.name, len(rates))
            result.results.append((client.name, len(rates), None))
            for pair, rate in rates.items():
                from_code, to_code = pair.split("_")
                pairs[pair] = {"rate": rate, "updated_at": now, "source": client.name}
                history.append(
                    {
                        "id": f"{pair}_{now}",
                        "from_currency": from_code,
                        "to_currency": to_code,
                        "rate": rate,
                        "timestamp": now,
                        "source": client.name,
                        "meta": client.meta_for(pair),
                    }
                )

        if pairs:
            self.storage.append_history(history)
            self.storage.update_current(pairs, now)
            self.log.info("Writing %d rates to %s", len(pairs), self.storage.rates_path)
        result.total = len(pairs)
        self.log.info(
            "Update finished: %d rates, %d errors", result.total, len(result.errors)
        )
        return result


def create_updater(config: ParserConfig | None = None) -> RatesUpdater:
    """Собирает RatesUpdater со стандартными клиентами и хранилищем."""
    config = config or ParserConfig()
    clients: dict[str, BaseApiClient] = {
        "coingecko": CoinGeckoClient(config),
        "exchangerate": ExchangeRateApiClient(config),
    }
    storage = RatesStorage(config.RATES_FILE_PATH, config.HISTORY_FILE_PATH)
    return RatesUpdater(clients, storage)
