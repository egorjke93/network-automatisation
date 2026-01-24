# CLI — Подробное руководство для начинающих

Этот документ объясняет внутреннее устройство CLI (Command Line Interface).
Написан максимально подробно для тех, кто только изучает Python.

---

## Содержание

1. [Введение](#введение)
2. [Архитектура CLI](#архитектура-cli)
3. [Точка входа: __main__.py](#точка-входа-__main__py)
4. [Парсер аргументов: setup_parser()](#парсер-аргументов-setup_parser)
5. [Главная функция: main()](#главная-функция-main)
6. [Утилиты CLI: utils.py](#утилиты-cli-utilspy)
7. [Команды сбора данных: collect.py](#команды-сбора-данных-collectpy)
8. [Команда sync-netbox: sync.py](#команда-sync-netbox-syncpy)
9. [Команда pipeline: pipeline.py](#команда-pipeline-pipelinepy)
10. [Полная цепочка: от команды до NetBox](#полная-цепочка-от-команды-до-netbox)
11. [Примеры с объяснениями](#примеры-с-объяснениями)

---

## Введение

### Что такое CLI?

CLI (Command Line Interface) — это способ взаимодействия с программой через терминал.
Вместо кнопок и окон — текстовые команды.

```bash
# Пример CLI команды
python -m network_collector devices --format excel
│       │               │       │        │
│       │               │       │        └── Аргумент (значение)
│       │               │       └── Опция (флаг)
│       │               └── Подкоманда (что делать)
│       └── Модуль Python
└── Интерпретатор Python
```

### Почему CLI?

1. **Автоматизация** — можно запускать из cron, скриптов
2. **Скорость** — не нужно ждать загрузки UI
3. **Гибкость** — множество опций и комбинаций
4. **Удалённая работа** — работает через SSH

---

## Архитектура CLI

```
cli/
├── __init__.py           # Главный модуль: main(), setup_parser()
├── utils.py              # Утилиты: load_devices, get_credentials
└── commands/
    ├── __init__.py       # Экспорт всех команд
    ├── collect.py        # devices, mac, lldp, interfaces, inventory
    ├── sync.py           # sync-netbox
    ├── pipeline.py       # pipeline (list, show, run, ...)
    ├── backup.py         # backup, run
    ├── match.py          # match-mac
    ├── push.py           # push-descriptions
    └── validate.py       # validate-fields
```

**Принцип организации:**
- Один файл = одна группа связанных команд
- Каждая команда — это функция `cmd_<name>(args, ctx)`
- Утилиты вынесены в `utils.py` для переиспользования

---

## Точка входа: __main__.py

**Файл:** `network_collector/__main__.py`

```python
"""
Точка входа для запуска модуля как пакета.

Когда запускаем:
    python -m network_collector

Python ищет файл __main__.py в пакете network_collector
и выполняет его.
"""

from .cli import main

if __name__ == "__main__":
    main()
```

**Что здесь происходит?**

1. `from .cli import main` — импортируем функцию `main` из модуля `cli`
   - Точка `.` означает "из текущего пакета"
   - `cli` — это папка `network_collector/cli/`
   - `main` — функция из `cli/__init__.py`

2. `if __name__ == "__main__":` — стандартная проверка Python
   - `__name__` — специальная переменная
   - Равна `"__main__"` когда файл запускается напрямую
   - Не равна когда файл импортируется

3. `main()` — запускаем главную функцию CLI

**Цепочка вызовов:**
```
python -m network_collector devices
        │
        ▼
network_collector/__main__.py
        │
        ▼
from .cli import main  → cli/__init__.py
        │
        ▼
main()  → парсинг аргументов → выполнение команды
```

---

## Парсер аргументов: setup_parser()

**Файл:** `cli/__init__.py`

### Что такое argparse?

`argparse` — это стандартный модуль Python для разбора аргументов командной строки.

```python
import argparse

# Создаём парсер
parser = argparse.ArgumentParser(
    prog="network_collector",           # Имя программы (для --help)
    description="Утилита для сбора...", # Описание
)

# Добавляем аргументы
parser.add_argument("-v", "--verbose", action="store_true")
parser.add_argument("-d", "--devices", default="devices_ips.py")

# Парсим
args = parser.parse_args()

# Используем
print(args.verbose)  # True или False
print(args.devices)  # "devices_ips.py" или что указал пользователь
```

### Функция setup_parser()

```python
def setup_parser() -> argparse.ArgumentParser:
    """
    Создаёт парсер аргументов командной строки.

    Returns:
        ArgumentParser: Настроенный парсер

    Структура:
    1. Создание главного парсера
    2. Добавление общих аргументов (-v, -d, -o, ...)
    3. Создание subparsers для подкоманд
    4. Настройка каждой подкоманды
    """

    # 1. СОЗДАНИЕ ГЛАВНОГО ПАРСЕРА
    parser = argparse.ArgumentParser(
        prog="network_collector",
        description="Утилита для сбора данных с сетевых устройств",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # RawDescriptionHelpFormatter сохраняет форматирование в epilog
        epilog="""
Примеры:
  %(prog)s devices --format csv
  %(prog)s mac --format excel
  %(prog)s lldp --format csv
        """,
    )

    # 2. ОБЩИЕ АРГУМЕНТЫ
    # Эти аргументы доступны для ВСЕХ команд

    parser.add_argument(
        "-v", "--verbose",           # Короткая и длинная форма
        action="store_true",         # Флаг: True если указан, иначе False
        help="Подробный вывод (DEBUG)",
    )

    parser.add_argument(
        "-d", "--devices",
        default="devices_ips.py",    # Значение по умолчанию
        help="Файл со списком устройств",
    )

    parser.add_argument(
        "-o", "--output",
        default="reports",
        help="Папка для отчётов",
    )

    parser.add_argument(
        "--transport",
        choices=["ssh2", "paramiko", "system"],  # Ограничение значений
        default="ssh2",
        help="SSH транспорт для Scrapli",
    )

    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Путь к файлу конфигурации YAML",
    )

    # 3. ПОДКОМАНДЫ (subparsers)
    # Подкоманды — это отдельные "ветки" CLI
    # devices, mac, lldp, sync-netbox, etc.

    subparsers = parser.add_subparsers(
        dest="command",              # Имя атрибута для хранения выбранной команды
        help="Команды",
    )

    # 4. НАСТРОЙКА КАЖДОЙ ПОДКОМАНДЫ

    # === DEVICES ===
    devices_parser = subparsers.add_parser(
        "devices",                   # Имя команды
        help="Сбор инвентаризации устройств",
    )
    devices_parser.add_argument(
        "--format", "-f",
        choices=["excel", "csv", "json", "raw"],
        default="csv",
        help="Формат вывода",
    )
    devices_parser.add_argument("--delimiter", default=",")
    devices_parser.add_argument("--site", default="Main")
    devices_parser.add_argument("--role", default="Switch")
    devices_parser.add_argument("--manufacturer", default="Cisco")

    # === MAC ===
    mac_parser = subparsers.add_parser("mac", help="Сбор MAC-адресов")
    mac_parser.add_argument("--format", "-f", choices=["excel", "csv", "json", "raw"], default="excel")
    mac_parser.add_argument("--mac-format", choices=["ieee", "cisco", "unix"])
    mac_parser.add_argument("--with-descriptions", action="store_true")
    mac_parser.add_argument("--no-descriptions", action="store_true")
    # ... и так далее

    # === LLDP ===
    lldp_parser = subparsers.add_parser("lldp", help="Сбор LLDP/CDP соседей")
    lldp_parser.add_argument("--format", "-f", choices=["excel", "csv", "json", "raw"], default="excel")
    lldp_parser.add_argument(
        "--protocol",
        choices=["lldp", "cdp", "both"],
        default="lldp",
        help="Протокол обнаружения",
    )

    # === SYNC-NETBOX ===
    netbox_parser = subparsers.add_parser("sync-netbox", help="Синхронизация с NetBox")
    netbox_parser.add_argument("--url", help="URL NetBox")
    netbox_parser.add_argument("--token", help="API токен")
    netbox_parser.add_argument("--interfaces", action="store_true")
    netbox_parser.add_argument("--cables", action="store_true")
    netbox_parser.add_argument("--dry-run", action="store_true")
    netbox_parser.add_argument("--sync-all", action="store_true")
    # ... много других опций

    # === PIPELINE ===
    # Pipeline имеет свои подкоманды (list, show, run, ...)
    pipeline_parser = subparsers.add_parser("pipeline", help="Управление pipelines")

    # Вложенные subparsers для pipeline
    pipeline_subparsers = pipeline_parser.add_subparsers(
        dest="pipeline_command",
        help="Подкоманды pipeline",
    )

    # pipeline list
    pl_list = pipeline_subparsers.add_parser("list", help="Показать все pipelines")
    pl_list.add_argument("--format", "-f", choices=["table", "json"], default="table")

    # pipeline run
    pl_run = pipeline_subparsers.add_parser("run", help="Запустить pipeline")
    pl_run.add_argument("name", help="Имя pipeline")
    pl_run.add_argument("--dry-run", action="store_true", default=True)
    pl_run.add_argument("--apply", action="store_true")

    return parser
```

### Типы аргументов

```python
# 1. Позиционный аргумент (обязательный)
parser.add_argument("name")
# Использование: python script.py my_name

# 2. Опциональный аргумент (начинается с -)
parser.add_argument("-v", "--verbose")
# Использование: python script.py -v или python script.py --verbose

# 3. Флаг (store_true)
parser.add_argument("--dry-run", action="store_true")
# Если указан: args.dry_run = True
# Если не указан: args.dry_run = False

# 4. С выбором значений
parser.add_argument("--format", choices=["csv", "json", "excel"])
# Ограничивает возможные значения

# 5. Со значением по умолчанию
parser.add_argument("--output", default="reports")
# Если не указан: args.output = "reports"

# 6. Обязательный опциональный
parser.add_argument("--token", required=True)
# Должен быть указан, иначе ошибка
```

---

## Главная функция: main()

**Файл:** `cli/__init__.py`

```python
def main() -> None:
    """
    Главная функция CLI.

    Последовательность:
    1. Создание парсера
    2. Парсинг аргументов
    3. Загрузка конфигурации
    4. Создание контекста выполнения
    5. Настройка логирования
    6. Выбор и выполнение команды
    7. Логирование завершения
    """
    from ..config import load_config, config
    from ..core.context import RunContext, set_current_context
    from ..core.logging import LogConfig, setup_logging_from_config

    # 1. СОЗДАНИЕ ПАРСЕРА
    parser = setup_parser()

    # 2. ПАРСИНГ АРГУМЕНТОВ
    # parse_args() читает sys.argv и возвращает Namespace
    args = parser.parse_args()
    # args — это объект с атрибутами:
    # args.command = "devices" или "mac" или "sync-netbox"
    # args.verbose = True/False
    # args.devices = "devices_ips.py"
    # args.format = "excel"
    # ...

    # 3. ЗАГРУЗКА КОНФИГУРАЦИИ
    # config.yaml содержит настройки приложения
    load_config(args.config)
    # После этого config.netbox.url, config.logging.level доступны

    # 4. СОЗДАНИЕ КОНТЕКСТА ВЫПОЛНЕНИЯ
    # RunContext — это объект для отслеживания текущего запуска
    dry_run = getattr(args, "dry_run", False)
    ctx = RunContext.create(
        dry_run=dry_run,
        triggered_by="cli",           # Источник запуска
        command=args.command or "",   # Какая команда
        base_output_dir=Path(args.output),
    )
    set_current_context(ctx)
    # Теперь ctx.run_id, ctx.dry_run доступны везде

    # 5. НАСТРОЙКА ЛОГИРОВАНИЯ
    # Приоритет: флаг -v > config.yaml > INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif config.logging and config.logging.level:
        log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    else:
        log_level = logging.INFO

    log_config = LogConfig(
        level=log_level,
        console=True,
        file_path=config.logging.file_path if config.logging else None,
    )
    setup_logging_from_config(log_config)

    logger.info(f"Run started (command={args.command}, dry_run={dry_run})")

    # 6. ВЫБОР И ВЫПОЛНЕНИЕ КОМАНДЫ
    # Простая диспетчеризация по имени команды
    if args.command == "devices":
        cmd_devices(args, ctx)
    elif args.command == "mac":
        cmd_mac(args, ctx)
    elif args.command == "lldp":
        cmd_lldp(args, ctx)
    elif args.command == "interfaces":
        cmd_interfaces(args, ctx)
    elif args.command == "inventory":
        cmd_inventory(args, ctx)
    elif args.command == "run":
        cmd_run(args, ctx)
    elif args.command == "match-mac":
        cmd_match_mac(args, ctx)
    elif args.command == "push-descriptions":
        cmd_push_descriptions(args, ctx)
    elif args.command == "sync-netbox":
        cmd_sync_netbox(args, ctx)     # ← Синхронизация с NetBox
    elif args.command == "backup":
        cmd_backup(args, ctx)
    elif args.command == "validate-fields":
        cmd_validate_fields(args, ctx)
    elif args.command == "pipeline":
        cmd_pipeline(args, ctx)        # ← Pipeline
    else:
        # Если команда не указана — показываем справку
        parser.print_help()
        return

    # 7. ЛОГИРОВАНИЕ ЗАВЕРШЕНИЯ
    logger.info(f"Run completed: {ctx.run_id} (elapsed={ctx.elapsed_human})")
```

---

## Утилиты CLI: utils.py

**Файл:** `cli/utils.py`

### load_devices() — Загрузка устройств

```python
def load_devices(devices_file: str) -> List:
    """
    Загружает список устройств из файла.

    Файл devices_ips.py должен содержать переменную devices_list:

        devices_list = [
            {"host": "192.168.1.1", "platform": "cisco_ios"},
            {"host": "192.168.1.2", "platform": "cisco_nxos"},
        ]

    Args:
        devices_file: Путь к файлу

    Returns:
        List[Device]: Список объектов Device
    """
    from ..core.device import Device

    devices_path = Path(devices_file)

    # Если файл не найден — ищем в директории модуля
    if not devices_path.exists():
        module_dir = Path(__file__).parent.parent
        devices_path = module_dir / devices_file

    if not devices_path.exists():
        logger.error(f"Файл устройств не найден: {devices_file}")
        sys.exit(1)  # Выход с кодом ошибки

    # Динамический импорт Python файла
    # importlib.util позволяет загружать модули по пути
    import importlib.util

    # Создаём "спецификацию" модуля
    spec = importlib.util.spec_from_file_location("devices", devices_path)
    # Создаём модуль из спецификации
    module = importlib.util.module_from_spec(spec)
    # Выполняем модуль (как import)
    spec.loader.exec_module(module)

    # Получаем переменную devices_list из модуля
    devices_list = getattr(module, "devices_list", None)

    if devices_list is None:
        logger.error(f"Переменная 'devices_list' не найдена в {devices_path}")
        sys.exit(1)

    # Преобразуем словари в объекты Device
    devices = []
    for d in devices_list:
        if not isinstance(d, dict):
            continue

        host = d.get("host")
        if not host:
            continue

        devices.append(
            Device(
                host=host,
                platform=d.get("platform"),
                device_type=d.get("device_type"),
                role=d.get("role"),
            )
        )

    if not devices:
        logger.error("Список устройств пуст")
        sys.exit(1)

    logger.info(f"Загружено устройств: {len(devices)}")
    return devices
```

### get_credentials() — Получение учётных данных

```python
def get_credentials():
    """
    Получает учётные данные для SSH подключения.

    Использует CredentialsManager, который проверяет:
    1. Переменные окружения (SSH_USERNAME, SSH_PASSWORD)
    2. Keyring (системное хранилище паролей)
    3. Интерактивный ввод (getpass)

    Returns:
        Credentials: Объект с username и password
    """
    from ..core.credentials import CredentialsManager

    creds_manager = CredentialsManager()
    return creds_manager.get_credentials()
```

### get_exporter() — Выбор экспортера

```python
def get_exporter(format_type: str, output_folder: str, delimiter: str = ","):
    """
    Возвращает экспортер по типу формата.

    Args:
        format_type: "excel", "csv", "json", "raw"
        output_folder: Папка для файлов
        delimiter: Разделитель для CSV

    Returns:
        BaseExporter: Экспортер
    """
    from ..exporters import CSVExporter, JSONExporter, ExcelExporter, RawExporter

    if format_type == "csv":
        return CSVExporter(output_folder=output_folder, delimiter=delimiter)
    elif format_type == "json":
        return JSONExporter(output_folder=output_folder)
    elif format_type == "raw":
        return RawExporter()  # Просто печатает в stdout
    else:
        return ExcelExporter(output_folder=output_folder)
```

### prepare_collection() — Подготовка к сбору

```python
def prepare_collection(args) -> Tuple[List, object]:
    """
    Подготавливает устройства и credentials для сбора данных.

    Удобная обёртка для частой операции.

    Args:
        args: Аргументы командной строки

    Returns:
        tuple: (devices, credentials)
    """
    devices = load_devices(args.devices)
    credentials = get_credentials()
    return devices, credentials
```

---

## Команды сбора данных: collect.py

**Файл:** `cli/commands/collect.py`

### cmd_devices() — Сбор инвентаризации

```python
def cmd_devices(args, ctx=None) -> None:
    """
    Обработчик команды devices.

    Собирает информацию об устройствах:
    - hostname
    - model
    - serial number
    - software version
    - uptime

    Команда: python -m network_collector devices --format excel
    """
    from ...collectors import DeviceInventoryCollector
    from ...fields_config import apply_fields_config

    # 1. ПОДГОТОВКА
    # Загружаем устройства и credentials
    devices, credentials = prepare_collection(args)

    # 2. СОЗДАНИЕ COLLECTOR
    collector = DeviceInventoryCollector(
        credentials=credentials,
        site=args.site,
        role=args.role,
        manufacturer=args.manufacturer,
        transport=args.transport,  # ssh2, paramiko, system
    )

    # 3. СБОР ДАННЫХ
    # collect_dicts() возвращает список словарей
    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # 4. ПРИМЕНЕНИЕ КОНФИГУРАЦИИ ПОЛЕЙ
    # fields.yaml определяет какие поля показывать и как их называть
    data = apply_fields_config(data, "devices")

    # 5. ЭКСПОРТ
    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "device_inventory")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

### cmd_mac() — Сбор MAC-адресов

```python
def cmd_mac(args, ctx=None) -> None:
    """
    Обработчик команды mac.

    Собирает MAC-адреса с таблиц коммутации.
    """
    from ...collectors import MACCollector
    from ...config import config as app_config
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    # Настройки из config.yaml или аргументов
    mac_format = args.mac_format or app_config.output.mac_format

    # Определяем флаги
    # Приоритет: CLI аргументы > config.yaml
    if args.with_descriptions:
        collect_descriptions = True
    elif args.no_descriptions:
        collect_descriptions = False
    else:
        collect_descriptions = app_config.mac.collect_descriptions

    collector = MACCollector(
        credentials=credentials,
        mac_format=mac_format,
        collect_descriptions=collect_descriptions,
        collect_trunk_ports=args.include_trunk or app_config.mac.collect_trunk_ports,
        transport=args.transport,
    )

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    data = apply_fields_config(data, "mac")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "mac_addresses")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

### cmd_lldp() — Сбор LLDP/CDP соседей

```python
def cmd_lldp(args, ctx=None) -> None:
    """
    Обработчик команды lldp.

    Собирает информацию о соседях по протоколам LLDP и/или CDP.

    Команда: python -m network_collector lldp --protocol both
    """
    from ...collectors import LLDPCollector
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    collector = LLDPCollector(
        credentials=credentials,
        protocol=args.protocol,  # "lldp", "cdp", "both"
        transport=args.transport,
    )

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    data = apply_fields_config(data, "lldp")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    report_name = f"{args.protocol}_neighbors"
    file_path = exporter.export(data, report_name)

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

---

## Команда sync-netbox: sync.py

**Файл:** `cli/commands/sync.py`

### cmd_sync_netbox() — Синхронизация с NetBox

```python
def cmd_sync_netbox(args, ctx=None) -> None:
    """
    Обработчик команды sync-netbox.

    ВАЖНО: С устройств мы только ЧИТАЕМ данные!
    Синхронизация — это выгрузка собранных данных В NetBox.

    Этапы:
    1. Подключение к NetBox
    2. Сбор данных с устройств
    3. Сравнение с существующими в NetBox
    4. Создание/обновление/удаление записей

    Команда: python -m network_collector sync-netbox --sync-all --dry-run
    """
    from ...netbox import NetBoxClient, NetBoxSync, DiffCalculator
    from ...collectors import InterfaceCollector, LLDPCollector
    from ...config import config

    # --sync-all включает ВСЕ флаги синхронизации
    if getattr(args, "sync_all", False):
        args.create_devices = True
        args.update_devices = True
        args.interfaces = True
        args.ip_addresses = True
        args.vlans = True
        args.cables = True
        args.inventory = True
        logger.info("Режим --sync-all: полная синхронизация")

    # 1. ПОДКЛЮЧЕНИЕ К NETBOX
    # Приоритет: CLI аргументы > config.yaml > env переменные
    url = args.url or config.netbox.url
    token = args.token or config.netbox.token

    try:
        client = NetBoxClient(url=url, token=token)
    except Exception as e:
        logger.error(f"Ошибка подключения к NetBox: {e}")
        return

    # Создаём синхронизатор
    sync = NetBoxSync(
        client,
        dry_run=args.dry_run,      # Режим симуляции
        create_only=args.create_only,  # Только создавать
    )

    # Загружаем устройства
    devices, credentials = prepare_collection(args)

    # Статистика
    summary = {
        "devices": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0},
        "interfaces": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0},
        "ip_addresses": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0},
        "cables": {"created": 0, "deleted": 0, "skipped": 0},
        # ...
    }

    # 2. СИНХРОНИЗАЦИЯ УСТРОЙСТВ
    if args.create_devices:
        from ...collectors import DeviceInventoryCollector

        logger.info("Синхронизация устройств в NetBox...")

        collector = DeviceInventoryCollector(
            credentials=credentials,
            transport=args.transport,
        )

        # Сбор данных с устройств
        device_infos = collector.collect(devices)

        if device_infos:
            # Показываем diff если dry-run
            if args.dry_run:
                diff_calc = DiffCalculator(client)
                diff = diff_calc.diff_devices(device_infos, site=args.site)
                if diff.has_changes:
                    logger.info(f"\n{diff.format_detailed()}")
                else:
                    logger.info("Устройства: нет изменений")

            # Синхронизация
            stats = sync.sync_devices_from_inventory(
                device_infos,
                site=args.site,
                role=args.role,
                update_existing=args.update_devices,
                cleanup=args.cleanup,
                tenant=args.tenant,
            )

            # Обновляем статистику
            for key in ("created", "updated", "deleted", "skipped"):
                summary["devices"][key] += stats.get(key, 0)

    # 3. СИНХРОНИЗАЦИЯ ИНТЕРФЕЙСОВ
    if args.interfaces:
        logger.info("Сбор интерфейсов с устройств...")

        collector = InterfaceCollector(
            credentials=credentials,
            transport=args.transport,
        )

        # Для каждого устройства отдельно
        for device in devices:
            data = collector.collect([device])
            if data:
                hostname = data[0].hostname or device.host

                # Синхронизация интерфейсов этого устройства
                stats = sync.sync_interfaces(
                    hostname,
                    data,
                    cleanup=args.cleanup_interfaces,
                )

                for key in ("created", "updated", "deleted", "skipped"):
                    summary["interfaces"][key] += stats.get(key, 0)

    # 4. СИНХРОНИЗАЦИЯ КАБЕЛЕЙ ИЗ LLDP
    if args.cables:
        logger.info(f"Сбор {args.protocol.upper()} данных...")

        collector = LLDPCollector(
            credentials=credentials,
            protocol=args.protocol,  # lldp, cdp, both
            transport=args.transport,
        )

        all_lldp_data = []
        for device in devices:
            data = collector.collect([device])
            if data:
                all_lldp_data.extend(data)

        if all_lldp_data:
            logger.info(f"Найдено {len(all_lldp_data)} соседей, создаём кабели...")

            stats = sync.sync_cables_from_lldp(
                all_lldp_data,
                skip_unknown=args.skip_unknown,
                cleanup=args.cleanup_cables,
            )

            for key in ("created", "deleted", "skipped"):
                summary["cables"][key] += stats.get(key, 0)

    # 5. СИНХРОНИЗАЦИЯ IP-АДРЕСОВ
    # (аналогично interfaces)

    # 6. СИНХРОНИЗАЦИЯ VLAN
    # (из SVI интерфейсов типа Vlan10 → VLAN 10)

    # 7. СИНХРОНИЗАЦИЯ INVENTORY
    # (модули, SFP, PSU из show inventory)

    # 8. ВЫВОД СВОДКИ
    _print_sync_summary(summary, args)
```

### _print_sync_summary() — Вывод сводки

```python
def _print_sync_summary(summary: dict, args) -> None:
    """
    Выводит красивую сводку синхронизации.

    Пример вывода:
    ============================================================
    [DRY-RUN] СВОДКА СИНХРОНИЗАЦИИ NetBox
    ============================================================
      Устройства: +3 создано, ~2 обновлено
      Интерфейсы: +15 создано, ~5 обновлено
      Кабели: +8 создано
    ------------------------------------------------------------
      ИТОГО: +26 создано, ~7 обновлено
    ============================================================
    """
    total_created = sum(s.get("created", 0) for s in summary.values())
    total_updated = sum(s.get("updated", 0) for s in summary.values())
    total_deleted = sum(s.get("deleted", 0) for s in summary.values())

    mode = "[DRY-RUN] " if args.dry_run else ""
    print(f"\n{'='*60}")
    print(f"{mode}СВОДКА СИНХРОНИЗАЦИИ NetBox")
    print(f"{'='*60}")

    category_names = {
        "devices": "Устройства",
        "interfaces": "Интерфейсы",
        "ip_addresses": "IP-адреса",
        "cables": "Кабели",
    }

    for category, stats in summary.items():
        if any(v > 0 for v in stats.values()):
            name = category_names.get(category, category)
            parts = []
            if stats.get("created", 0) > 0:
                parts.append(f"+{stats['created']} создано")
            if stats.get("updated", 0) > 0:
                parts.append(f"~{stats['updated']} обновлено")
            if stats.get("deleted", 0) > 0:
                parts.append(f"-{stats['deleted']} удалено")
            print(f"  {name}: {', '.join(parts)}")

    print(f"{'='*60}\n")
```

---

## Команда pipeline: pipeline.py

**Файл:** `cli/commands/pipeline.py`

### cmd_pipeline() — Диспетчер подкоманд

```python
def cmd_pipeline(args, ctx=None) -> None:
    """
    Обработчик команды pipeline.

    Pipeline имеет свои подкоманды:
    - list     — показать все pipelines
    - show     — показать детали pipeline
    - run      — запустить pipeline
    - validate — валидировать pipeline
    - create   — создать pipeline из YAML
    - delete   — удалить pipeline
    """
    subcommand = getattr(args, "pipeline_command", None)

    if subcommand == "list":
        _cmd_list(args)
    elif subcommand == "show":
        _cmd_show(args)
    elif subcommand == "run":
        _cmd_run(args, ctx)
    elif subcommand == "validate":
        _cmd_validate(args)
    elif subcommand == "create":
        _cmd_create(args)
    elif subcommand == "delete":
        _cmd_delete(args)
    else:
        print("Usage: pipeline {list|show|run|validate|create|delete}")
```

### _cmd_run() — Запуск pipeline

```python
def _cmd_run(args, ctx=None) -> None:
    """
    Запустить pipeline.

    Команда: python -m network_collector pipeline run default --apply
    """
    from ..utils import load_devices, get_credentials
    from ...config import config
    from ...core.pipeline.models import Pipeline, StepStatus
    from ...core.pipeline.executor import PipelineExecutor

    name = args.name
    if not name:
        print("Error: pipeline name required")
        return

    # 1. ЗАГРУЗКА PIPELINE
    pipeline = _load_pipeline(name)
    if not pipeline:
        print(f"Error: pipeline '{name}' not found")
        return

    # 2. ВАЛИДАЦИЯ
    errors = pipeline.validate()
    if errors:
        _print_validation_result(pipeline, errors)
        return

    # 3. ЗАГРУЗКА УСТРОЙСТВ
    devices = load_devices(args.devices)
    if not devices:
        print("No devices to process")
        return

    # 4. ПОЛУЧЕНИЕ CREDENTIALS
    credentials = get_credentials(args)

    # 5. КОНФИГУРАЦИЯ NETBOX
    netbox_config = {}
    if config.netbox:
        netbox_config["url"] = config.netbox.url
        netbox_config["token"] = config.netbox.token

    # Переопределение из аргументов
    if args.netbox_url:
        netbox_config["url"] = args.netbox_url
    if args.netbox_token:
        netbox_config["token"] = args.netbox_token

    # 6. DRY-RUN РЕЖИМ
    dry_run = args.dry_run
    if args.apply:
        dry_run = False

    print(f"\nRunning pipeline: {pipeline.name}")
    print(f"Devices: {len(devices)}")
    print(f"Dry-run: {dry_run}")
    print("-" * 40)

    # 7. CALLBACKS ДЛЯ ПРОГРЕССА
    def on_step_start(step):
        print(f"  ► {step.id}...")

    def on_step_complete(step, result):
        icon = "✓" if result.status == StepStatus.COMPLETED else "✗"
        print(f"  {icon} {step.id} ({result.duration_ms}ms)")
        if result.error:
            print(f"    Error: {result.error}")

    # 8. ВЫПОЛНЕНИЕ
    executor = PipelineExecutor(
        pipeline,
        dry_run=dry_run,
        on_step_start=on_step_start,
        on_step_complete=on_step_complete,
    )

    # Credentials как словарь
    creds_dict = {
        "username": credentials.username,
        "password": credentials.password,
    }

    result = executor.run(
        devices=devices,
        credentials=creds_dict,
        netbox_config=netbox_config,
    )

    # 9. ВЫВОД РЕЗУЛЬТАТА
    _print_run_result(result, args.format)
```

---

## Полная цепочка: от команды до NetBox

### Пример: `python -m network_collector sync-netbox --interfaces`

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ТЕРМИНАЛ                                                     │
│                                                                 │
│    $ python -m network_collector sync-netbox --interfaces       │
│                                                                 │
│    Python ищет network_collector/__main__.py и запускает его   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. __main__.py                                                  │
│                                                                 │
│    from .cli import main                                        │
│    main()  # Вызываем главную функцию CLI                      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. cli/__init__.py → main()                                     │
│                                                                 │
│    parser = setup_parser()                                      │
│    args = parser.parse_args()                                   │
│    # args.command = "sync-netbox"                              │
│    # args.interfaces = True                                     │
│                                                                 │
│    load_config()  # Загружаем config.yaml                      │
│    ctx = RunContext.create(...)                                │
│    setup_logging_from_config(...)                              │
│                                                                 │
│    if args.command == "sync-netbox":                           │
│        cmd_sync_netbox(args, ctx)  # ← Переходим сюда          │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. cli/commands/sync.py → cmd_sync_netbox()                     │
│                                                                 │
│    # Подключаемся к NetBox                                      │
│    client = NetBoxClient(url=url, token=token)                 │
│    sync = NetBoxSync(client, dry_run=args.dry_run)             │
│                                                                 │
│    # Загружаем устройства                                       │
│    devices, credentials = prepare_collection(args)             │
│    # devices = [Device(host="192.168.1.1", ...), ...]         │
│                                                                 │
│    # Синхронизация интерфейсов                                  │
│    if args.interfaces:                                          │
│        collector = InterfaceCollector(credentials=credentials) │
│        for device in devices:                                   │
│            data = collector.collect([device])                  │
│            stats = sync.sync_interfaces(hostname, data)        │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. collectors/interfaces.py → InterfaceCollector.collect()      │
│                                                                 │
│    # Подключаемся к устройству по SSH                          │
│    connection = Connection(device, credentials)                │
│    connection.connect()                                         │
│                                                                 │
│    # Выполняем команды                                          │
│    output = connection.send_command("show interfaces")         │
│    output += connection.send_command("show interfaces status") │
│                                                                 │
│    # Парсим вывод (NTC Templates)                              │
│    parsed = parse_output(platform, command, output)            │
│                                                                 │
│    # Конвертируем в модели                                      │
│    interfaces = [Interface(name=..., status=...) for ...]     │
│                                                                 │
│    connection.disconnect()                                      │
│    return interfaces                                            │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. netbox/sync/interfaces.py → sync_interfaces()                │
│                                                                 │
│    # Находим устройство в NetBox                                │
│    device = client.get_device_by_name(hostname)                │
│                                                                 │
│    # Получаем существующие интерфейсы                           │
│    existing = client.get_interfaces(device_id=device.id)       │
│                                                                 │
│    # Сравниваем                                                 │
│    comparator = SyncComparator()                               │
│    diff = comparator.compare_interfaces(local, existing)       │
│                                                                 │
│    # Применяем изменения                                        │
│    for item in diff.to_create:                                 │
│        client.create_interface(device.id, name=item.name, ...) │
│    for item in diff.to_update:                                 │
│        client.update_interface(item.id, ...)                   │
│    for item in diff.to_delete:                                 │
│        item.delete()                                            │
│                                                                 │
│    return {"created": 5, "updated": 3, "deleted": 1}           │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. netbox/client.py → NetBoxClient                              │
│                                                                 │
│    # Обёртка над pynetbox                                       │
│    class NetBoxClient:                                          │
│        def __init__(self, url, token):                         │
│            self.api = pynetbox.api(url, token=token)           │
│                                                                 │
│        def create_interface(self, device_id, name, **kwargs):  │
│            return self.api.dcim.interfaces.create({            │
│                "device": device_id,                             │
│                "name": name,                                    │
│                **kwargs                                         │
│            })                                                   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 8. NetBox REST API                                              │
│                                                                 │
│    POST https://netbox.local/api/dcim/interfaces/              │
│    Authorization: Token abc123                                  │
│    Content-Type: application/json                               │
│                                                                 │
│    {                                                            │
│      "device": 42,                                              │
│      "name": "GigabitEthernet0/1",                             │
│      "type": "1000base-t",                                      │
│      "enabled": true,                                           │
│      "description": "Uplink to core"                           │
│    }                                                            │
│                                                                 │
│    Response: 201 Created                                        │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 9. Возврат к cmd_sync_netbox()                                  │
│                                                                 │
│    # Накапливаем статистику                                     │
│    summary["interfaces"]["created"] += stats["created"]        │
│    summary["interfaces"]["updated"] += stats["updated"]        │
│                                                                 │
│    # Выводим сводку                                             │
│    _print_sync_summary(summary, args)                          │
│                                                                 │
│    ============================================================ │
│    СВОДКА СИНХРОНИЗАЦИИ NetBox                                  │
│    ============================================================ │
│      Интерфейсы: +5 создано, ~3 обновлено, -1 удалено          │
│    ============================================================ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Примеры с объяснениями

### Пример 1: Сбор MAC-адресов

```bash
python -m network_collector mac --format excel --mac-format ieee
```

**Цепочка вызовов:**
```python
# 1. main() парсит аргументы:
args.command = "mac"
args.format = "excel"
args.mac_format = "ieee"

# 2. Вызывается cmd_mac(args, ctx)

# 3. Внутри cmd_mac():
devices, credentials = prepare_collection(args)
# devices = [Device(host="192.168.1.1"), Device(host="192.168.1.2")]

collector = MACCollector(
    credentials=credentials,
    mac_format="ieee",  # AA:BB:CC:DD:EE:FF
)

data = collector.collect_dicts(devices)
# data = [
#   {"hostname": "switch-01", "interface": "Gi0/1", "mac": "AA:BB:CC:DD:EE:FF", ...},
#   {"hostname": "switch-01", "interface": "Gi0/2", "mac": "11:22:33:44:55:66", ...},
# ]

exporter = get_exporter("excel", "reports", ",")
# exporter = ExcelExporter(output_folder="reports")

file_path = exporter.export(data, "mac_addresses")
# file_path = "reports/mac_addresses_20240115_143022.xlsx"
```

### Пример 2: Pipeline с dry-run

```bash
python -m network_collector pipeline run full-sync --dry-run
```

**Цепочка вызовов:**
```python
# 1. main() → cmd_pipeline(args, ctx)

# 2. cmd_pipeline() → _cmd_run(args, ctx)

# 3. _cmd_run():
pipeline = _load_pipeline("full-sync")
# Pipeline из pipelines/full-sync.yaml

errors = pipeline.validate()
# Проверка на ошибки

devices = load_devices("devices_ips.py")
credentials = get_credentials()

executor = PipelineExecutor(
    pipeline,
    dry_run=True,  # Режим симуляции
    on_step_start=lambda step: print(f"► {step.id}..."),
)

result = executor.run(
    devices=devices,
    credentials={"username": "admin", "password": "***"},
    netbox_config={"url": "https://netbox.local", "token": "***"},
)

# result.status = StepStatus.COMPLETED
# result.steps = [
#   StepResult(step_id="collect_devices", status=COMPLETED, duration_ms=5000),
#   StepResult(step_id="sync_devices", status=COMPLETED, duration_ms=3000),
# ]
```

### Пример 3: Полная синхронизация

```bash
python -m network_collector sync-netbox --sync-all --site Office --dry-run
```

**Что происходит:**
1. `--sync-all` включает все флаги: devices, interfaces, ip_addresses, vlans, cables, inventory
2. `--site Office` — все устройства будут привязаны к сайту "Office"
3. `--dry-run` — никаких изменений в NetBox, только показ что будет сделано

```python
# В cmd_sync_netbox():
if args.sync_all:
    args.create_devices = True
    args.update_devices = True
    args.interfaces = True
    args.ip_addresses = True
    args.vlans = True
    args.cables = True
    args.inventory = True

# Последовательно выполняются:
# 1. Сбор и синхронизация устройств
# 2. Сбор и синхронизация интерфейсов (для каждого устройства)
# 3. Сбор и синхронизация IP-адресов
# 4. Сбор и синхронизация VLAN из SVI
# 5. Сбор LLDP/CDP и создание кабелей
# 6. Сбор и синхронизация inventory
```

---

## Резюме

### Ключевые файлы

| Файл | Описание |
|------|----------|
| `__main__.py` | Точка входа: `python -m network_collector` |
| `cli/__init__.py` | `main()` и `setup_parser()` |
| `cli/utils.py` | `load_devices`, `get_credentials`, `get_exporter` |
| `cli/commands/collect.py` | devices, mac, lldp, interfaces, inventory |
| `cli/commands/sync.py` | sync-netbox |
| `cli/commands/pipeline.py` | pipeline (list, show, run, ...) |

### Поток выполнения

```
Команда → __main__.py → main() → setup_parser() → parse_args()
                                        ↓
                              cmd_<command>(args, ctx)
                                        ↓
                              Collector.collect()
                                        ↓
                              Exporter.export() или Sync.sync_*()
```

### Основные концепции

1. **argparse** — парсинг аргументов командной строки
2. **subparsers** — подкоманды (devices, mac, sync-netbox, ...)
3. **Collector** — сбор данных с устройств по SSH
4. **Exporter** — сохранение в файлы (Excel, CSV, JSON)
5. **NetBoxSync** — синхронизация с NetBox API
6. **Pipeline** — автоматизация нескольких операций
