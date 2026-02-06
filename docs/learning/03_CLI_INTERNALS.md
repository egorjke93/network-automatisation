# 03. CLI -- как работает командная строка изнутри

> **Время чтения:** ~30 минут
>
> **Предыдущий документ:** [02. Обзор проекта](02_PROJECT_OVERVIEW.md)
>
> **Связанная документация:** [CLI_INTERNALS.md](../CLI_INTERNALS.md) -- полное техническое описание CLI

---

## 1. Что происходит при запуске

Когда ты вводишь:

```bash
python -m network_collector mac --format excel
```

Python выполняет следующую цепочку:

```
python -m network_collector mac --format excel
       │
       ▼
  __main__.py                          # Python ищет __main__.py в пакете
       │
       │   from .cli import main
       │   main()
       ▼
  cli/__init__.py → main()             # Главная функция CLI
       │
       │   parser = setup_parser()     # Создаём парсер аргументов
       │   args = parser.parse_args()  # Парсим "mac --format excel"
       │   ...                         # Настраиваем логирование
       │   if args.command == "mac":
       │       cmd_mac(args, ctx)      # Вызываем обработчик команды
       ▼
  cli/commands/collect.py → cmd_mac()  # Обработчик команды "mac"
       │
       │   devices, credentials = prepare_collection(args)  # Загружаем устройства
       │   collector = MACCollector(...)                     # Создаём коллектор
       │   data = collector.collect_dicts(devices)           # Собираем данные
       │   exporter = get_exporter("excel", ...)             # Создаём экспортёр
       │   exporter.export(data, "mac_addresses")            # Сохраняем в Excel
       ▼
  Готово! Файл mac_addresses_20250115.xlsx в папке reports/
```

Давай разберём каждый шаг подробно.

---

## 2. argparse простыми словами

### Зачем нужен argparse

Когда ты пишешь `python -m network_collector mac --format excel`, Python получает строку `"mac --format excel"`. Нужно как-то понять:
- `mac` -- это команда (подкоманда)
- `--format excel` -- это опция со значением `excel`

Модуль `argparse` из стандартной библиотеки Python делает это автоматически.

### Аналогия: меню в ресторане

Представь меню в ресторане:

```
МЕНЮ (parser):
├── Бургер (подкоманда "mac")
│   ├── С сыром (--format excel)
│   ├── Без лука (--no-descriptions)
│   └── Двойная котлета (--with-port-security)
├── Пицца (подкоманда "lldp")
│   ├── Маргарита (--protocol lldp)
│   └── Четыре сыра (--protocol both)
└── Салат (подкоманда "devices")
    └── Без заправки (--format csv)
```

Ты говоришь: "Бургер с сыром" -- и кассир (argparse) понимает: блюдо = бургер, опция = с сыром.

### Как это выглядит в коде

Вот упрощённый пример -- так работает argparse:

```python
import argparse

# 1. Создаём главный парсер
parser = argparse.ArgumentParser(
    prog="network_collector",
    description="Утилита для сбора данных с сетевых устройств"
)

# 2. Добавляем общие аргументы (работают для всех команд)
parser.add_argument("-v", "--verbose", action="store_true", help="Подробный вывод")
parser.add_argument("-d", "--devices", default="devices_ips.py", help="Файл с устройствами")

# 3. Создаём подкоманды
subparsers = parser.add_subparsers(dest="command", help="Команды")

# 4. Подкоманда "mac"
mac_parser = subparsers.add_parser("mac", help="Сбор MAC-адресов")
mac_parser.add_argument("--format", choices=["excel", "csv", "json"], default="excel")
mac_parser.add_argument("--mac-format", choices=["ieee", "cisco", "unix"])

# 5. Подкоманда "lldp"
lldp_parser = subparsers.add_parser("lldp", help="Сбор LLDP/CDP соседей")
lldp_parser.add_argument("--protocol", choices=["lldp", "cdp", "both"], default="lldp")

# 6. Парсим аргументы
args = parser.parse_args()  # Для "mac --format excel" вернёт:
                             # args.command = "mac"
                             # args.format = "excel"
                             # args.verbose = False
                             # args.devices = "devices_ips.py"
```

**Что здесь происходит:**

- `ArgumentParser()` -- создаёт парсер. Это объект, который знает, какие аргументы ожидать.
- `add_argument()` -- описывает один аргумент (имя, тип, значение по умолчанию).
- `add_subparsers()` -- создаёт "ветвление" -- каждая подкоманда (`mac`, `lldp`, `devices`) имеет свои аргументы.
- `parse_args()` -- берёт то, что ты ввёл в терминале, и превращает в объект `args` с атрибутами.

### Типы аргументов

```python
# Флаг (True/False): --verbose → args.verbose = True
parser.add_argument("--verbose", action="store_true")

# Значение со списком допустимых: --format excel → args.format = "excel"
parser.add_argument("--format", choices=["excel", "csv", "json"], default="csv")

# Произвольное значение: --site "Office" → args.site = "Office"
parser.add_argument("--site", default="Main")

# Короткая и длинная форма: -f excel или --format excel -- одно и то же
parser.add_argument("-f", "--format", choices=["excel", "csv"])
```

---

## 3. Структура CLI модуля

```
cli/
├── __init__.py          # main() и setup_parser() -- точка входа
├── utils.py             # Общие утилиты: load_devices, get_credentials, get_exporter
└── commands/            # Каждая команда -- отдельный файл
    ├── __init__.py      #   Импорты всех команд в одном месте
    ├── collect.py       #   cmd_devices, cmd_mac, cmd_lldp, cmd_interfaces, cmd_inventory
    ├── sync.py          #   cmd_sync_netbox
    ├── backup.py        #   cmd_backup, cmd_run
    ├── pipeline.py      #   cmd_pipeline
    ├── match.py         #   cmd_match_mac
    ├── push.py          #   cmd_push_descriptions
    └── validate.py      #   cmd_validate_fields
```

### Зачем так разделено

Можно было бы свалить всё в один файл на 2000 строк. Но тогда:
- Искать нужный код -- мучение.
- Два разработчика не могут одновременно редактировать разные команды.
- Тесты сложнее писать.

Поэтому каждая команда -- в отдельном файле. Хочешь понять `sync-netbox`? Открывай `commands/sync.py`. Хочешь `mac`? Открывай `commands/collect.py`.

### Как файлы связаны между собой

```
cli/__init__.py                         # Точка входа
    │
    ├── from .utils import ...          # Общие утилиты
    │       └── load_devices()          #   Загрузка устройств из devices_ips.py
    │       └── get_exporter()          #   Выбор экспортёра (Excel/CSV/JSON)
    │       └── get_credentials()       #   Получение логина/пароля
    │       └── prepare_collection()    #   Комбо: load_devices + get_credentials
    │
    └── from .commands import ...       # Все обработчики команд
            ├── cmd_mac                 #   из commands/collect.py
            ├── cmd_lldp               #   из commands/collect.py
            ├── cmd_sync_netbox        #   из commands/sync.py
            ├── cmd_pipeline           #   из commands/pipeline.py
            └── ...
```

---

## 4. Пошаговый путь команды `mac`

Давай проследим весь путь команды от ввода до результата, с реальным кодом из проекта.

### Шаг 1: `__main__.py` -- точка входа

Файл: `network_collector/__main__.py`

```python
"""
Точка входа для запуска модуля.

Позволяет запускать утилиту как:
    python -m network_collector [команда] [опции]
"""
from .cli import main

if __name__ == "__main__":
    main()
```

**Что тут происходит:**
- Когда ты пишешь `python -m network_collector`, Python ищет файл `__main__.py` в пакете `network_collector`.
- Импортирует функцию `main()` из `cli/__init__.py`.
- Вызывает её.

### Шаг 2: `main()` -- настройка и маршрутизация

Файл: `network_collector/cli/__init__.py`

```python
def main() -> None:
    """Главная функция CLI."""
    from ..config import load_config, config
    from ..core.context import RunContext, set_current_context
    from ..core.logging import LogConfig, setup_logging_from_config

    # 1. Создаём парсер и разбираем аргументы
    parser = setup_parser()
    args = parser.parse_args()

    # 2. Загружаем конфигурацию из config.yaml
    load_config(args.config)

    # 3. Создаём контекст выполнения (dry_run, run_id, и т.д.)
    dry_run = getattr(args, "dry_run", False)
    ctx = RunContext.create(
        dry_run=dry_run,
        triggered_by="cli",
        command=args.command or "",
    )
    set_current_context(ctx)

    # 4. Настраиваем логирование
    # ... (пропускаем для краткости)

    # 5. Маршрутизация: вызываем нужную функцию по имени команды
    if args.command == "devices":
        cmd_devices(args, ctx)
    elif args.command == "mac":
        cmd_mac(args, ctx)              # ← Для "mac" вызывается cmd_mac
    elif args.command == "lldp":
        cmd_lldp(args, ctx)
    elif args.command == "sync-netbox":
        cmd_sync_netbox(args, ctx)
    elif args.command == "pipeline":
        cmd_pipeline(args, ctx)
    # ... остальные команды
    else:
        parser.print_help()             # Если команда не указана -- показываем справку
```

**Что тут происходит:**
1. `setup_parser()` создаёт объект-парсер со всеми командами и их аргументами.
2. `parser.parse_args()` разбирает то, что ты ввёл. Для `mac --format excel` получаем: `args.command = "mac"`, `args.format = "excel"`.
3. Загружаем конфиг из `config.yaml` -- там таймауты, URL NetBox, настройки вывода.
4. Создаём `RunContext` -- объект с метаданными запуска (ID, время, dry_run).
5. Большой `if/elif` -- маршрутизация. Для `"mac"` вызываем `cmd_mac(args, ctx)`.

### Шаг 3: `setup_parser()` -- регистрация команды `mac`

Файл: `network_collector/cli/__init__.py`

```python
def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="network_collector",
        description="Утилита для сбора данных с сетевых устройств",
    )

    # Общие аргументы (для всех команд)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--devices", default="devices_ips.py")
    parser.add_argument("-o", "--output", default="reports")
    parser.add_argument("--transport", choices=["ssh2", "paramiko", "system"], default="ssh2")

    # Создаём подкоманды
    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # === MAC ===
    mac_parser = subparsers.add_parser("mac", help="Сбор MAC-адресов")
    mac_parser.add_argument("--format", "-f",
        choices=["excel", "csv", "json", "raw"], default="excel")
    mac_parser.add_argument("--mac-format",
        choices=["ieee", "cisco", "unix"], default=None)
    mac_parser.add_argument("--fields", help="Поля для вывода (через запятую)")
    mac_parser.add_argument("--with-descriptions", action="store_true")
    mac_parser.add_argument("--no-descriptions", action="store_true")
    mac_parser.add_argument("--include-trunk", action="store_true")
    mac_parser.add_argument("--per-device", action="store_true")

    # ... (другие подкоманды: devices, lldp, sync-netbox и т.д.)

    return parser
```

**Что тут происходит:**
- Для команды `mac` регистрируются все возможные аргументы.
- `choices=["excel", "csv", "json", "raw"]` -- argparse сам проверит, что формат допустимый.
- `default="excel"` -- если `--format` не указан, будет `"excel"`.
- `action="store_true"` -- это флаг-переключатель (есть → `True`, нет → `False`).

### Шаг 4: `cmd_mac()` -- обработчик команды

Файл: `network_collector/cli/commands/collect.py`

```python
def cmd_mac(args, ctx=None) -> None:
    """Обработчик команды mac."""
    # Ленивый импорт -- загружаем модули только когда нужны
    from ...collectors import MACCollector
    from ...config import config as app_config
    from ...fields_config import apply_fields_config

    # Шаг 4.1: Загружаем устройства и учётные данные
    devices, credentials = prepare_collection(args)
    # devices = [Device(host="10.0.0.1", platform="cisco_ios"), ...]
    # credentials = Credentials(username="admin", password="***")

    # Шаг 4.2: Определяем параметры из аргументов или конфига
    fields = args.fields.split(",") if args.fields else None
    mac_format = args.mac_format or app_config.output.mac_format

    # Шаг 4.3: Создаём коллектор
    collector = MACCollector(
        credentials=credentials,
        mac_format=mac_format,           # Формат MAC-адреса (ieee/cisco/unix)
        ntc_fields=fields,               # Какие поля извлекать
        collect_descriptions=True,       # Собирать описания интерфейсов
        transport=args.transport,        # SSH-транспорт (ssh2/paramiko)
    )

    # Шаг 4.4: Собираем данные со всех устройств
    data = collector.collect_dicts(devices)
    # data = [
    #     {"hostname": "switch-01", "mac": "00:11:22:33:44:55", "interface": "Gi0/1", "vlan": 10},
    #     {"hostname": "switch-01", "mac": "00:11:22:33:44:66", "interface": "Gi0/2", "vlan": 20},
    #     {"hostname": "switch-02", "mac": "AA:BB:CC:DD:EE:FF", "interface": "Gi0/1", "vlan": 10},
    #     ...
    # ]

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # Шаг 4.5: Применяем конфиг полей (из fields.yaml)
    data = apply_fields_config(data, "mac")
    # Переименовывает колонки, убирает отключённые поля, сортирует по order

    # Шаг 4.6: Экспортируем
    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "mac_addresses")
    # → reports/mac_addresses_20250115.xlsx

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

**Что тут происходит пошагово:**

1. **Ленивые импорты** (`from ...collectors import MACCollector`) -- модули загружаются только при вызове этой команды, а не при старте программы. Это ускоряет запуск.

2. **`prepare_collection(args)`** -- утилита из `cli/utils.py`. Загружает список устройств из `devices_ips.py` и получает учётные данные (логин/пароль). Возвращает кортеж `(devices, credentials)`.

3. **`MACCollector(...)`** -- создаём экземпляр коллектора с нужными настройками.

4. **`collector.collect_dicts(devices)`** -- главная работа. Коллектор:
   - Подключается к каждому устройству по SSH.
   - Выполняет `show mac address-table` (и другие команды).
   - Парсит текстовый вывод через NTC Templates.
   - Нормализует данные (формат MAC, имена интерфейсов).
   - Возвращает список словарей.

5. **`apply_fields_config(data, "mac")`** -- применяет настройки из `fields.yaml`: переименовывает колонки, убирает отключённые поля.

6. **`exporter.export(data, "mac_addresses")`** -- сохраняет данные в файл нужного формата.

### Шаг 5: `prepare_collection()` -- загрузка устройств

Файл: `network_collector/cli/utils.py`

```python
def prepare_collection(args) -> Tuple[List, object]:
    """
    Подготавливает устройства и credentials для сбора данных.

    Returns:
        tuple: (devices, credentials)
    """
    devices = load_devices(args.devices)    # Загрузка устройств из файла
    credentials = get_credentials()          # Получение логина/пароля
    return devices, credentials
```

**Что тут происходит:**
- `load_devices()` -- читает файл `devices_ips.py`, парсит список устройств, создаёт объекты `Device`.
- `get_credentials()` -- получает логин/пароль (из переменных окружения, конфига или интерактивного ввода).

А вот `load_devices()` подробнее:

```python
def load_devices(devices_file: str) -> List:
    """Загружает список устройств из файла."""
    from ..core.device import Device

    devices_path = Path(devices_file)

    # Если файл не найден по указанному пути -- ищем в директории модуля
    if not devices_path.exists():
        module_dir = Path(__file__).parent.parent
        devices_path = module_dir / devices_file

    if not devices_path.exists():
        logger.error(f"Файл устройств не найден: {devices_file}")
        sys.exit(1)

    # Загружаем Python-файл как модуль
    import importlib.util
    spec = importlib.util.spec_from_file_location("devices", devices_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Берём переменную devices_list из загруженного файла
    devices_list = getattr(module, "devices_list", None)

    # Преобразуем словари в объекты Device
    devices = []
    for d in devices_list:
        devices.append(
            Device(
                host=d.get("host"),
                platform=d.get("platform"),
                device_type=d.get("device_type"),
            )
        )

    logger.info(f"Загружено устройств: {len(devices)}")
    return devices
```

**Что тут происходит:**
- Файл `devices_ips.py` -- это обычный Python-файл со списком словарей.
- `importlib` загружает его как модуль и достаёт переменную `devices_list`.
- Каждый словарь превращается в объект `Device`.

Пример `devices_ips.py`:

```python
devices_list = [
    {"host": "10.0.0.1", "platform": "cisco_ios", "device_type": "C9200L-24P-4X"},
    {"host": "10.0.0.2", "platform": "cisco_iosxe", "device_type": "C9300-48T"},
    {"host": "10.0.0.3", "platform": "arista_eos", "device_type": "DCS-7050TX"},
]
```

### Шаг 6: `get_exporter()` -- выбор экспортёра

Файл: `network_collector/cli/utils.py`

```python
def get_exporter(format_type: str, output_folder: str, delimiter: str = ","):
    """Возвращает экспортер по типу формата."""
    from ..exporters import CSVExporter, JSONExporter, ExcelExporter, RawExporter

    if format_type == "csv":
        return CSVExporter(output_folder=output_folder, delimiter=delimiter)
    elif format_type == "json":
        return JSONExporter(output_folder=output_folder)
    elif format_type == "raw":
        return RawExporter()
    else:
        return ExcelExporter(output_folder=output_folder)
```

**Что тут происходит:**
- По значению `--format` выбирается нужный экспортёр.
- Все экспортёры имеют одинаковый метод `export(data, filename)` -- это общий интерфейс из базового класса `BaseExporter`.
- Паттерн "Фабрика" -- функция создаёт объект нужного типа по параметру.

---

## 5. Как sync-netbox отличается от collect-команд

### Collect-команды: SSH → файл

Collect-команды (`mac`, `lldp`, `devices`, `interfaces`, `inventory`) работают по простой схеме:

```
SSH к устройству → парсинг текста → экспорт в файл
```

Это "в одну сторону" -- мы только ЧИТАЕМ с устройства и сохраняем.

### sync-netbox: SSH → сравнение → NetBox API

Sync работает сложнее:

```
SSH к устройству → парсинг текста → сравнение с NetBox → API-вызовы в NetBox
                                          │
                                    ┌─────┴─────┐
                                    │  NetBox    │
                                    │  (текущие  │
                                    │  данные)   │
                                    └────────────┘
```

Ключевое отличие: **sync сравнивает** собранные данные с тем, что уже есть в NetBox, и решает, что нужно создать, обновить или удалить.

### Код `cmd_sync_netbox()` с пояснениями

Файл: `network_collector/cli/commands/sync.py`

```python
def cmd_sync_netbox(args, ctx=None) -> None:
    """
    Обработчик команды sync-netbox.

    ВАЖНО: С устройств мы только ЧИТАЕМ данные!
    Синхронизация -- это выгрузка собранных данных В NetBox.
    """
    from ...netbox import NetBoxClient, NetBoxSync, DiffCalculator
    from ...collectors import InterfaceCollector, LLDPCollector
    from ...config import config

    # --sync-all включает все флаги синхронизации
    if getattr(args, "sync_all", False):
        args.create_devices = True
        args.update_devices = True
        args.interfaces = True
        args.ip_addresses = True
        args.vlans = True
        args.cables = True
        args.inventory = True

    # === Подключение к NetBox ===
    url = args.url or config.netbox.url       # URL из аргументов или config.yaml
    token = args.token or config.netbox.token  # Токен из аргументов или config.yaml

    client = NetBoxClient(url=url, token=token)  # HTTP-клиент для NetBox API
    sync = NetBoxSync(client, dry_run=args.dry_run)  # Синхронизатор

    # === Загрузка устройств ===
    devices, credentials = prepare_collection(args)

    # === Синхронизация интерфейсов (если указан флаг --interfaces) ===
    if args.interfaces:
        collector = InterfaceCollector(credentials=credentials, transport=args.transport)

        for device in devices:
            # 1. Собираем данные с устройства по SSH
            data = collector.collect([device])

            if data:
                hostname = data[0].hostname or device.host

                # 2. Синхронизируем с NetBox
                #    Внутри sync.sync_interfaces():
                #    - Получает текущие интерфейсы из NetBox для этого устройства
                #    - Сравнивает с собранными (SyncComparator)
                #    - Создаёт новые / обновляет изменённые / удаляет лишние
                stats = sync.sync_interfaces(hostname, data, cleanup=False)
                # stats = {"created": 3, "updated": 5, "deleted": 0, ...}

    # ... (аналогично для cables, ip_addresses, vlans, inventory)

    # === Сводка в конце ===
    _print_sync_summary(summary, all_details, args)
```

### Разница в одной картинке

```
cmd_mac (collect):
  devices → [SSH → parse] → data → export(data) → файл.xlsx

cmd_sync_netbox (sync):
  devices → [SSH → parse] → data ─┐
                                   ├── compare → create/update/delete → NetBox API
  NetBox (текущие данные) ─────────┘
```

---

## 6. Как добавить свою команду

Допустим, ты хочешь добавить команду `arp` -- сбор ARP-таблицы.

### Шаг 1: Создай обработчик в `cli/commands/`

Файл: `network_collector/cli/commands/arp.py`

```python
"""
Команда arp -- сбор ARP-таблицы.
"""

import logging
from ..utils import prepare_collection, get_exporter

logger = logging.getLogger(__name__)


def cmd_arp(args, ctx=None) -> None:
    """Обработчик команды arp."""
    # Загружаем устройства и учётные данные
    devices, credentials = prepare_collection(args)

    # Используем существующий механизм run для произвольных команд
    from ...core.connection import ConnectionManager
    from ...parsers.textfsm_parser import NTCParser

    conn_manager = ConnectionManager(transport=args.transport)
    parser = NTCParser()
    all_data = []

    for device in devices:
        try:
            with conn_manager.connect(device, credentials) as conn:
                hostname = conn_manager.get_hostname(conn)
                output = conn.send_command("show ip arp").result

                # Парсим через NTC Templates
                parsed = parser.parse(
                    output=output,
                    platform=device.platform,
                    command="show ip arp",
                )
                for row in parsed:
                    row["hostname"] = hostname
                    row["device_ip"] = device.host
                all_data.extend(parsed)

        except Exception as e:
            logger.error(f"Ошибка на {device.host}: {e}")

    if not all_data:
        logger.warning("Нет данных для экспорта")
        return

    # Экспортируем
    exporter = get_exporter(args.format, args.output)
    file_path = exporter.export(all_data, "arp_table")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

### Шаг 2: Зарегистрируй команду в `cli/commands/__init__.py`

Файл: `network_collector/cli/commands/__init__.py`

```python
# Добавь импорт:
from .arp import cmd_arp

# Добавь в __all__:
__all__ = [
    "cmd_devices",
    "cmd_mac",
    # ...
    "cmd_arp",  # ← Новая команда
]
```

### Шаг 3: Добавь парсер в `setup_parser()` в `cli/__init__.py`

Файл: `network_collector/cli/__init__.py`

```python
def setup_parser() -> argparse.ArgumentParser:
    # ... (существующий код)

    # === ARP (новая команда) ===
    arp_parser = subparsers.add_parser("arp", help="Сбор ARP-таблицы")
    arp_parser.add_argument(
        "--format", "-f",
        choices=["excel", "csv", "json", "raw"],
        default="excel",
        help="Формат вывода",
    )

    # ... (return parser)
```

### Шаг 4: Добавь маршрут в `main()`

Файл: `network_collector/cli/__init__.py`

```python
def main() -> None:
    # ... (существующий код)

    elif args.command == "arp":
        cmd_arp(args, ctx)

    # ... (else: parser.print_help())
```

### Шаг 5: Добавь импорт в `cli/__init__.py`

```python
from .commands import (
    cmd_devices,
    cmd_mac,
    # ...
    cmd_arp,  # ← Новая команда
)
```

### Готово!

Теперь можно запускать:

```bash
python -m network_collector arp --format excel
```

### Чеклист для новой команды

1. [ ] Создать файл `cli/commands/my_command.py` с функцией `cmd_my_command(args, ctx=None)`
2. [ ] Добавить импорт в `cli/commands/__init__.py`
3. [ ] Добавить парсер аргументов в `setup_parser()` в `cli/__init__.py`
4. [ ] Добавить маршрут в `main()` в `cli/__init__.py`
5. [ ] Добавить импорт `cmd_my_command` в `cli/__init__.py`
6. [ ] Написать тесты в `tests/test_cli/`

---

## Итоги

Вот что ты узнал из этого документа:

| Концепция | Суть |
|-----------|------|
| `__main__.py` | Точка входа при запуске `python -m network_collector` |
| `argparse` | Стандартный модуль Python для разбора аргументов командной строки |
| `setup_parser()` | Регистрирует все команды и их аргументы |
| `main()` | Парсит аргументы, настраивает окружение, вызывает нужный обработчик |
| `cmd_*()` | Обработчик конкретной команды (cmd_mac, cmd_sync_netbox и т.д.) |
| `prepare_collection()` | Загружает устройства и credentials |
| `get_exporter()` | Фабрика: возвращает экспортёр по типу формата |
| collect vs sync | collect: SSH → файл. sync: SSH → сравнение с NetBox → API |

### Что читать дальше

| # | Документ | Что узнаешь |
|---|----------|-------------|
| 04 | Модели данных | Как устроены `Interface`, `MACEntry`, `LLDPNeighbor` -- модели, через которые передаются данные между слоями |
| 05 | NetBox Sync | Как работает `sync.sync_interfaces()` изнутри: сравнение, batch-операции, dry_run |

Также полезно:
- [CLI_INTERNALS.md](../CLI_INTERNALS.md) -- полное техническое описание CLI (все команды, все аргументы)
- [MANUAL.md](../MANUAL.md) -- руководство пользователя (примеры всех команд)
