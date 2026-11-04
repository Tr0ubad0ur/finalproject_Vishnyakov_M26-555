from valutatrade_hub.infra.database import DatabaseManager

db = DatabaseManager()


class RatesStorage:
    """Операции чтения/записи exchange_rates.json и rates.json."""

    def __init__(self, rates_path: str, history_path: str):
        self.rates_path = rates_path
        self.history_path = history_path

    def append_history(self, records: list[dict]) -> int:
        """Дописывает новые записи в журнал; дубли по id пропускаются."""
        history = db.load(self.history_path, [])
        known = {record["id"] for record in history}
        fresh = [record for record in records if record["id"] not in known]
        if fresh:
            db.save(self.history_path, history + fresh)
        return len(fresh)

    def update_current(self, pairs: dict, last_refresh: str) -> None:
        """Обновляет кэш: пара заменяется, только если новая запись не старее."""
        current = db.load(self.rates_path, {}).get("pairs", {})
        for pair, item in pairs.items():
            old = current.get(pair)
            if old is None or item["updated_at"] >= old["updated_at"]:
                current[pair] = item
        db.save(self.rates_path, {"pairs": current, "last_refresh": last_refresh})
