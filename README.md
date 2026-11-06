# finalproject_Vishnyakov_M26-555

## ValutaTrade Hub

Консольная платформа для отслеживания и симуляции торговли валютами.
Пользователь регистрируется, пополняет виртуальный портфель, покупает и продаёт
фиатные и криптовалюты и смотрит актуальные курсы.

Система состоит из двух сервисов:

- **Core Service**: CLI, пользователи, портфели, сделки, чтение курсов из кеша.
- **Parser Service**: запрашивает курсы у CoinGecko (крипта) и ExchangeRate-API
  (фиат), хранит историю и обновляет локальный кеш `data/rates.json`.

## Структура проекта

```bash
finalproject_<фамилия>_<группа>/
├── data/
│   ├── users.json            # пользователи
│   ├── portfolios.json       # портфели и кошельки
│   ├── rates.json            # кеш текущих курсов (читает Core)
│   └── exchange_rates.json   # история измерений (пишет Parser)
├── valutatrade_hub/
│   ├── logging_config.py     # настройка логов и ротации
│   ├── decorators.py         # @log_action
│   ├── core/                 # модели, валюты, исключения, usecases, utils
│   ├── infra/                # SettingsLoader и DatabaseManager (singleton)
│   ├── parser_service/       # config, api_clients, updater, storage, scheduler
│   └── cli/interface.py      # команды
├── main.py
├── pyproject.toml
└── uv.lock
```

## Установка

Нужны Python 3.11+ и [uv](https://docs.astral.sh/uv/).

```bash
git clone <ссылка-на-репозиторий>
cd finalproject_<фамилия>_<группа>
uv sync
```

## Запуск

```bash
uv run python main.py        # или: make project
uv run ruff check .          # линтер, или: make lint
uv build                     # сборка пакета, или: make build
```

После установки пакета (`uv tool install dist/*.whl`) доступна команда `project`.
Данные (`data/`) и логи (`logs/`) создаются в каталоге, откуда запущена программа.

## Parser Service и ключ API

1. Получите бесплатный ключ на <https://www.exchangerate-api.com/>.
2. Создайте файл `.env` в корне проекта (он в `.gitignore`, в репозиторий не попадает):

   ```bash
   EXCHANGERATE_API_KEY=ваш_ключ
   ```

   Шаблон лежит в `.env.example`. Ключ можно также передать переменной окружения.
3. Обновите курсы командой `update-rates`. Для CoinGecko ключ не нужен.

Автоматическое обновление по таймеру (каждые 5 минут, остановка Ctrl+C):

```bash
uv run python -m valutatrade_hub.parser_service.scheduler
```

Логи парсера: `logs/parser.log`, логи операций: `logs/actions.log`
(строковый формат, ротация 1 МБ × 3 файла, уровень INFO).

## Кеш курсов и TTL

Core читает только `data/rates.json`, обращений к внешним API при каждой сделке нет.
Для каждой пары хранится один последний срез (`rate`, `updated_at`, `source`).
Если курс старше `RATES_TTL_SECONDS` (по умолчанию 300 секунд), Core сам пробует
обновить кеш через Parser Service. Если не получилось, пользователь получает
сообщение, что курсы устарели, и совет выполнить `update-rates`.
Настройки (пути, TTL, базовая валюта, параметры логов) берутся из `SettingsLoader`
и могут переопределяться в `pyproject.toml`, секция `[tool.valutatrade]`.

## Команды CLI

| Команда | Описание |
|         |          |
| `register --username <имя> --password <пароль>` | регистрация (пароль не короче 4 символов) |
| `login --username <имя> --password <пароль>` | вход |
| `deposit --currency <код> --amount <число>` | пополнение кошелька (служебная команда) |
| `buy --currency <код> --amount <число>` | покупка валюты за USD |
| `sell --currency <код> --amount <число>` | продажа валюты за USD |
| `show-portfolio [--base <код>]` | кошельки и итог в базовой валюте |
| `get-rate --from <код> --to <код>` | курс пары и обратный курс |
| `update-rates [--source coingecko\|exchangerate]` | обновить кеш курсов |
| `show-rates [--currency <код>] [--top <N>] [--base <код>]` | курсы из кеша |
| `help`, `exit` | справка, выход |

Пример сессии:

```bash
> register --username alice --password 1234
Пользователь 'alice' зарегистрирован (id=1). Войдите: login --username alice --password ****
> login --username alice --password 1234
Вы вошли как 'alice'
> deposit --currency USD --amount 10000
Баланс USD: 10000.00
> buy --currency BTC --amount 0.05
Покупка выполнена: 0.0500 BTC по курсу 78,107.00 USD/BTC
Изменения в портфеле:
- BTC: было 0.0000 → стало 0.0500
Оценочная стоимость покупки: 3,905.35 USD
> show-portfolio
Портфель пользователя 'alice' (база: USD):
- USD: 6094.65  → 6,094.65 USD
- BTC: 0.0500  → 3,905.35 USD
---------------------------------
ИТОГО: 10,000.00 USD
> get-rate --from EUR --to USD
Курс EUR→USD: 1.11919418 (обновлено: 2026-11-04 12:24:39)
Обратный курс USD→EUR: 0.8935
```

Типичные ошибки:

```bash
> sell --currency BTC --amount 5
Недостаточно средств: доступно 0.0500 BTC, требуется 5.0000 BTC
> get-rate --from ABC --to USD
Неизвестная валюта 'ABC'. Поддерживаемые валюты: BTC, ETH, EUR, GBP, RUB, SOL, USD
> show-rates
Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные.
```

## Принятые решения

- **Покупка и продажа идут через USD:** `buy` списывает USD и начисляет купленную
  валюту, `sell` списывает валюту и начисляет USD. Так как у нового пользователя
  пустой портфель, добавлена служебная команда `deposit`.
- **Единый формат кеша:** `rates.json` хранит пары вида `BTC_USD` в блоке `pairs`.
  Курсы ExchangeRate-API (1 USD = X EUR) инвертируются в `EUR_USD = 1 / X`.
  Кросс-курсы считаются через USD.
- **Singleton через `__new__`:** `SettingsLoader` и `DatabaseManager`; проще и
  читабельнее метакласса.
- **Запись JSON атомарная** (временный файл, затем замена).
- **Исключения:** `InsufficientFundsError`, `CurrencyNotFoundError`, `ApiRequestError`
  пробрасываются из ядра и превращаются в сообщения только в CLI.
- **Свойство `Portfolio.user_id`** (только чтение) вместо объекта пользователя.

## Демо
