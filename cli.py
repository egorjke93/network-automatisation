"""
CLI интерфейс для network_collector.

Предоставляет командную строку для всех функций утилиты.

Примеры использования:
    # Сбор инвентаризации устройств
    python -m network_collector devices --format csv

    # Сбор MAC-адресов
    python -m network_collector mac --format excel

    # Сбор LLDP соседей в CSV
    python -m network_collector lldp --format csv --delimiter ";"

    # Сбор интерфейсов
    python -m network_collector interfaces --format json

    # Синхронизация с NetBox
    python -m network_collector sync-netbox --interfaces

    # Выполнить произвольную команду с NTC Templates
    python -m network_collector run "show version" --fields hostname,version
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import List

# Логгер будет настроен в main() после загрузки конфига
logger = logging.getLogger(__name__)


def setup_parser() -> argparse.ArgumentParser:
    """
    Создаёт парсер аргументов командной строки.

    Returns:
        ArgumentParser: Настроенный парсер
    """
    parser = argparse.ArgumentParser(
        prog="network_collector",
        description="Утилита для сбора данных с сетевых устройств (Scrapli + NTC Templates)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s devices --format csv
  %(prog)s mac --format excel --mac-format ieee
  %(prog)s lldp --format csv --delimiter ";"
  %(prog)s interfaces --fields interface,status,description
  %(prog)s run "show version" --platform cisco_ios
        """,
    )

    # Общие аргументы
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Подробный вывод (DEBUG)",
    )
    parser.add_argument(
        "-d",
        "--devices",
        default="devices_ips.py",
        help="Файл со списком устройств (default: devices_ips.py)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="reports",
        help="Папка для отчётов (default: reports)",
    )
    parser.add_argument(
        "--transport",
        choices=["ssh2", "paramiko", "system"],
        default="ssh2",
        help="SSH транспорт для Scrapli (default: ssh2)",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Путь к файлу конфигурации YAML (default: config.yaml)",
    )

    # Подкоманды
    subparsers = parser.add_subparsers(dest="command", help="Команды")

    # === DEVICES (инвентаризация) ===
    devices_parser = subparsers.add_parser("devices", help="Сбор инвентаризации устройств")
    devices_parser.add_argument(
        "--format",
        "-f",
        choices=["excel", "csv", "json"],
        default="csv",
        help="Формат вывода",
    )
    devices_parser.add_argument(
        "--delimiter",
        default=",",
        help="Разделитель для CSV",
    )
    devices_parser.add_argument(
        "--site",
        default="Main",
        help="Сайт для NetBox",
    )
    devices_parser.add_argument(
        "--role",
        default="Switch",
        help="Роль устройства",
    )
    devices_parser.add_argument(
        "--manufacturer",
        default="Cisco",
        help="Производитель по умолчанию",
    )

    # === MAC ===
    mac_parser = subparsers.add_parser("mac", help="Сбор MAC-адресов")
    mac_parser.add_argument(
        "--format",
        "-f",
        choices=["excel", "csv", "json"],
        default="excel",
        help="Формат вывода",
    )
    mac_parser.add_argument(
        "--delimiter",
        default=",",
        help="Разделитель для CSV",
    )
    mac_parser.add_argument(
        "--mac-format",
        choices=["ieee", "cisco", "unix"],
        default=None,
        help="Формат MAC-адреса (ieee/cisco/unix). По умолчанию из config.py",
    )
    mac_parser.add_argument(
        "--fields",
        help="Поля для вывода (через запятую)",
    )
    mac_parser.add_argument(
        "--with-descriptions",
        action="store_true",
        help="Собирать описания интерфейсов (по умолчанию из config.yaml)",
    )
    mac_parser.add_argument(
        "--no-descriptions",
        action="store_true",
        help="Не собирать описания интерфейсов",
    )
    mac_parser.add_argument(
        "--include-trunk",
        action="store_true",
        help="Включать trunk порты (по умолчанию из config.yaml)",
    )
    mac_parser.add_argument(
        "--exclude-trunk",
        action="store_true",
        help="Исключать trunk порты",
    )
    mac_parser.add_argument(
        "--match-file",
        help="Excel файл для сопоставления MAC с хостами",
    )
    mac_parser.add_argument(
        "--per-device",
        action="store_true",
        help="Сохранять отдельный файл для каждого устройства",
    )
    mac_parser.add_argument(
        "--with-port-security",
        action="store_true",
        help="Собирать sticky MAC из port-security (offline устройства)",
    )

    # === LLDP ===
    lldp_parser = subparsers.add_parser("lldp", help="Сбор LLDP/CDP соседей")
    lldp_parser.add_argument(
        "--format",
        "-f",
        choices=["excel", "csv", "json"],
        default="excel",
        help="Формат вывода",
    )
    lldp_parser.add_argument(
        "--delimiter",
        default=",",
        help="Разделитель для CSV",
    )
    lldp_parser.add_argument(
        "--protocol",
        choices=["lldp", "cdp", "both"],
        default="lldp",
        help="Протокол обнаружения",
    )
    lldp_parser.add_argument(
        "--fields",
        help="Поля для вывода (через запятую)",
    )

    # === Interfaces ===
    intf_parser = subparsers.add_parser(
        "interfaces", help="Сбор информации об интерфейсах"
    )
    intf_parser.add_argument(
        "--format",
        "-f",
        choices=["excel", "csv", "json"],
        default="excel",
        help="Формат вывода",
    )
    intf_parser.add_argument(
        "--delimiter",
        default=",",
        help="Разделитель для CSV",
    )
    intf_parser.add_argument(
        "--fields",
        help="Поля для вывода (через запятую)",
    )

    # === Inventory ===
    inv_parser = subparsers.add_parser(
        "inventory", help="Сбор инвентаризации (модули, трансиверы, серийники)"
    )
    inv_parser.add_argument(
        "--format",
        "-f",
        choices=["excel", "csv", "json"],
        default="json",
        help="Формат вывода",
    )
    inv_parser.add_argument(
        "--delimiter",
        default=",",
        help="Разделитель для CSV",
    )
    inv_parser.add_argument(
        "--fields",
        help="Поля для вывода (через запятую)",
    )

    # === Run (произвольная команда) ===
    run_parser = subparsers.add_parser("run", help="Выполнить произвольную команду")
    run_parser.add_argument(
        "cmd",
        help="Команда для выполнения (например: 'show version')",
    )
    run_parser.add_argument(
        "--platform",
        help="Платформа для NTC Templates (cisco_ios, arista_eos, etc.)",
    )
    run_parser.add_argument(
        "--format",
        "-f",
        choices=["excel", "csv", "json", "raw"],
        default="json",
        help="Формат вывода",
    )
    run_parser.add_argument(
        "--fields",
        help="Поля для извлечения из NTC (через запятую)",
    )

    # === Match MAC (сопоставление) ===
    match_parser = subparsers.add_parser(
        "match-mac", help="Сопоставление MAC-адресов с таблицей хостов"
    )
    match_parser.add_argument(
        "--mac-file",
        required=True,
        help="Excel файл с MAC-адресами (результат команды mac)",
    )
    match_parser.add_argument(
        "--hosts-file",
        required=True,
        help="Excel файл со справочником хостов (GLPI, etc.)",
    )
    match_parser.add_argument(
        "--hosts-folder",
        help="Папка с несколькими справочниками хостов",
    )
    match_parser.add_argument(
        "--mac-column",
        default="MAC",
        help="Название колонки с MAC в справочнике",
    )
    match_parser.add_argument(
        "--name-column",
        default="Name",
        help="Название колонки с именем хоста",
    )
    match_parser.add_argument(
        "--output",
        "-o",
        default="matched_data.xlsx",
        help="Файл для сохранения результатов",
    )

    # === Push descriptions (применение описаний) ===
    push_parser = subparsers.add_parser(
        "push-descriptions", help="Применение описаний интерфейсов на устройствах"
    )
    push_parser.add_argument(
        "--matched-file",
        required=True,
        help="Excel файл с результатами сопоставления",
    )
    push_parser.add_argument(
        "--only-empty",
        action="store_true",
        help="Только для портов без текущего описания",
    )
    push_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Перезаписывать существующие описания",
    )
    push_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Режим симуляции (default: True)",
    )
    push_parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить изменения (отключает dry-run)",
    )

    # === NetBox Sync ===
    netbox_parser = subparsers.add_parser("sync-netbox", help="Синхронизация с NetBox")
    netbox_parser.add_argument(
        "--url",
        help="URL NetBox (или env NETBOX_URL)",
    )
    netbox_parser.add_argument(
        "--token",
        help="API токен (или env NETBOX_TOKEN)",
    )
    netbox_parser.add_argument(
        "--interfaces",
        action="store_true",
        help="Синхронизировать интерфейсы",
    )
    netbox_parser.add_argument(
        "--cables",
        action="store_true",
        help="Создать кабели из LLDP/CDP данных",
    )
    netbox_parser.add_argument(
        "--protocol",
        choices=["lldp", "cdp", "both"],
        default="both",
        help="Протокол для сбора соседей (default: both)",
    )
    netbox_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Режим симуляции (без изменений)",
    )
    netbox_parser.add_argument(
        "--create-only",
        action="store_true",
        help="Только создавать новые объекты",
    )
    netbox_parser.add_argument(
        "--skip-unknown",
        action="store_true",
        default=True,
        help="Пропускать соседей без hostname (default: True)",
    )
    netbox_parser.add_argument(
        "--ip-addresses",
        action="store_true",
        help="Синхронизировать IP-адреса",
    )
    netbox_parser.add_argument(
        "--create-devices",
        action="store_true",
        help="Создать устройства в NetBox из инвентаризации",
    )
    netbox_parser.add_argument(
        "--site",
        default=None,
        help="Сайт для создаваемых устройств (из конфига если не указан)",
    )
    netbox_parser.add_argument(
        "--role",
        default=None,
        help="Роль для создаваемых устройств (из конфига если не указан)",
    )
    netbox_parser.add_argument(
        "--update-devices",
        action="store_true",
        help="Обновлять существующие устройства (serial, model)",
    )
    netbox_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Удалять устройства из NetBox которых нет в списке",
    )
    netbox_parser.add_argument(
        "--tenant",
        help="Арендатор (tenant) - только устройства этого tenant будут удаляться при --cleanup",
    )
    netbox_parser.add_argument(
        "--vlans",
        action="store_true",
        help="Синхронизировать VLAN из SVI интерфейсов (Vlan10 → VLAN 10)",
    )
    netbox_parser.add_argument(
        "--inventory",
        action="store_true",
        help="Синхронизировать inventory (модули, SFP, PSU) из show inventory",
    )
    netbox_parser.add_argument(
        "--sync-all",
        action="store_true",
        help="Полная синхронизация: devices → interfaces → ip-addresses → vlans → cables → inventory",
    )
    netbox_parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Показать детальный diff изменений перед применением",
    )

    # === Backup (резервное копирование) ===
    backup_parser = subparsers.add_parser("backup", help="Резервное копирование конфигураций")
    backup_parser.add_argument(
        "--output",
        "-o",
        default="backups",
        help="Папка для сохранения конфигураций (default: backups)",
    )

    return parser


def load_devices(devices_file: str) -> List:
    """
    Загружает список устройств из файла.

    Args:
        devices_file: Путь к файлу с устройствами

    Returns:
        List: Список устройств

    Raises:
        SystemExit: Если файл не найден или содержит ошибки
    """
    from .core.device import Device

    devices_path = Path(devices_file)

    # Если не найден — ищем в директории модуля
    if not devices_path.exists():
        module_dir = Path(__file__).parent
        devices_path = module_dir / devices_file

    if not devices_path.exists():
        logger.error(f"Файл устройств не найден: {devices_file}")
        sys.exit(1)

    # Импортируем devices_list из файла
    import importlib.util

    try:
        spec = importlib.util.spec_from_file_location("devices", devices_path)
        if spec is None or spec.loader is None:
            logger.error(f"Не удалось загрузить спецификацию модуля: {devices_path}")
            sys.exit(1)

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except SyntaxError as e:
        logger.error(f"Синтаксическая ошибка в файле {devices_path}: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Ошибка загрузки файла {devices_path}: {e}")
        sys.exit(1)

    devices_list = getattr(module, "devices_list", None)

    if devices_list is None:
        logger.error(f"Переменная 'devices_list' не найдена в {devices_path}")
        sys.exit(1)

    if not isinstance(devices_list, list):
        logger.error(f"'devices_list' должен быть списком, получен {type(devices_list).__name__}")
        sys.exit(1)

    # Преобразуем в объекты Device
    devices = []
    for idx, d in enumerate(devices_list):
        if not isinstance(d, dict):
            logger.warning(f"Пропущен элемент #{idx}: ожидался dict, получен {type(d).__name__}")
            continue

        host = d.get("host")
        if not host:
            logger.warning(f"Пропущен элемент #{idx}: отсутствует 'host'")
            continue

        # Новый формат (рекомендуется):
        # {"host": "10.0.0.1", "platform": "cisco_iosxe", "device_type": "C9200L-24P-4X", "role": "Switch"}
        platform = d.get("platform")
        device_type = d.get("device_type")
        role = d.get("role")

        # Backward compatibility: если platform не указан, используем device_type
        # (в Device.__post_init__ есть логика конвертации device_type → platform)
        if not platform and not device_type:
            logger.warning(f"Устройство {host}: ни 'platform' ни 'device_type' не указаны, используется 'cisco_ios'")
            platform = "cisco_ios"

        devices.append(
            Device(
                host=host,
                platform=platform,
                device_type=device_type,
                role=role,
            )
        )

    if not devices:
        logger.error("Список устройств пуст или все записи некорректны")
        sys.exit(1)

    logger.info(f"Загружено устройств: {len(devices)}")
    return devices


def get_exporter(format_type: str, output_folder: str, delimiter: str = ","):
    """
    Возвращает экспортер по типу формата.

    Args:
        format_type: Тип формата (excel, csv, json)
        output_folder: Папка для вывода
        delimiter: Разделитель для CSV

    Returns:
        BaseExporter: Экспортер
    """
    from .exporters import CSVExporter, JSONExporter, ExcelExporter

    if format_type == "csv":
        return CSVExporter(output_folder=output_folder, delimiter=delimiter)
    elif format_type == "json":
        return JSONExporter(output_folder=output_folder)
    else:
        return ExcelExporter(output_folder=output_folder)


def get_credentials():
    """
    Получает учётные данные для подключения.

    Returns:
        Credentials: Объект с учётными данными
    """
    from .core.credentials import CredentialsManager

    creds_manager = CredentialsManager()
    return creds_manager.get_credentials()


def prepare_collection(args):
    """
    Подготавливает устройства и credentials для сбора данных.

    Args:
        args: Аргументы командной строки

    Returns:
        tuple: (devices, credentials)
    """
    devices = load_devices(args.devices)
    credentials = get_credentials()
    return devices, credentials


def cmd_devices(args, ctx=None) -> None:
    """Обработчик команды devices (инвентаризация)."""
    from .collectors import DeviceInventoryCollector
    from .fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    # Создаём коллектор
    collector = DeviceInventoryCollector(
        credentials=credentials,
        site=args.site,
        role=args.role,
        manufacturer=args.manufacturer,
        transport=args.transport,
    )

    # Собираем данные (как словари для экспорта)
    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # Применяем конфигурацию полей
    data = apply_fields_config(data, "devices")

    # Экспортируем
    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "device_inventory")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_mac(args, ctx=None) -> None:
    """Обработчик команды mac."""
    from .collectors import MACCollector
    from .config import config as app_config
    from .fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    # Парсим поля
    fields = args.fields.split(",") if args.fields else None

    # Берём mac_format из аргументов или из конфига
    mac_format = args.mac_format or app_config.output.mac_format

    # Настройки из config.yaml (по умолчанию)
    # CLI флаги переопределяют:
    #   --with-descriptions / --no-descriptions
    #   --include-trunk / --exclude-trunk
    config_descriptions = True
    config_trunk = False
    if app_config.mac:
        config_descriptions = app_config.mac.collect_descriptions if app_config.mac.collect_descriptions is not None else True
        config_trunk = app_config.mac.collect_trunk_ports if app_config.mac.collect_trunk_ports is not None else False

    # Определяем collect_descriptions
    if args.with_descriptions:
        collect_descriptions = True
    elif hasattr(args, 'no_descriptions') and args.no_descriptions:
        collect_descriptions = False
    else:
        collect_descriptions = config_descriptions

    # Определяем collect_trunk
    if args.include_trunk:
        collect_trunk = True
    elif hasattr(args, 'exclude_trunk') and args.exclude_trunk:
        collect_trunk = False
    else:
        collect_trunk = config_trunk

    # Определяем collect_port_security
    config_port_security = False
    if app_config.mac:
        config_port_security = app_config.mac.collect_port_security if app_config.mac.collect_port_security is not None else False

    collect_port_security = getattr(args, 'with_port_security', False) or config_port_security

    # Создаём коллектор
    collector = MACCollector(
        credentials=credentials,
        mac_format=mac_format,
        ntc_fields=fields,
        collect_descriptions=collect_descriptions,
        collect_trunk_ports=collect_trunk,
        collect_port_security=collect_port_security,
        transport=args.transport,
    )

    # Собираем данные (как словари для экспорта)
    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # Сопоставляем с файлом если указан
    if args.match_file:
        try:
            from .configurator import DescriptionMatcher
            matcher = DescriptionMatcher()
            matcher.load_hosts_file(args.match_file)
            matched = matcher.match_mac_data(data)
            # Преобразуем MatchedEntry обратно в dict
            data = []
            for entry in matched:
                row = {
                    "hostname": entry.hostname,
                    "device_ip": entry.device_ip,
                    "interface": entry.interface,
                    "mac": entry.mac,
                    "vlan": entry.vlan,
                    "description": entry.current_description,
                    "host_name": entry.host_name,
                    "matched": "Yes" if entry.matched else "No",
                }
                data.append(row)
            logger.info(f"Данные обогащены из {args.match_file}")
        except Exception as e:
            logger.warning(f"Ошибка сопоставления: {e}")

    # Применяем конфигурацию полей
    data = apply_fields_config(data, "mac")

    # Экспортируем
    exporter = get_exporter(args.format, args.output, args.delimiter)

    # per_device из аргументов или из конфига
    per_device = getattr(args, "per_device", False) or app_config.output.per_device

    if per_device:
        # Сохраняем по отдельности для каждого устройства
        from collections import defaultdict

        # Группируем данные по hostname
        data_by_device = defaultdict(list)
        for row in data:
            hostname = row.get("hostname", "unknown")
            data_by_device[hostname].append(row)

        # Сохраняем каждое устройство в отдельный файл
        for hostname, device_data in data_by_device.items():
            safe_hostname = hostname.replace("/", "_").replace("\\", "_")
            file_path = exporter.export(device_data, f"mac_{safe_hostname}")
            if file_path:
                logger.info(f"Отчёт сохранён: {file_path}")
    else:
        # Один общий файл
        file_path = exporter.export(data, "mac_addresses")
        if file_path:
            logger.info(f"Отчёт сохранён: {file_path}")


def cmd_lldp(args, ctx=None) -> None:
    """Обработчик команды lldp."""
    from .collectors import LLDPCollector
    from .fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    collector = LLDPCollector(
        credentials=credentials,
        protocol=args.protocol,
        ntc_fields=fields,
        transport=args.transport,
    )

    # Собираем данные (как словари для экспорта)
    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # Применяем конфигурацию полей (фильтрация, переименование, порядок)
    data = apply_fields_config(data, "lldp")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    report_name = f"{args.protocol}_neighbors"
    file_path = exporter.export(data, report_name)

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_interfaces(args, ctx=None) -> None:
    """Обработчик команды interfaces."""
    from .collectors import InterfaceCollector
    from .fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    collector = InterfaceCollector(
        credentials=credentials,
        ntc_fields=fields,
        transport=args.transport,
    )

    # Собираем данные (как словари для экспорта)
    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # Применяем конфигурацию полей
    data = apply_fields_config(data, "interfaces")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "interfaces")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_inventory(args, ctx=None) -> None:
    """Обработчик команды inventory."""
    from .collectors import InventoryCollector
    from .fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    collector = InventoryCollector(
        credentials=credentials,
        ntc_fields=fields,
        transport=args.transport,
    )

    # Собираем данные (как словари для экспорта)
    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # Применяем конфигурацию полей
    data = apply_fields_config(data, "inventory")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "inventory")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_run(args, ctx=None) -> None:
    """Обработчик команды run (произвольная команда)."""
    from .core.connection import ConnectionManager, get_ntc_platform
    from .parsers.textfsm_parser import NTCParser, NTC_AVAILABLE

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    conn_manager = ConnectionManager(transport=args.transport)
    all_data = []

    for device in devices:
        try:
            with conn_manager.connect(device, credentials) as conn:
                hostname = conn_manager.get_hostname(conn)
                response = conn.send_command(args.cmd)
                output = response.result

                if args.format == "raw":
                    # Сырой вывод
                    print(f"\n=== {hostname} ({device.host}) ===")
                    print(output)
                    continue

                # Парсим с NTC Templates
                if NTC_AVAILABLE:
                    parser = NTCParser()
                    platform = args.platform or get_ntc_platform(device.platform)
                    try:
                        parsed = parser.parse(
                            output=output,
                            platform=platform,
                            command=args.cmd,
                            fields=fields,
                        )
                        for row in parsed:
                            row["hostname"] = hostname
                            row["device_ip"] = device.host
                        all_data.extend(parsed)
                    except Exception as e:
                        logger.warning(
                            f"NTC парсинг не удался для {platform}/{args.cmd}: {e}"
                        )
                        # Возвращаем сырой вывод
                        all_data.append(
                            {
                                "hostname": hostname,
                                "device_ip": device.host,
                                "raw_output": output,
                            }
                        )
                else:
                    all_data.append(
                        {
                            "hostname": hostname,
                            "device_ip": device.host,
                            "raw_output": output,
                        }
                    )

        except Exception as e:
            logger.error(f"Ошибка на {device.host}: {e}")

    if args.format == "raw":
        return

    if not all_data:
        logger.warning("Нет данных для экспорта")
        return

    exporter = get_exporter(args.format, args.output)
    file_path = exporter.export(all_data, "custom_command")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_match_mac(args, ctx=None) -> None:
    """Обработчик команды match-mac (сопоставление MAC с хостами)."""
    from .configurator import DescriptionMatcher
    import pandas as pd

    # Загружаем MAC-данные
    logger.info(f"Загрузка MAC-данных из {args.mac_file}...")
    mac_df = pd.read_excel(args.mac_file)
    # Нормализуем имена колонок к lowercase и заменяем пробелы на underscore
    mac_df.columns = [col.lower().replace(" ", "_") for col in mac_df.columns]
    mac_data = mac_df.to_dict("records")
    logger.info(f"Загружено {len(mac_data)} записей MAC")

    # Создаём матчер
    matcher = DescriptionMatcher()

    # Загружаем справочник хостов
    if args.hosts_folder:
        matcher.load_hosts_folder(
            args.hosts_folder,
            mac_column=args.mac_column,
            name_column=args.name_column,
        )
    else:
        matcher.load_hosts_file(
            args.hosts_file,
            mac_column=args.mac_column,
            name_column=args.name_column,
        )

    # Сопоставляем (указываем имена полей из MAC файла)
    matched = matcher.match_mac_data(
        mac_data,
        mac_field="mac",
        hostname_field="device",  # В экспорте колонка называется DEVICE -> device
        interface_field="port",   # В экспорте колонка называется PORT -> port
        vlan_field="vlan",
        description_field="description",
    )

    # Сохраняем результат
    output_file = args.output
    matcher.save_matched(output_file)

    # Статистика
    stats = matcher.get_stats()
    logger.info("=== СТАТИСТИКА ===")
    logger.info(f"Справочник хостов: {stats['reference_hosts']} записей")
    logger.info(f"MAC-адресов: {stats['total_mac_entries']}")
    logger.info(f"Сопоставлено: {stats['matched']} ({stats['match_rate']})")
    logger.info(f"Не сопоставлено: {stats['unmatched']}")
    logger.info(f"Результат сохранён: {output_file}")


def cmd_push_descriptions(args, ctx=None) -> None:
    """Обработчик команды push-descriptions (применение описаний)."""
    from .configurator import DescriptionPusher
    import pandas as pd

    # Определяем режим
    dry_run = not args.apply

    # Загружаем результаты сопоставления
    logger.info(f"Загрузка данных из {args.matched_file}...")
    df = pd.read_excel(args.matched_file)

    # Фильтруем только сопоставленные записи
    matched_df = df[df["Matched"] == "Yes"]
    if matched_df.empty:
        logger.warning("Нет сопоставленных записей для применения")
        return

    # Генерируем команды
    import pandas as pd  # для pd.isna()

    commands: dict = {}
    device_names: dict = {}  # IP -> hostname для логирования
    for _, row in matched_df.iterrows():
        hostname = row.get("Device", "")
        device_ip = row.get("IP", "")  # Колонка IP для поиска устройства
        interface = row.get("Interface", "")
        host_name = row.get("Host_Name", "")
        current_desc = row.get("Current_Description", "")

        if not device_ip or not interface or not host_name:
            continue

        # Проверяем условия
        # Пустая строка: None, NaN, пробелы
        is_empty = pd.isna(current_desc) or str(current_desc).strip() == ""

        if args.only_empty and not is_empty:
            continue
        if not args.overwrite and not is_empty:
            continue

        # Пропускаем если текущее описание совпадает с новым
        if str(current_desc).strip() == str(host_name).strip():
            continue

        # Используем IP как ключ для поиска устройства
        if device_ip not in commands:
            commands[device_ip] = []
            device_names[device_ip] = hostname  # Сохраняем hostname для логов

        commands[device_ip].append(f"interface {interface}")
        commands[device_ip].append(f"description {host_name}")

    if not commands:
        logger.warning("Нет команд для применения")
        return

    # Показываем что будет сделано
    total_interfaces = sum(len(cmds) // 2 for cmds in commands.values())
    logger.info(f"Будет обновлено {total_interfaces} интерфейсов на {len(commands)} устройствах")

    if dry_run:
        logger.info("=== DRY RUN (команды не будут применены) ===")
        for device_ip, cmds in commands.items():
            display_name = device_names.get(device_ip, device_ip)
            logger.info(f"\n{display_name} ({device_ip}):")
            for cmd in cmds:
                logger.info(f"  {cmd}")
        logger.info("\nДля применения используйте флаг --apply")
        return

    # Получаем учётные данные и устройства
    devices, credentials = prepare_collection(args)

    # Применяем
    pusher = DescriptionPusher(credentials)
    results = pusher.push_descriptions(devices, commands, dry_run=False)

    # Статистика
    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    logger.info("=== РЕЗУЛЬТАТЫ ===")
    logger.info(f"Успешно: {success}")
    logger.info(f"Ошибки: {failed}")

    for r in results:
        if not r.success:
            logger.error(f"  {r.device}: {r.error}")


def cmd_sync_netbox(args, ctx=None) -> None:
    """
    Обработчик команды sync-netbox.

    ВАЖНО: С устройств мы только ЧИТАЕМ данные!
    Синхронизация — это выгрузка собранных данных В NetBox.
    """
    from .netbox import NetBoxClient, NetBoxSync, DiffCalculator
    from .collectors import InterfaceCollector, LLDPCollector
    from .config import config

    # --sync-all включает все флаги синхронизации
    if getattr(args, "sync_all", False):
        args.create_devices = True
        args.update_devices = True
        args.interfaces = True
        args.ip_addresses = True
        args.vlans = True
        args.cables = True
        args.inventory = True
        logger.info("Режим --sync-all: полная синхронизация")

    # Приоритет: CLI аргументы > config.yaml > переменные окружения
    url = args.url or config.netbox.url
    token = args.token or config.netbox.token
    ssl_verify = config.netbox.verify_ssl

    try:
        client = NetBoxClient(url=url, token=token, ssl_verify=ssl_verify)
    except Exception as e:
        logger.error(f"Ошибка подключения к NetBox: {e}")
        return

    # Создаём синхронизатор с нужными опциями
    sync = NetBoxSync(
        client,
        dry_run=args.dry_run,
        create_only=getattr(args, "create_only", False),
    )

    # Загружаем устройства и учётные данные
    devices, credentials = prepare_collection(args)

    # Создание/обновление устройств в NetBox из инвентаризации
    # ВАЖНО: Должно идти первым, чтобы устройства существовали для интерфейсов/IP/кабелей
    if getattr(args, "create_devices", False):
        from .collectors import DeviceInventoryCollector

        update_devices = getattr(args, "update_devices", False)
        cleanup = getattr(args, "cleanup", False)
        tenant = getattr(args, "tenant", None)

        if cleanup:
            if not tenant:
                logger.error(
                    "ОШИБКА: --cleanup требует указания --tenant для безопасности! "
                    "Это предотвращает случайное удаление чужих устройств."
                )
                return
            if not args.dry_run:
                logger.warning(
                    f"ВНИМАНИЕ: --cleanup удалит устройства tenant='{tenant}' "
                    f"которых нет в списке!"
                )

        action = "Синхронизация" if update_devices else "Создание"
        logger.info(f"{action} устройств в NetBox...")

        collector = DeviceInventoryCollector(
            credentials=credentials,
            transport=args.transport,
        )

        # collect() теперь возвращает List[DeviceInfo]
        device_infos = collector.collect(devices)
        if device_infos:
            # Показываем diff если запрошено
            show_diff = getattr(args, "show_diff", False)
            if show_diff:
                diff_calc = DiffCalculator(client)
                # Конвертируем DeviceInfo в dict для diff
                inventory_dicts = [
                    d.to_dict() if hasattr(d, "to_dict") else d
                    for d in device_infos
                ]
                diff = diff_calc.diff_devices(
                    inventory_dicts,
                    site=getattr(args, "site", "Main"),
                    update_existing=update_devices,
                )
                if diff.has_changes:
                    logger.info(f"\n{diff.format_detailed()}")
                else:
                    logger.info("Устройства: нет изменений")

            sync.sync_devices_from_inventory(
                device_infos,
                site=getattr(args, "site", "Main"),
                role=getattr(args, "role", "switch"),
                update_existing=update_devices,
                cleanup=cleanup,
                tenant=tenant,
                # Primary IP устанавливается только при --ip-addresses
                set_primary_ip=getattr(args, "ip_addresses", False),
            )
        else:
            logger.warning("Нет данных инвентаризации")

    # Синхронизация интерфейсов
    if args.interfaces:
        logger.info("Сбор интерфейсов с устройств...")
        collector = InterfaceCollector(
            credentials=credentials,
            transport=args.transport,
        )

        # DiffCalculator для показа изменений
        show_diff = getattr(args, "show_diff", False)
        diff_calc = DiffCalculator(client) if show_diff else None

        for device in devices:
            data = collector.collect([device])
            if data:
                hostname = data[0].hostname or device.host

                # Показываем diff если запрошено
                if diff_calc:
                    # Конвертируем в список dict для DiffCalculator
                    intf_dicts = [intf.to_dict() if hasattr(intf, "to_dict") else intf for intf in data]
                    diff = diff_calc.diff_interfaces(hostname, intf_dicts)
                    if diff.has_changes:
                        logger.info(f"\n{diff.format_detailed()}")
                    else:
                        logger.info(f"Интерфейсы {hostname}: нет изменений")

                sync.sync_interfaces(hostname, data)

    # Синхронизация кабелей из LLDP/CDP
    if getattr(args, "cables", False):
        protocol = getattr(args, "protocol", "both")
        logger.info(f"Сбор {protocol.upper()} данных с устройств...")
        collector = LLDPCollector(
            credentials=credentials,
            protocol=protocol,
            transport=args.transport,
        )

        all_lldp_data = []
        for device in devices:
            data = collector.collect([device])
            if data:
                all_lldp_data.extend(data)

        if all_lldp_data:
            logger.info(f"Найдено {len(all_lldp_data)} соседей, создаём кабели...")
            sync.sync_cables_from_lldp(
                all_lldp_data,
                skip_unknown=getattr(args, "skip_unknown", True),
            )
        else:
            logger.warning("LLDP/CDP данные не найдены")

    # Синхронизация IP-адресов
    if getattr(args, "ip_addresses", False):
        from .core.models import IPAddressEntry

        logger.info("Сбор IP-адресов с устройств...")
        collector = InterfaceCollector(
            credentials=credentials,
            transport=args.transport,
        )

        # DiffCalculator для показа изменений
        show_diff = getattr(args, "show_diff", False)
        diff_calc = DiffCalculator(client) if show_diff else None

        for device in devices:
            interfaces = collector.collect([device])
            if interfaces:
                hostname = interfaces[0].hostname or device.host
                # Фильтруем только интерфейсы с IP и создаём IPAddressEntry
                ip_entries = [
                    IPAddressEntry(
                        ip_address=intf.ip_address,
                        interface=intf.name,
                        mask="",  # mask будет определена из ip_address если есть /
                        hostname=hostname,
                        device_ip=device.host,
                    )
                    for intf in interfaces
                    if intf.ip_address
                ]
                if ip_entries:
                    # Показываем diff если запрошено
                    if diff_calc:
                        ip_dicts = [e.to_dict() if hasattr(e, "to_dict") else e for e in ip_entries]
                        diff = diff_calc.diff_ip_addresses(hostname, ip_dicts)
                        if diff.has_changes:
                            logger.info(f"\n{diff.format_detailed()}")
                        else:
                            logger.info(f"IP-адреса {hostname}: нет изменений")

                    sync.sync_ip_addresses(
                        hostname,
                        ip_entries,
                        device_ip=device.host,
                        update_existing=getattr(args, "update_devices", False),
                    )

    # Синхронизация VLAN из SVI интерфейсов
    if getattr(args, "vlans", False):
        logger.info("Сбор VLAN из SVI интерфейсов...")
        collector = InterfaceCollector(
            credentials=credentials,
            transport=args.transport,
        )

        for device in devices:
            interfaces = collector.collect([device])
            if interfaces:
                hostname = interfaces[0].hostname or device.host
                sync.sync_vlans_from_interfaces(
                    hostname,
                    interfaces,
                    site=getattr(args, "site", None),
                )

    # Синхронизация inventory (модули, SFP, PSU)
    if getattr(args, "inventory", False):
        from .collectors import InventoryCollector

        logger.info("Сбор inventory (модули, SFP, PSU)...")
        collector = InventoryCollector(
            credentials=credentials,
            transport=args.transport,
        )

        for device in devices:
            items = collector.collect([device])
            if items:
                hostname = items[0].hostname or device.host
                sync.sync_inventory(hostname, items)


def cmd_backup(args, ctx=None) -> None:
    """Обработчик команды backup (резервное копирование конфигураций)."""
    from .collectors import ConfigBackupCollector

    devices, credentials = prepare_collection(args)

    # Создаём коллектор бэкапов
    collector = ConfigBackupCollector(
        credentials=credentials,
        transport=args.transport,
    )

    # Выполняем бэкап
    output_folder = getattr(args, "output", "backups")
    results = collector.backup(devices, output_folder=output_folder)

    # Статистика
    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    logger.info("=== РЕЗУЛЬТАТЫ ===")
    logger.info(f"Успешно: {success}")
    logger.info(f"Ошибки: {failed}")

    for r in results:
        if not r.success:
            logger.error(f"  {r.hostname}: {r.error}")


def main() -> None:
    """Главная функция CLI."""
    from .config import load_config, config
    from .core.context import RunContext, set_current_context
    from .core.logging import LogConfig, RotationType, setup_logging_from_config

    parser = setup_parser()
    args = parser.parse_args()

    # Загружаем конфигурацию из YAML (если есть)
    load_config(args.config)

    # Создаём контекст выполнения
    dry_run = getattr(args, "dry_run", False)
    ctx = RunContext.create(
        dry_run=dry_run,
        triggered_by="cli",
        command=args.command or "",
        base_output_dir=Path(args.output) if hasattr(args, "output") else None,
    )
    set_current_context(ctx)

    # Настройка логирования из config.yaml
    log_cfg = config.logging

    # Приоритет: -v флаг > config.yaml > INFO по умолчанию
    if args.verbose:
        log_level = logging.DEBUG
    elif log_cfg and hasattr(log_cfg, "level"):
        # Поддержка строковых и числовых уровней
        cfg_level = getattr(log_cfg, "level", "INFO")
        if isinstance(cfg_level, str):
            log_level = getattr(logging, cfg_level.upper(), logging.INFO)
        else:
            log_level = cfg_level
    else:
        log_level = logging.INFO

    # Создаём LogConfig из config.yaml
    rotation_str = getattr(log_cfg, "rotation", "size") if log_cfg else "size"
    try:
        rotation = RotationType(rotation_str) if rotation_str else RotationType.SIZE
    except ValueError:
        rotation = RotationType.SIZE

    log_config = LogConfig(
        level=log_level,
        json_format=getattr(log_cfg, "json_format", False) if log_cfg else False,
        console=getattr(log_cfg, "console", True) if log_cfg else True,
        file_path=getattr(log_cfg, "file_path", None) if log_cfg else None,
        rotation=rotation,
        max_bytes=getattr(log_cfg, "max_bytes", 10 * 1024 * 1024) if log_cfg else 10 * 1024 * 1024,
        backup_count=getattr(log_cfg, "backup_count", 5) if log_cfg else 5,
        when=getattr(log_cfg, "when", "midnight") if log_cfg else "midnight",
        interval=getattr(log_cfg, "interval", 1) if log_cfg else 1,
    )

    setup_logging_from_config(log_config)

    logger.info(f"Run started (command={args.command}, dry_run={dry_run})")

    # Выбор команды
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
        cmd_sync_netbox(args, ctx)
    elif args.command == "backup":
        cmd_backup(args, ctx)
    else:
        parser.print_help()
        return

    # Логируем завершение
    logger.info(f"Run completed: {ctx.run_id} (elapsed={ctx.elapsed_human})")


if __name__ == "__main__":
    main()
