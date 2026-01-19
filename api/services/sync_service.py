"""
Sync Service - сервис синхронизации с NetBox.

Обёртка над netbox/sync.py для использования в API.
"""

import asyncio
import logging
import time
import threading
from typing import List
from concurrent.futures import ThreadPoolExecutor

from .task_manager import task_manager

logger = logging.getLogger(__name__)

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
from network_collector.config import config


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
        # Используем max_workers из config.yaml
        self._max_workers = config.connection.max_workers or 5
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

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

    def _calculate_steps(self, request: SyncRequest) -> List[str]:
        """Вычисляет список шагов для синхронизации."""
        steps = []
        if request.sync_all or request.create_devices or request.update_devices:
            steps.append("Devices")
        if request.sync_all or request.interfaces or request.cleanup_interfaces:
            steps.append("Interfaces")
        if request.sync_all or request.ip_addresses:
            steps.append("IP Addresses")
        if request.sync_all or request.vlans:
            steps.append("VLANs")
        if request.sync_all or request.inventory or request.cleanup_inventory:
            steps.append("Inventory")
        if request.sync_all or request.cables or request.cleanup_cables:
            steps.append("Cables")
        return steps

    def _run_sync_background(
        self,
        task_id: str,
        request: SyncRequest,
        devices: List,
    ):
        """Выполняет синхронизацию в фоновом режиме."""
        from . import history_service

        start_time = time.time()
        steps = self._calculate_steps(request)
        current_step = 0

        try:
            result = self._do_sync(request, devices, task_id, steps)

            duration_ms = int((time.time() - start_time) * 1000)

            # Записываем в историю (не для dry_run)
            if not result["dry_run"]:
                # Конвертируем DiffEntry в dict для JSON сериализации
                diff_list = [
                    d.model_dump() if hasattr(d, "model_dump") else dict(d)
                    for d in result.get("diff", [])
                ]
                history_service.add_entry(
                    operation="sync",
                    status="success" if result["success"] else "partial",
                    devices=[d.host for d in devices],
                    stats={
                        "devices": result["stats"]["devices"].model_dump() if hasattr(result["stats"]["devices"], "model_dump") else dict(result["stats"]["devices"]),
                        "interfaces": result["stats"]["interfaces"].model_dump() if hasattr(result["stats"]["interfaces"], "model_dump") else dict(result["stats"]["interfaces"]),
                        "ip_addresses": result["stats"]["ip_addresses"].model_dump() if hasattr(result["stats"]["ip_addresses"], "model_dump") else dict(result["stats"]["ip_addresses"]),
                        "cables": result["stats"]["cables"].model_dump() if hasattr(result["stats"]["cables"], "model_dump") else dict(result["stats"]["cables"]),
                    },
                    details=diff_list,
                    duration_ms=duration_ms,
                )

            task_manager.complete_task(
                task_id,
                result=result,
                message="Синхронизация завершена" if result["success"] else f"Синхронизация завершена с {len(result['errors'])} ошибками",
            )

        except Exception as e:
            logger.error(f"Ошибка синхронизации с NetBox: {e}")
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="sync",
                status="error",
                devices=[d.host for d in devices],
                duration_ms=duration_ms,
                error=str(e),
            )
            task_manager.fail_task(task_id, str(e))

    def _do_sync(self, request: SyncRequest, devices: List, task_id: str, steps: List[str]) -> dict:
        """Выполняет фактическую синхронизацию."""
        from . import history_service

        current_step_idx = 0

        def update_step(step_name: str):
            nonlocal current_step_idx
            task_manager.update_task(
                task_id,
                current_step=current_step_idx,
                message=f"Синхронизация: {step_name}",
            )
            current_step_idx += 1

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
            update_step("Devices")
            try:
                collector = DeviceCollector(credentials=self.credentials, max_workers=self._max_workers)
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
            update_step("Interfaces")
            try:
                collector = InterfaceCollector(credentials=self.credentials, max_workers=self._max_workers)
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
            update_step("IP Addresses")
            try:
                # IP адреса извлекаются из интерфейсов
                collector = InterfaceCollector(credentials=self.credentials, max_workers=self._max_workers)
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

                    for action, items in result.get("details", {}).items():
                        if action == "skip":
                            continue
                        # primary_ip - это dict, не list
                        if action == "primary_ip":
                            diff_entries.append(DiffEntry(
                                entity_type="primary_ip",
                                entity_name=items.get("address", ""),
                                action="update",
                                device=hostname,
                            ))
                            continue
                        for item in items:
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
            update_step("VLANs")
            try:
                collector = InterfaceCollector(credentials=self.credentials, max_workers=self._max_workers)
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

        # Inventory sync (модули, SFP, PSU)
        if request.sync_all or request.inventory or request.cleanup_inventory:
            update_step("Inventory")
            try:
                collector = InventoryCollector(credentials=self.credentials, max_workers=self._max_workers)
                inventory_data = collector.collect_dicts(devices)

                # Group by device
                by_device = {}
                for item in inventory_data:
                    hostname = item.get("hostname", "")
                    if hostname not in by_device:
                        by_device[hostname] = []
                    by_device[hostname].append(item)

                total_created = 0
                total_updated = 0
                total_deleted = 0
                total_skipped = 0

                for hostname, items in by_device.items():
                    result = sync.sync_inventory(
                        hostname, items, cleanup=request.cleanup_inventory
                    )
                    total_created += result.get("created", 0)
                    total_updated += result.get("updated", 0)
                    total_deleted += result.get("deleted", 0)
                    total_skipped += result.get("skipped", 0)

                    for action, action_items in result.get("details", {}).items():
                        for item in action_items:
                            diff_entries.append(DiffEntry(
                                entity_type="inventory",
                                entity_name=item.get("name", ""),
                                action=action,
                                device=hostname,
                            ))

                stats["inventory"] = SyncStats(
                    created=total_created,
                    updated=total_updated,
                    deleted=total_deleted,
                    skipped=total_skipped,
                )

            except Exception as e:
                errors.append(f"Inventory sync error: {e}")

        if request.sync_all or request.cables or request.cleanup_cables:
            update_step("Cables")
            try:
                # Используем protocol из запроса
                protocol = request.protocol.value if hasattr(request.protocol, 'value') else str(request.protocol)
                collector = LLDPCollector(
                    protocol=protocol,
                    credentials=self.credentials,
                    max_workers=self._max_workers,
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

    async def sync(self, request: SyncRequest) -> SyncResponse:
        """Выполняет синхронизацию с NetBox."""
        from . import history_service

        start_time = time.time()
        devices = self._get_devices(request.devices)

        if not devices:
            return SyncResponse(
                success=False,
                dry_run=request.dry_run,
                errors=["No devices to sync"],
            )

        # Создаём задачу для отслеживания прогресса
        steps = self._calculate_steps(request)

        task = task_manager.create_task(
            task_type="sync_netbox",
            total_steps=len(steps) if steps else 1,
            total_items=len(devices),
            steps=steps,
        )
        task_manager.start_task(
            task.id,
            f"Синхронизация {'(dry-run)' if request.dry_run else ''} с {len(devices)} устройствами"
        )

        # Async mode - запускаем в фоне и возвращаем сразу task_id
        if request.async_mode:
            thread = threading.Thread(
                target=self._run_sync_background,
                args=(task.id, request, devices),
                daemon=True,
            )
            thread.start()

            return SyncResponse(
                success=True,
                dry_run=request.dry_run,
                task_id=task.id,
            )

        # Sync mode - выполняем и ждём результат
        try:
            result = await self._run_in_executor(
                lambda: self._do_sync(request, devices, task.id, steps)
            )
            duration_ms = int((time.time() - start_time) * 1000)

            # Записываем в историю (не для dry_run)
            if not result["dry_run"]:
                # Конвертируем DiffEntry в dict для JSON сериализации
                diff_list = [
                    d.model_dump() if hasattr(d, "model_dump") else dict(d)
                    for d in result.get("diff", [])
                ]
                history_service.add_entry(
                    operation="sync",
                    status="success" if result["success"] else "partial",
                    devices=[d.host for d in devices],
                    stats={
                        "devices": result["stats"]["devices"].model_dump() if hasattr(result["stats"]["devices"], "model_dump") else dict(result["stats"]["devices"]),
                        "interfaces": result["stats"]["interfaces"].model_dump() if hasattr(result["stats"]["interfaces"], "model_dump") else dict(result["stats"]["interfaces"]),
                        "ip_addresses": result["stats"]["ip_addresses"].model_dump() if hasattr(result["stats"]["ip_addresses"], "model_dump") else dict(result["stats"]["ip_addresses"]),
                        "cables": result["stats"]["cables"].model_dump() if hasattr(result["stats"]["cables"], "model_dump") else dict(result["stats"]["cables"]),
                    },
                    details=diff_list,
                    duration_ms=duration_ms,
                )

            task_manager.complete_task(
                task.id,
                result={"success": result["success"], "errors_count": len(result["errors"])},
                message="Синхронизация завершена" if result["success"] else f"Синхронизация завершена с {len(result['errors'])} ошибками",
            )

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
                task_id=task.id,
            )
        except Exception as e:
            logger.error(f"Ошибка синхронизации с NetBox: {e}")
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="sync",
                status="error",
                devices=[d.host for d in devices],
                duration_ms=duration_ms,
                error=str(e),
            )
            task_manager.fail_task(task.id, str(e))
            return SyncResponse(
                success=False,
                dry_run=request.dry_run,
                errors=[str(e)],
                task_id=task.id,
            )
