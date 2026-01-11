"""
Collector Service - сервис для сбора данных с устройств.

Обёртка над существующими collectors для использования в API.
"""

import asyncio
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from ..schemas import (
    Credentials,
    DevicesRequest,
    DevicesResponse,
    DeviceInfo,
    MACRequest,
    MACResponse,
    MACEntry,
    LLDPRequest,
    LLDPResponse,
    LLDPNeighborInfo,
    InterfacesRequest,
    InterfacesResponse,
    InterfaceInfo,
    InventoryRequest,
    InventoryResponse,
    InventoryItem,
    BackupRequest,
    BackupResponse,
    BackupResult,
)

# Импорт существующих collectors
from network_collector.collectors import (
    DeviceCollector,
    MACCollector,
    LLDPCollector,
    InterfaceCollector,
    InventoryCollector,
    ConfigBackupCollector,
)
from network_collector.core.device import Device


class CollectorService:
    """Сервис для выполнения сбора данных."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self._executor = ThreadPoolExecutor(max_workers=10)

    def _get_devices(self, device_list: Optional[List[str]] = None) -> List[Device]:
        """Получает список устройств.

        Args:
            device_list: Список IP адресов.
                        None = использовать устройства из конфига
                        [] = пустой список (нет устройств)
        """
        # Явно передан список (даже пустой) - используем его
        if device_list is not None:
            return [Device(host=ip) for ip in device_list]

        # Из device_service (JSON хранилище)
        from .device_service import get_device_service
        service = get_device_service()
        hosts = service.get_device_hosts()

        if hosts:
            return [Device(host=ip) for ip in hosts]

        # Fallback: из devices_ips.py для обратной совместимости
        try:
            from network_collector.devices_ips import devices_list
            return [Device(host=d.get("host", d) if isinstance(d, dict) else d) for d in devices_list]
        except ImportError:
            return []

    async def _run_in_executor(self, func, *args):
        """Запускает синхронную функцию в executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    # =========================================================================
    # Devices
    # =========================================================================

    async def collect_devices(self, request: DevicesRequest) -> DevicesResponse:
        """Собирает информацию об устройствах."""
        devices = self._get_devices(request.devices)

        if not devices:
            return DevicesResponse(
                success=False,
                devices=[],
                errors=["No devices to collect from"],
            )

        def _collect():
            collector = DeviceCollector(credentials=self.credentials)
            return collector.collect_dicts(devices)

        try:
            results = await self._run_in_executor(_collect)
            device_infos = [
                DeviceInfo(
                    hostname=r.get("hostname", ""),
                    ip_address=r.get("device_ip", ""),
                    platform=r.get("platform", ""),
                    model=r.get("model", ""),
                    serial=r.get("serial", ""),
                    version=r.get("version", ""),
                    uptime=r.get("uptime", ""),
                )
                for r in results
            ]
            return DevicesResponse(success=True, devices=device_infos)
        except Exception as e:
            return DevicesResponse(success=False, devices=[], errors=[str(e)])

    # =========================================================================
    # MAC
    # =========================================================================

    async def collect_mac(self, request: MACRequest) -> MACResponse:
        """Собирает MAC-адреса."""
        devices = self._get_devices(request.devices)

        if not devices:
            return MACResponse(
                success=False,
                entries=[],
                total=0,
                errors=["No devices to collect from"],
            )

        def _collect():
            collector = MACCollector(credentials=self.credentials)
            return collector.collect_dicts(devices)

        try:
            results = await self._run_in_executor(_collect)
            entries = [
                MACEntry(
                    mac=r.get("mac", ""),
                    interface=r.get("interface", ""),
                    vlan=str(r.get("vlan", "")),
                    hostname=r.get("hostname", ""),
                    device_ip=r.get("device_ip", ""),
                    type=r.get("type", ""),
                )
                for r in results
            ]
            return MACResponse(success=True, entries=entries, total=len(entries))
        except Exception as e:
            return MACResponse(success=False, entries=[], total=0, errors=[str(e)])

    # =========================================================================
    # LLDP
    # =========================================================================

    async def collect_lldp(self, request: LLDPRequest) -> LLDPResponse:
        """Собирает LLDP/CDP соседей."""
        devices = self._get_devices(request.devices)

        if not devices:
            return LLDPResponse(
                success=False,
                neighbors=[],
                total=0,
                errors=["No devices to collect from"],
            )

        def _collect():
            collector = LLDPCollector(
                protocol=request.protocol.value,
                credentials=self.credentials,
            )
            return collector.collect_dicts(devices)

        try:
            results = await self._run_in_executor(_collect)
            neighbors = [
                LLDPNeighborInfo(
                    hostname=r.get("hostname", ""),
                    device_ip=r.get("device_ip", ""),
                    local_interface=r.get("local_interface", ""),
                    remote_hostname=r.get("remote_hostname", ""),
                    remote_port=r.get("remote_port"),
                    remote_ip=r.get("remote_ip"),
                    remote_mac=r.get("remote_mac"),
                    remote_platform=r.get("remote_platform"),
                    protocol=r.get("protocol", ""),
                )
                for r in results
            ]
            return LLDPResponse(success=True, neighbors=neighbors, total=len(neighbors))
        except Exception as e:
            return LLDPResponse(success=False, neighbors=[], total=0, errors=[str(e)])

    # =========================================================================
    # Interfaces
    # =========================================================================

    async def collect_interfaces(self, request: InterfacesRequest) -> InterfacesResponse:
        """Собирает интерфейсы."""
        devices = self._get_devices(request.devices)

        if not devices:
            return InterfacesResponse(
                success=False,
                interfaces=[],
                total=0,
                errors=["No devices to collect from"],
            )

        def _collect():
            collector = InterfaceCollector(credentials=self.credentials)
            return collector.collect_dicts(devices)

        try:
            results = await self._run_in_executor(_collect)
            interfaces = [
                InterfaceInfo(
                    name=r.get("name", ""),
                    description=r.get("description"),
                    status=r.get("status", ""),
                    ip_address=r.get("ip_address"),
                    mac=r.get("mac"),
                    speed=r.get("speed"),
                    duplex=r.get("duplex"),
                    vlan=r.get("vlan"),
                    mode=r.get("mode"),
                    hostname=r.get("hostname", ""),
                    device_ip=r.get("device_ip", ""),
                )
                for r in results
            ]
            return InterfacesResponse(
                success=True, interfaces=interfaces, total=len(interfaces)
            )
        except Exception as e:
            return InterfacesResponse(
                success=False, interfaces=[], total=0, errors=[str(e)]
            )

    # =========================================================================
    # Inventory
    # =========================================================================

    async def collect_inventory(self, request: InventoryRequest) -> InventoryResponse:
        """Собирает inventory."""
        devices = self._get_devices(request.devices)

        if not devices:
            return InventoryResponse(
                success=False,
                items=[],
                total=0,
                errors=["No devices to collect from"],
            )

        def _collect():
            collector = InventoryCollector(credentials=self.credentials)
            return collector.collect_dicts(devices)

        try:
            results = await self._run_in_executor(_collect)
            items = [
                InventoryItem(
                    name=r.get("name", ""),
                    description=r.get("description"),
                    pid=r.get("pid"),
                    serial=r.get("serial"),
                    hostname=r.get("hostname", ""),
                    device_ip=r.get("device_ip", ""),
                )
                for r in results
            ]
            return InventoryResponse(success=True, items=items, total=len(items))
        except Exception as e:
            return InventoryResponse(success=False, items=[], total=0, errors=[str(e)])

    # =========================================================================
    # Backup
    # =========================================================================

    async def run_backup(self, request: BackupRequest) -> BackupResponse:
        """Выполняет backup конфигураций."""
        devices = self._get_devices(request.devices)

        if not devices:
            return BackupResponse(
                success=False,
                results=[],
                total_success=0,
                total_failed=0,
            )

        def _collect():
            collector = ConfigBackupCollector(
                credentials=self.credentials,
                output_dir=request.output_dir,
            )
            return collector.collect_dicts(devices)

        try:
            results = await self._run_in_executor(_collect)
            backup_results = [
                BackupResult(
                    hostname=r.get("hostname", ""),
                    device_ip=r.get("device_ip", ""),
                    success=r.get("success", False),
                    file_path=r.get("file_path"),
                    error=r.get("error"),
                )
                for r in results
            ]
            success_count = sum(1 for r in backup_results if r.success)
            return BackupResponse(
                success=True,
                results=backup_results,
                total_success=success_count,
                total_failed=len(backup_results) - success_count,
            )
        except Exception as e:
            return BackupResponse(
                success=False,
                results=[],
                total_success=0,
                total_failed=len(devices),
            )
