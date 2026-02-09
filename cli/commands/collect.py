"""
Команды сбора данных.

Команды: devices, mac, lldp, interfaces, inventory
"""

import logging
from typing import Optional

from ..utils import prepare_collection, get_exporter

logger = logging.getLogger(__name__)


def _export_parsed(data, report_name):
    """Выводит parsed данные (до нормализации) через RawExporter в stdout."""
    from ...exporters import RawExporter
    RawExporter().export(data, report_name)


def cmd_devices(args, ctx=None) -> None:
    """Обработчик команды devices (инвентаризация)."""
    from ...collectors import DeviceInventoryCollector
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    collector = DeviceInventoryCollector(
        credentials=credentials,
        site=args.site,
        role=args.role,
        manufacturer=args.manufacturer,
        transport=args.transport,
    )

    # --format parsed: пропускаем нормализацию
    if args.format == "parsed":
        collector._skip_normalize = True

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # --format parsed: сырые данные TextFSM, без fields.yaml
    if args.format == "parsed":
        _export_parsed(data, "device_inventory_parsed")
        return

    data = apply_fields_config(data, "devices")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "device_inventory")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_mac(args, ctx=None) -> None:
    """Обработчик команды mac."""
    from ...collectors import MACCollector
    from ...config import config as app_config
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None
    mac_format = args.mac_format or app_config.output.mac_format

    # Настройки из config.yaml
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

    collector = MACCollector(
        credentials=credentials,
        mac_format=mac_format,
        ntc_fields=fields,
        collect_descriptions=collect_descriptions,
        collect_trunk_ports=collect_trunk,
        collect_port_security=collect_port_security,
        transport=args.transport,
    )

    # --format parsed: пропускаем нормализацию
    if args.format == "parsed":
        collector._skip_normalize = True

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # --format parsed: сырые данные TextFSM, без fields.yaml и match
    if args.format == "parsed":
        _export_parsed(data, "mac_addresses_parsed")
        return

    # Сопоставляем с файлом если указан
    if args.match_file:
        try:
            from ...configurator import DescriptionMatcher
            matcher = DescriptionMatcher()
            matcher.load_hosts_file(args.match_file)
            matched = matcher.match_mac_data(data)
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

    data = apply_fields_config(data, "mac")

    exporter = get_exporter(args.format, args.output, args.delimiter)

    per_device = getattr(args, "per_device", False) or app_config.output.per_device

    if per_device:
        from collections import defaultdict

        data_by_device = defaultdict(list)
        for row in data:
            hostname = row.get("hostname", "unknown")
            data_by_device[hostname].append(row)

        for hostname, device_data in data_by_device.items():
            safe_hostname = hostname.replace("/", "_").replace("\\", "_")
            file_path = exporter.export(device_data, f"mac_{safe_hostname}")
            if file_path:
                logger.info(f"Отчёт сохранён: {file_path}")
    else:
        file_path = exporter.export(data, "mac_addresses")
        if file_path:
            logger.info(f"Отчёт сохранён: {file_path}")


def cmd_lldp(args, ctx=None) -> None:
    """Обработчик команды lldp."""
    from ...collectors import LLDPCollector
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    collector = LLDPCollector(
        credentials=credentials,
        protocol=args.protocol,
        ntc_fields=fields,
        transport=args.transport,
    )

    # --format parsed: пропускаем нормализацию
    if args.format == "parsed":
        collector._skip_normalize = True

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # --format parsed: сырые данные TextFSM, без fields.yaml
    if args.format == "parsed":
        _export_parsed(data, f"{args.protocol}_neighbors_parsed")
        return

    data = apply_fields_config(data, "lldp")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    report_name = f"{args.protocol}_neighbors"
    file_path = exporter.export(data, report_name)

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_interfaces(args, ctx=None) -> None:
    """Обработчик команды interfaces."""
    from ...collectors import InterfaceCollector
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    collector = InterfaceCollector(
        credentials=credentials,
        ntc_fields=fields,
        transport=args.transport,
    )

    # --format parsed: пропускаем нормализацию
    if args.format == "parsed":
        collector._skip_normalize = True

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # --format parsed: сырые данные TextFSM, без fields.yaml
    if args.format == "parsed":
        _export_parsed(data, "interfaces_parsed")
        return

    data = apply_fields_config(data, "interfaces")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "interfaces")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")


def cmd_inventory(args, ctx=None) -> None:
    """Обработчик команды inventory."""
    from ...collectors import InventoryCollector
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    collector = InventoryCollector(
        credentials=credentials,
        ntc_fields=fields,
        transport=args.transport,
    )

    # --format parsed: пропускаем нормализацию
    if args.format == "parsed":
        collector._skip_normalize = True

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # --format parsed: сырые данные TextFSM, без fields.yaml
    if args.format == "parsed":
        _export_parsed(data, "inventory_parsed")
        return

    data = apply_fields_config(data, "inventory")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "inventory")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
