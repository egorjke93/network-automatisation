"""
CLI модуль network_collector.

Структура:
- utils.py: общие утилиты (load_devices, get_exporter, get_credentials)
- commands/: обработчики команд
  - collect.py: devices, mac, lldp, interfaces, inventory
  - sync.py: sync-netbox
  - backup.py: backup, run
  - match.py: match-mac
  - push.py: push-descriptions
  - validate.py: validate-fields

Примеры использования:
    python -m network_collector devices --format csv
    python -m network_collector mac --format excel
    python -m network_collector lldp --protocol both
    python -m network_collector sync-netbox --interfaces
"""

import argparse
import logging
from pathlib import Path

from .utils import (
    load_devices,
    get_exporter,
    get_credentials,
    prepare_collection,
)

from .commands import (
    cmd_devices,
    cmd_mac,
    cmd_lldp,
    cmd_interfaces,
    cmd_inventory,
    cmd_sync_netbox,
    cmd_backup,
    cmd_run,
    cmd_match_mac,
    cmd_push_descriptions,
    cmd_validate_fields,
    cmd_pipeline,
    _print_sync_summary,
)

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
        choices=["excel", "csv", "json", "raw"],
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
        choices=["excel", "csv", "json", "raw"],
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
        choices=["excel", "csv", "json", "raw"],
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
        choices=["excel", "csv", "json", "raw"],
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
        choices=["excel", "csv", "json", "raw"],
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
        "-v",
        "--verbose",
        action="store_true",
        help="Подробный вывод (DEBUG)",
    )
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
        help="Удалять устройства из NetBox которых нет в списке (требует --tenant)",
    )
    netbox_parser.add_argument(
        "--cleanup-interfaces",
        action="store_true",
        help="Удалять интерфейсы из NetBox которых нет на устройстве",
    )
    netbox_parser.add_argument(
        "--cleanup-ips",
        action="store_true",
        help="Удалять IP-адреса из NetBox которых нет на устройстве",
    )
    netbox_parser.add_argument(
        "--cleanup-cables",
        action="store_true",
        help="Удалять кабели из NetBox которых нет в LLDP/CDP данных",
    )
    netbox_parser.add_argument(
        "--update-ips",
        action="store_true",
        help="Обновлять существующие IP-адреса (description, tenant)",
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
        "--cleanup-inventory",
        action="store_true",
        help="Удалять inventory items из NetBox которых нет на устройстве",
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

    # === Validate Fields (валидация fields.yaml) ===
    validate_parser = subparsers.add_parser(
        "validate-fields",
        help="Валидация fields.yaml против моделей"
    )
    validate_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Подробный вывод",
    )
    validate_parser.add_argument(
        "--show-registry",
        action="store_true",
        help="Показать реестр полей",
    )
    validate_parser.add_argument(
        "--type",
        "-t",
        choices=["lldp", "mac", "interfaces", "devices", "inventory"],
        help="Показать только указанный тип данных",
    )

    # === Pipeline (управление pipelines) ===
    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Управление и запуск pipelines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  %(prog)s list                    # Показать все pipelines
  %(prog)s show default            # Детали pipeline
  %(prog)s run default --dry-run   # Запустить в режиме dry-run
  %(prog)s validate default        # Валидировать pipeline
  %(prog)s create my_pipeline.yaml # Создать из YAML файла
  %(prog)s delete old_pipeline     # Удалить pipeline
        """,
    )

    # Subparsers для pipeline
    pipeline_subparsers = pipeline_parser.add_subparsers(
        dest="pipeline_command",
        help="Подкоманды pipeline"
    )

    # pipeline list
    pl_list = pipeline_subparsers.add_parser("list", help="Показать все pipelines")
    pl_list.add_argument(
        "--format", "-f",
        choices=["table", "json"],
        default="table",
        help="Формат вывода",
    )

    # pipeline show
    pl_show = pipeline_subparsers.add_parser("show", help="Показать детали pipeline")
    pl_show.add_argument("name", help="Имя pipeline")
    pl_show.add_argument(
        "--format", "-f",
        choices=["table", "json"],
        default="table",
        help="Формат вывода",
    )

    # pipeline run
    pl_run = pipeline_subparsers.add_parser("run", help="Запустить pipeline")
    pl_run.add_argument("name", help="Имя pipeline")
    pl_run.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Режим симуляции (default: True)",
    )
    pl_run.add_argument(
        "--apply",
        action="store_true",
        help="Применить изменения (отключает dry-run)",
    )
    pl_run.add_argument(
        "--format", "-f",
        choices=["table", "json"],
        default="table",
        help="Формат вывода результата",
    )
    pl_run.add_argument(
        "--netbox-url",
        help="URL NetBox (переопределяет config.yaml)",
    )
    pl_run.add_argument(
        "--netbox-token",
        help="API токен NetBox (переопределяет config.yaml)",
    )

    # pipeline validate
    pl_validate = pipeline_subparsers.add_parser("validate", help="Валидировать pipeline")
    pl_validate.add_argument("name", help="Имя pipeline")

    # pipeline create
    pl_create = pipeline_subparsers.add_parser("create", help="Создать pipeline из YAML")
    pl_create.add_argument("source", help="Путь к YAML файлу")
    pl_create.add_argument(
        "--force",
        action="store_true",
        help="Перезаписать если существует",
    )

    # pipeline delete
    pl_delete = pipeline_subparsers.add_parser("delete", help="Удалить pipeline")
    pl_delete.add_argument("name", help="Имя pipeline")
    pl_delete.add_argument(
        "--force", "-f",
        action="store_true",
        help="Удалить без подтверждения",
    )

    return parser


def main() -> None:
    """Главная функция CLI."""
    from ..config import load_config, config
    from ..core.context import RunContext, set_current_context
    from ..core.logging import LogConfig, RotationType, setup_logging_from_config

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
    elif args.command == "validate-fields":
        cmd_validate_fields(args, ctx)
    elif args.command == "pipeline":
        cmd_pipeline(args, ctx)
    else:
        parser.print_help()
        return

    # Логируем завершение
    logger.info(f"Run completed: {ctx.run_id} (elapsed={ctx.elapsed_human})")


__all__ = [
    # Utils
    "load_devices",
    "get_exporter",
    "get_credentials",
    "prepare_collection",
    # Commands
    "cmd_devices",
    "cmd_mac",
    "cmd_lldp",
    "cmd_interfaces",
    "cmd_inventory",
    "cmd_sync_netbox",
    "cmd_backup",
    "cmd_run",
    "cmd_match_mac",
    "cmd_push_descriptions",
    "cmd_validate_fields",
    "cmd_pipeline",
    "_print_sync_summary",
    # Entry points
    "setup_parser",
    "main",
]
