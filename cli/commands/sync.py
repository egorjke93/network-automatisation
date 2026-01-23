"""
Команда sync-netbox.

Синхронизация данных с NetBox.
"""

import logging

from ..utils import prepare_collection

logger = logging.getLogger(__name__)


def cmd_sync_netbox(args, ctx=None) -> None:
    """
    Обработчик команды sync-netbox.

    ВАЖНО: С устройств мы только ЧИТАЕМ данные!
    Синхронизация — это выгрузка собранных данных В NetBox.
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

    # Статистика для сводки в конце
    summary = {
        "devices": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
        "interfaces": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
        "ip_addresses": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
        "vlans": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
        "cables": {"created": 0, "deleted": 0, "skipped": 0, "failed": 0, "already_exists": 0},
        "inventory": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
    }

    # Детали изменений для вывода в конце
    all_details = {
        "devices": {"create": [], "update": [], "delete": []},
        "interfaces": {"create": [], "update": [], "delete": []},
        "ip_addresses": {"create": [], "update": [], "delete": []},
        "vlans": {"create": [], "update": [], "delete": []},
        "cables": {"create": [], "delete": []},
        "inventory": {"create": [], "update": [], "delete": []},
    }

    # Создание/обновление устройств в NetBox из инвентаризации
    if getattr(args, "create_devices", False):
        from ...collectors import DeviceInventoryCollector

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

        device_infos = collector.collect(devices)
        if device_infos:
            show_diff = getattr(args, "show_diff", False) or getattr(args, "dry_run", False)
            if show_diff:
                diff_calc = DiffCalculator(client)
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

            stats = sync.sync_devices_from_inventory(
                device_infos,
                site=getattr(args, "site", "Main"),
                role=getattr(args, "role", "switch"),
                update_existing=update_devices,
                cleanup=cleanup,
                tenant=tenant,
                set_primary_ip=getattr(args, "ip_addresses", False),
            )
            for key in ("created", "updated", "deleted", "skipped", "failed"):
                summary["devices"][key] += stats.get(key, 0)
            # Собираем детали
            if stats.get("details"):
                for action in ("create", "update", "delete"):
                    all_details["devices"][action].extend(stats["details"].get(action, []))
        else:
            logger.warning("Нет данных инвентаризации")

    # Синхронизация интерфейсов
    if args.interfaces:
        cleanup_interfaces = getattr(args, "cleanup_interfaces", False)
        logger.info("Сбор интерфейсов с устройств...")
        collector = InterfaceCollector(
            credentials=credentials,
            transport=args.transport,
        )

        show_diff = getattr(args, "show_diff", False) or getattr(args, "dry_run", False)
        diff_calc = DiffCalculator(client) if show_diff else None

        for device in devices:
            data = collector.collect([device])
            if data:
                hostname = data[0].hostname or device.host

                if diff_calc:
                    intf_dicts = [intf.to_dict() if hasattr(intf, "to_dict") else intf for intf in data]
                    diff = diff_calc.diff_interfaces(hostname, intf_dicts)
                    if diff.has_changes:
                        logger.info(f"\n{diff.format_detailed()}")
                    else:
                        logger.info(f"Интерфейсы {hostname}: нет изменений")

                stats = sync.sync_interfaces(hostname, data, cleanup=cleanup_interfaces)
                for key in ("created", "updated", "deleted", "skipped", "failed"):
                    summary["interfaces"][key] += stats.get(key, 0)
                # Собираем детали с hostname
                if stats.get("details"):
                    for action in ("create", "update", "delete"):
                        for item in stats["details"].get(action, []):
                            item["device"] = hostname
                            all_details["interfaces"][action].append(item)

    # Синхронизация кабелей из LLDP/CDP
    if getattr(args, "cables", False):
        protocol = getattr(args, "protocol", "both")
        cleanup_cables = getattr(args, "cleanup_cables", False)
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
            stats = sync.sync_cables_from_lldp(
                all_lldp_data,
                skip_unknown=getattr(args, "skip_unknown", True),
                cleanup=cleanup_cables,
            )
            for key in ("created", "deleted", "skipped", "failed", "already_exists"):
                summary["cables"][key] += stats.get(key, 0)
            # Собираем детали
            if stats.get("details"):
                all_details["cables"]["create"].extend(stats["details"].get("create", []))
                all_details["cables"]["delete"].extend(stats["details"].get("delete", []))
        else:
            logger.warning("LLDP/CDP данные не найдены")

    # Синхронизация IP-адресов
    if getattr(args, "ip_addresses", False):
        from ...core.models import IPAddressEntry

        update_ips = getattr(args, "update_ips", False)
        cleanup_ips = getattr(args, "cleanup_ips", False)
        logger.info("Сбор IP-адресов с устройств...")
        collector = InterfaceCollector(
            credentials=credentials,
            transport=args.transport,
        )

        show_diff = getattr(args, "show_diff", False) or getattr(args, "dry_run", False)
        diff_calc = DiffCalculator(client) if show_diff else None

        for device in devices:
            interfaces = collector.collect([device])
            if interfaces:
                hostname = interfaces[0].hostname or device.host
                ip_entries = [
                    IPAddressEntry(
                        ip_address=intf.ip_address,
                        interface=intf.name,
                        mask=intf.prefix_length,  # маска из парсинга интерфейсов
                        hostname=hostname,
                        device_ip=device.host,
                    )
                    for intf in interfaces
                    if intf.ip_address
                ]
                if ip_entries:
                    if diff_calc:
                        ip_dicts = [e.to_dict() if hasattr(e, "to_dict") else e for e in ip_entries]
                        diff = diff_calc.diff_ip_addresses(hostname, ip_dicts)
                        if diff.has_changes:
                            logger.info(f"\n{diff.format_detailed()}")
                        else:
                            logger.info(f"IP-адреса {hostname}: нет изменений")

                    stats = sync.sync_ip_addresses(
                        hostname,
                        ip_entries,
                        device_ip=device.host,
                        update_existing=update_ips,
                        cleanup=cleanup_ips,
                    )
                    for key in ("created", "updated", "deleted", "skipped", "failed"):
                        summary["ip_addresses"][key] += stats.get(key, 0)
                    # Собираем детали с hostname
                    if stats.get("details"):
                        for action in ("create", "update", "delete"):
                            for item in stats["details"].get(action, []):
                                item["device"] = hostname
                                all_details["ip_addresses"][action].append(item)

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
                stats = sync.sync_vlans_from_interfaces(
                    hostname,
                    interfaces,
                    site=getattr(args, "site", None),
                )
                for key in ("created", "updated", "deleted", "skipped", "failed"):
                    summary["vlans"][key] += stats.get(key, 0)
                # Собираем детали
                if stats.get("details"):
                    for action in ("create", "update", "delete"):
                        all_details["vlans"][action].extend(stats["details"].get(action, []))

    # Синхронизация inventory (модули, SFP, PSU)
    if getattr(args, "inventory", False):
        from ...collectors import InventoryCollector

        cleanup_inventory = getattr(args, "cleanup_inventory", False)
        logger.info("Сбор inventory (модули, SFP, PSU)...")
        collector = InventoryCollector(
            credentials=credentials,
            transport=args.transport,
        )

        for device in devices:
            items = collector.collect([device])
            hostname = items[0].hostname if items else device.hostname or device.host
            # Вызываем sync_inventory даже если items пустой - для cleanup
            if items or cleanup_inventory:
                stats = sync.sync_inventory(hostname, items, cleanup=cleanup_inventory)
                for key in ("created", "updated", "deleted", "skipped", "failed"):
                    summary["inventory"][key] += stats.get(key, 0)
                # Собираем детали с hostname
                if stats.get("details"):
                    for action in ("create", "update", "delete"):
                        for item in stats["details"].get(action, []):
                            item["device"] = hostname
                            all_details["inventory"][action].append(item)

    # === СВОДКА В КОНЦЕ ===
    _print_changes_details(all_details, args)
    _print_sync_summary(summary, all_details, args)


def _print_changes_details(all_details: dict, args) -> None:
    """Выводит детали изменений перед сводкой."""
    # В JSON режиме пропускаем — детали будут в summary
    if getattr(args, "format", None) == "json":
        return

    # Проверяем есть ли вообще изменения
    has_any = False
    for category_details in all_details.values():
        for items in category_details.values():
            if items:
                has_any = True
                break

    if not has_any:
        return

    category_names = {
        "devices": "DEVICES",
        "interfaces": "INTERFACES",
        "ip_addresses": "IP ADDRESSES",
        "vlans": "VLANS",
        "cables": "CABLES",
        "inventory": "INVENTORY",
    }

    action_icons = {"create": "+", "update": "~", "delete": "-"}

    mode = "[DRY-RUN] " if getattr(args, "dry_run", False) else ""
    print(f"\n{'='*60}")
    print(f"{mode}ДЕТАЛИ ИЗМЕНЕНИЙ")
    print(f"{'='*60}")

    for category, details in all_details.items():
        # Проверяем есть ли изменения в этой категории
        if not any(details.values()):
            continue

        print(f"\n{category_names.get(category, category.upper())}:")

        for action in ("create", "update", "delete"):
            items = details.get(action, [])
            if not items:
                continue

            icon = action_icons.get(action, "•")

            for item in items:
                # Поддержка разных форматов: "name" для интерфейсов, "address" для IP
                name = item.get("name") or item.get("address", "")
                device = item.get("device", "")
                changes = item.get("changes", [])

                # Форматируем вывод в зависимости от типа
                if category == "cables":
                    # Кабели: + switch1:Gi0/1 ↔ switch2:Gi0/1
                    print(f"  {icon} {name}")
                elif device:
                    # С устройством: + switch1: Gi0/1
                    if changes:
                        print(f"  {icon} {device}: {name} ({', '.join(changes)})")
                    else:
                        print(f"  {icon} {device}: {name}")
                else:
                    # Без устройства: + switch1
                    if changes:
                        print(f"  {icon} {name} ({', '.join(changes)})")
                    else:
                        print(f"  {icon} {name}")


def _print_sync_summary(summary: dict, all_details: dict, args) -> None:
    """Выводит сводку синхронизации в конце."""
    import json

    total_created = sum(s.get("created", 0) for s in summary.values())
    total_updated = sum(s.get("updated", 0) for s in summary.values())
    total_deleted = sum(s.get("deleted", 0) for s in summary.values())
    total_skipped = sum(s.get("skipped", 0) for s in summary.values())
    total_failed = sum(s.get("failed", 0) for s in summary.values())
    has_changes = total_created > 0 or total_updated > 0 or total_deleted > 0

    # JSON формат
    if getattr(args, "format", None) == "json":
        result = {
            "dry_run": getattr(args, "dry_run", False),
            "has_changes": has_changes,
            "summary": summary,
            "details": all_details,
            "totals": {
                "created": total_created,
                "updated": total_updated,
                "deleted": total_deleted,
                "skipped": total_skipped,
                "failed": total_failed,
            },
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # Консольный вывод
    mode = "[DRY-RUN] " if getattr(args, "dry_run", False) else ""
    print(f"\n{'='*60}")
    print(f"{mode}СВОДКА СИНХРОНИЗАЦИИ NetBox")
    print(f"{'='*60}")

    category_names = {
        "devices": "Устройства",
        "interfaces": "Интерфейсы",
        "ip_addresses": "IP-адреса",
        "vlans": "VLANs",
        "cables": "Кабели",
        "inventory": "Inventory",
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
            if stats.get("skipped", 0) > 0:
                parts.append(f"={stats['skipped']} пропущено")
            if stats.get("already_exists", 0) > 0:
                parts.append(f"✓{stats['already_exists']} существует")
            if stats.get("failed", 0) > 0:
                parts.append(f"✗{stats['failed']} ошибок")
            print(f"  {name}: {', '.join(parts)}")

    print(f"{'-'*60}")
    if has_changes or total_failed > 0:
        parts = []
        if total_created > 0:
            parts.append(f"+{total_created} создано")
        if total_updated > 0:
            parts.append(f"~{total_updated} обновлено")
        if total_deleted > 0:
            parts.append(f"-{total_deleted} удалено")
        if total_failed > 0:
            parts.append(f"✗{total_failed} ошибок")
        print(f"  ИТОГО: {', '.join(parts) if parts else 'нет изменений'}")
    else:
        print("  Изменений нет")
    print(f"{'='*60}\n")
