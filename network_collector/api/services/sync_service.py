"""
Sync Service - сервис синхронизации с NetBox.

Обёртка над netbox/sync.py для использования в API.
"""

import asyncio
from typing import List
from concurrent.futures import ThreadPoolExecutor

from ..schemas import (
    Credentials,
    NetBoxConfig,
    SyncRequest,
    SyncResponse,
    SyncStats,
    DiffEntry,
)

from network_collector.core.device import Device
from network_collector.netbox.client import NetBoxClient
from network_collector.netbox.sync import NetBoxSync
from network_collector.collectors import (
    DeviceCollector,
    InterfaceCollector,
    LLDPCollector,
    InventoryCollector,
)


class SyncService:
    """Сервис синхронизации с NetBox."""

    def __init__(self, credentials: Credentials, netbox: NetBoxConfig):
        # Сохраняем как объект Credentials (не dict!)
        from network_collector.core.credentials import Credentials as CoreCredentials
        self.credentials = CoreCredentials(
            username=credentials.username,
            password=credentials.password,
            secret=credentials.secret,
        )
        self.netbox_url = netbox.url
        self.netbox_token = netbox.token
        self._executor = ThreadPoolExecutor(max_workers=5)

    def _get_devices(self, device_list: List[str] = None) -> List[Device]:
        """Получает список устройств с device_type."""
        # Получаем device_type из device_service
        from .device_service import get_device_service
        device_service = get_device_service()
        all_devices = device_service.get_all_devices()

        # Создаём маппинг host -> device_type
        host_to_type = {d["host"]: d.get("device_type", "cisco_ios") for d in all_devices}

        if device_list:
            return [
                Device(host=ip, device_type=host_to_type.get(ip, "cisco_ios"))
                for ip in device_list
            ]

        # Получаем enabled устройства
        hosts = device_service.get_device_hosts()
        if hosts:
            return [
                Device(host=ip, device_type=host_to_type.get(ip, "cisco_ios"))
                for ip in hosts
            ]

        # Fallback на devices_ips.py
        try:
            from network_collector.devices_ips import devices_list
            return [
                Device(
                    host=d.get("host", d) if isinstance(d, dict) else d,
                    device_type=d.get("device_type", "cisco_ios") if isinstance(d, dict) else "cisco_ios"
                )
                for d in devices_list
            ]
        except ImportError:
            return []

    async def _run_in_executor(self, func, *args):
        """Запускает синхронную функцию в executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    async def sync(self, request: SyncRequest) -> SyncResponse:
        """Выполняет синхронизацию с NetBox."""
        devices = self._get_devices(request.devices)

        if not devices:
            return SyncResponse(
                success=False,
                dry_run=request.dry_run,
                errors=["No devices to sync"],
            )

        def _sync():
            # Создаём NetBox клиент
            client = NetBoxClient(
                url=self.netbox_url,
                token=self.netbox_token,
            )
            sync = NetBoxSync(client, dry_run=request.dry_run)

            diff_entries: List[DiffEntry] = []
            stats = {
                "devices": SyncStats(),
                "interfaces": SyncStats(),
                "ip_addresses": SyncStats(),
                "vlans": SyncStats(),
                "cables": SyncStats(),
                "inventory": SyncStats(),
            }
            errors = []

            # Собираем данные
            if request.sync_all or request.create_devices or request.update_devices:
                try:
                    collector = DeviceCollector(credentials=self.credentials)
                    device_data = collector.collect_dicts(devices)

                    result = sync.sync_devices_from_inventory(
                        device_data,
                        site=request.site,
                        role=request.role,
                    )
                    stats["devices"] = SyncStats(
                        created=result.get("created", 0),
                        updated=result.get("updated", 0),
                        skipped=result.get("skipped", 0),
                        failed=result.get("failed", 0),
                    )

                    # Добавляем diff entries
                    for action, items in result.get("details", {}).items():
                        for item in items:
                            diff_entries.append(DiffEntry(
                                entity_type="device",
                                entity_name=item.get("name", ""),
                                action=action,
                                device=item.get("name"),
                            ))

                except Exception as e:
                    errors.append(f"Devices sync error: {e}")

            if request.sync_all or request.interfaces or request.cleanup_interfaces:
                try:
                    collector = InterfaceCollector(credentials=self.credentials)
                    interface_data = collector.collect_dicts(devices)

                    # Group by device
                    by_device = {}
                    for intf in interface_data:
                        hostname = intf.get("hostname", "")
                        if hostname not in by_device:
                            by_device[hostname] = []
                        by_device[hostname].append(intf)

                    total_created = 0
                    total_updated = 0
                    total_deleted = 0
                    total_skipped = 0

                    for hostname, interfaces in by_device.items():
                        # sync_interfaces поддерживает cleanup параметр
                        result = sync.sync_interfaces(
                            hostname,
                            interfaces,
                            cleanup=request.cleanup_interfaces,
                        )
                        total_created += result.get("created", 0)
                        total_updated += result.get("updated", 0)
                        total_deleted += result.get("deleted", 0)
                        total_skipped += result.get("skipped", 0)

                        for action, items in result.get("details", {}).items():
                            for item in items:
                                diff_entries.append(DiffEntry(
                                    entity_type="interface",
                                    entity_name=item.get("name", ""),
                                    action=action,
                                    device=hostname,
                                ))

                    stats["interfaces"] = SyncStats(
                        created=total_created,
                        updated=total_updated,
                        deleted=total_deleted,
                        skipped=total_skipped,
                    )

                except Exception as e:
                    errors.append(f"Interfaces sync error: {e}")

            # IP Addresses sync
            if request.sync_all or request.ip_addresses:
                try:
                    # IP адреса извлекаются из интерфейсов
                    collector = InterfaceCollector(credentials=self.credentials)
                    interface_data = collector.collect_dicts(devices)

                    by_device = {}
                    for intf in interface_data:
                        hostname = intf.get("hostname", "")
                        device_ip = intf.get("device_ip", "")
                        if hostname not in by_device:
                            by_device[hostname] = {"interfaces": [], "device_ip": device_ip}
                        by_device[hostname]["interfaces"].append(intf)

                    total_created = 0
                    total_updated = 0
                    total_deleted = 0
                    total_skipped = 0

                    for hostname, data in by_device.items():
                        result = sync.sync_ip_addresses(
                            hostname,
                            data["interfaces"],
                            device_ip=data["device_ip"],
                            update_existing=request.update_ips,
                            cleanup=request.cleanup_ips,
                        )
                        total_created += result.get("created", 0)
                        total_updated += result.get("updated", 0)
                        total_deleted += result.get("deleted", 0)
                        total_skipped += result.get("skipped", 0)

                        for action in ["created", "updated", "deleted"]:
                            for item in result.get("details", {}).get(action, []):
                                diff_entries.append(DiffEntry(
                                    entity_type="ip_address",
                                    entity_name=item.get("address", item.get("name", "")),
                                    action=action,
                                    device=hostname,
                                ))

                    stats["ip_addresses"] = SyncStats(
                        created=total_created,
                        updated=total_updated,
                        deleted=total_deleted,
                        skipped=total_skipped,
                    )

                except Exception as e:
                    errors.append(f"IP addresses sync error: {e}")

            # VLANs sync
            if request.sync_all or request.vlans:
                try:
                    collector = InterfaceCollector(credentials=self.credentials)
                    interface_data = collector.collect_dicts(devices)

                    by_device = {}
                    for intf in interface_data:
                        hostname = intf.get("hostname", "")
                        if hostname not in by_device:
                            by_device[hostname] = []
                        by_device[hostname].append(intf)

                    total_created = 0
                    total_skipped = 0

                    for hostname, interfaces in by_device.items():
                        result = sync.sync_vlans_from_interfaces(
                            hostname,
                            interfaces,
                            site=request.site,
                        )
                        total_created += result.get("created", 0)
                        total_skipped += result.get("skipped", 0)

                        for item in result.get("details", {}).get("created", []):
                            diff_entries.append(DiffEntry(
                                entity_type="vlan",
                                entity_name=item.get("name", f"VLAN {item.get('vid', '')}"),
                                action="created",
                                device=hostname,
                            ))

                    stats["vlans"] = SyncStats(
                        created=total_created,
                        skipped=total_skipped,
                    )

                except Exception as e:
                    errors.append(f"VLANs sync error: {e}")

            if request.sync_all or request.cables or request.cleanup_cables:
                try:
                    # Используем protocol из запроса
                    protocol = request.protocol.value if hasattr(request.protocol, 'value') else str(request.protocol)
                    collector = LLDPCollector(
                        protocol=protocol,
                        credentials=self.credentials,
                    )
                    lldp_data = collector.collect_dicts(devices)

                    # sync_cables_from_lldp поддерживает cleanup параметр
                    result = sync.sync_cables_from_lldp(
                        lldp_data,
                        cleanup=request.cleanup_cables,
                    )
                    stats["cables"] = SyncStats(
                        created=result.get("created", 0),
                        deleted=result.get("deleted", 0),
                        skipped=result.get("skipped", 0),
                        failed=result.get("failed", 0),
                    )

                    # Добавляем diff entries для кабелей
                    for action, items in result.get("details", {}).items():
                        for item in items:
                            diff_entries.append(DiffEntry(
                                entity_type="cable",
                                entity_name=item.get("name", f"{item.get('a_device', '')}:{item.get('a_interface', '')} - {item.get('b_device', '')}:{item.get('b_interface', '')}"),
                                action=action,
                            ))

                except Exception as e:
                    errors.append(f"Cables sync error: {e}")

            return {
                "success": len(errors) == 0,
                "dry_run": request.dry_run,
                "stats": stats,
                "diff": diff_entries,
                "errors": errors,
            }

        try:
            result = await self._run_in_executor(_sync)
            return SyncResponse(
                success=result["success"],
                dry_run=result["dry_run"],
                devices=result["stats"]["devices"],
                interfaces=result["stats"]["interfaces"],
                ip_addresses=result["stats"]["ip_addresses"],
                vlans=result["stats"]["vlans"],
                cables=result["stats"]["cables"],
                inventory=result["stats"]["inventory"],
                diff=result["diff"],
                errors=result["errors"],
            )
        except Exception as e:
            return SyncResponse(
                success=False,
                dry_run=request.dry_run,
                errors=[str(e)],
            )
