"""
Collector Service - сервис для сбора данных с устройств.

Обёртка над существующими collectors для использования в API.
"""

import asyncio
import logging
import time
import threading
from typing import List, Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor

from .task_manager import task_manager, TaskStatus

logger = logging.getLogger(__name__)

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
from network_collector.config import config
from . import history_service


class CollectorService:
    """Сервис для выполнения сбора данных."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        # Используем max_workers из config.yaml
        self._max_workers = config.connection.max_workers or 5
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)

    def _get_devices(self, device_list: Optional[List[str]] = None) -> List[Device]:
        """Получает список устройств.

        Args:
            device_list: Список IP адресов.
                        None или [] = использовать все устройства из device management
                        [ip1, ip2] = использовать указанные устройства
        """
        from .device_service import get_device_service

        # Явно передан непустой список IP адресов - ищем их в device_service
        if device_list:
            service = get_device_service()
            devices = []
            for ip in device_list:
                device_data = service.get_device_by_host(ip)
                if device_data:
                    # Используем полные данные устройства
                    devices.append(Device(
                        host=device_data.get("host", ip),
                        platform=device_data.get("device_type", "cisco_ios"),
                    ))
                else:
                    # Fallback: устройство не найдено в базе
                    # Используем cisco_ios по умолчанию
                    logger.warning(f"Устройство {ip} не найдено в device management, используем platform=cisco_ios")
                    devices.append(Device(host=ip, platform="cisco_ios"))
            return devices

        # Из device_service (JSON хранилище) - полные данные
        service = get_device_service()
        all_devices = service.get_all_devices()
        enabled_devices = service.get_enabled_devices()

        logger.info(f"Device Management: всего {len(all_devices)}, enabled {len(enabled_devices)}")

        if not all_devices:
            logger.warning("В Device Management нет устройств. Добавьте устройства или импортируйте из NetBox.")
        elif not enabled_devices:
            logger.warning(
                f"В Device Management {len(all_devices)} устройств, но все disabled. "
                "Включите устройства в Device Management (enabled=true)."
            )

        if enabled_devices:
            return [
                Device(
                    host=d.get("host"),
                    platform=d.get("device_type", "cisco_ios"),
                )
                for d in enabled_devices
            ]

        # Fallback: из devices_ips.py для обратной совместимости
        try:
            from network_collector.devices_ips import devices_list
            return [
                Device(
                    host=d.get("host", d) if isinstance(d, dict) else d,
                    platform=d.get("device_type", "cisco_ios") if isinstance(d, dict) else "cisco_ios",
                )
                for d in devices_list
            ]
        except ImportError:
            return []

    async def _run_in_executor(self, func, *args):
        """Запускает синхронную функцию в executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    def _run_in_background(
        self,
        task_id: str,
        collect_func: Callable,
        process_results: Callable[[list], dict],
        operation: str,
        devices: List[Device],
    ) -> None:
        """
        Запускает сбор данных в фоновом потоке.

        Args:
            task_id: ID задачи
            collect_func: Функция сбора (возвращает list)
            process_results: Функция обработки результатов (возвращает dict для task.result)
            operation: Название операции для history
            devices: Список устройств
        """
        def _background_worker():
            start_time = time.time()
            try:
                results = collect_func()
                processed = process_results(results)

                duration_ms = int((time.time() - start_time) * 1000)
                history_service.add_entry(
                    operation=operation,
                    status="success",
                    devices=[d.host for d in devices],
                    stats=processed,
                    duration_ms=duration_ms,
                )
                task_manager.complete_task(
                    task_id,
                    result=processed,
                    message=f"Завершено: {processed.get('total', 0)} записей",
                )
            except Exception as e:
                logger.error(f"Ошибка в background task {task_id}: {e}")
                duration_ms = int((time.time() - start_time) * 1000)
                history_service.add_entry(
                    operation=operation,
                    status="error",
                    devices=[d.host for d in devices],
                    duration_ms=duration_ms,
                    error=str(e),
                )
                task_manager.fail_task(task_id, str(e))

        thread = threading.Thread(target=_background_worker, daemon=True)
        thread.start()

    def _format_collector_error(self, error: Exception, devices: List[Device]) -> str:
        """Форматирует ошибку коллектора в понятное сообщение."""
        error_str = str(error)
        device_ips = [d.host for d in devices]

        # Типичные ошибки
        if "Authentication" in error_str or "auth" in error_str.lower():
            return f"Ошибка аутентификации. Проверьте SSH credentials. Устройства: {device_ips}"
        if "Connection" in error_str or "connect" in error_str.lower():
            return f"Ошибка подключения к устройствам: {device_ips}. Проверьте доступность по SSH."
        if "Timeout" in error_str or "timed out" in error_str.lower():
            return f"Таймаут подключения к устройствам: {device_ips}"
        if "platform" in error_str.lower():
            return f"Неизвестная платформа устройства. Проверьте device_type в Device Management."

        # Общая ошибка
        return f"Ошибка сбора данных: {error_str}. Устройства: {device_ips}"

    # =========================================================================
    # Devices
    # =========================================================================

    async def collect_devices(self, request: DevicesRequest) -> DevicesResponse:
        """Собирает информацию об устройствах."""
        start_time = time.time()
        devices = self._get_devices(request.devices)

        if not devices:
            return DevicesResponse(
                success=False,
                devices=[],
                errors=["No devices to collect from"],
            )

        # Создаём задачу для отслеживания прогресса
        task = task_manager.create_task(
            task_type="collect_devices",
            total_steps=1,
            total_items=len(devices),
        )
        task_manager.start_task(task.id, f"Сбор информации с {len(devices)} устройств")

        def _progress_callback(current: int, total: int, host: str, success: bool):
            """Callback для обновления прогресса по устройствам."""
            task_manager.update_item(task.id, current=current, name=host, total=total)

        def _collect():
            collector = DeviceCollector(credentials=self.credentials, max_workers=self._max_workers)
            return collector.collect_dicts(devices, progress_callback=_progress_callback)

        # Async mode: возвращаем task_id сразу, сбор в фоне
        if request.async_mode:
            def _process_results(results):
                return {"total": len(results), "data": results}

            self._run_in_background(
                task_id=task.id,
                collect_func=_collect,
                process_results=_process_results,
                operation="devices",
                devices=devices,
            )
            return DevicesResponse(success=True, devices=[], task_id=task.id)

        # Sync mode: ждём результат
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
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="devices",
                status="success",
                devices=[d.host for d in devices],
                stats={"total": len(device_infos)},
                duration_ms=duration_ms,
            )
            task_manager.complete_task(
                task.id,
                result={"total": len(device_infos)},
                message=f"Собрано {len(device_infos)} устройств",
            )
            return DevicesResponse(success=True, devices=device_infos, task_id=task.id)
        except Exception as e:
            logger.error(f"Ошибка сбора devices: {e}")
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="devices",
                status="error",
                devices=[d.host for d in devices],
                duration_ms=duration_ms,
                error=str(e),
            )
            task_manager.fail_task(task.id, str(e))
            return DevicesResponse(success=False, devices=[], errors=[str(e)], task_id=task.id)

    # =========================================================================
    # MAC
    # =========================================================================

    async def collect_mac(self, request: MACRequest) -> MACResponse:
        """Собирает MAC-адреса."""
        start_time = time.time()
        devices = self._get_devices(request.devices)

        if not devices:
            error_msg = (
                "Нет устройств для сбора. "
                "Добавьте устройства в Device Management или укажите IP адреса."
            )
            return MACResponse(
                success=False,
                entries=[],
                total=0,
                errors=[error_msg],
            )

        logger.info(f"Сбор MAC с {len(devices)} устройств: {[d.host for d in devices]}")

        # Создаём задачу для отслеживания прогресса
        task = task_manager.create_task(
            task_type="collect_mac",
            total_steps=1,
            total_items=len(devices),
        )
        task_manager.start_task(task.id, f"Сбор MAC-адресов с {len(devices)} устройств")

        def _progress_callback(current: int, total: int, host: str, success: bool):
            """Callback для обновления прогресса по устройствам."""
            task_manager.update_item(task.id, current=current, name=host, total=total)

        def _collect():
            collector = MACCollector(credentials=self.credentials, max_workers=self._max_workers)
            return collector.collect_dicts(devices, progress_callback=_progress_callback)

        # Async mode: возвращаем task_id сразу
        if request.async_mode:
            def _process_results(results):
                return {"total": len(results), "data": results}

            self._run_in_background(
                task_id=task.id,
                collect_func=_collect,
                process_results=_process_results,
                operation="mac",
                devices=devices,
            )
            return MACResponse(success=True, entries=[], total=0, task_id=task.id)

        # Sync mode
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
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="mac",
                status="success",
                devices=[d.host for d in devices],
                stats={"total": len(entries)},
                duration_ms=duration_ms,
            )
            task_manager.complete_task(
                task.id,
                result={"total": len(entries)},
                message=f"Собрано {len(entries)} MAC-адресов",
            )
            return MACResponse(success=True, entries=entries, total=len(entries), task_id=task.id)
        except Exception as e:
            error_msg = self._format_collector_error(e, devices)
            logger.error(f"Ошибка сбора MAC: {error_msg}")
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="mac",
                status="error",
                devices=[d.host for d in devices],
                duration_ms=duration_ms,
                error=error_msg,
            )
            task_manager.fail_task(task.id, error_msg)
            return MACResponse(success=False, entries=[], total=0, errors=[error_msg], task_id=task.id)

    # =========================================================================
    # LLDP
    # =========================================================================

    async def collect_lldp(self, request: LLDPRequest) -> LLDPResponse:
        """Собирает LLDP/CDP соседей."""
        start_time = time.time()
        devices = self._get_devices(request.devices)

        if not devices:
            return LLDPResponse(
                success=False,
                neighbors=[],
                total=0,
                errors=["No devices to collect from"],
            )

        # Создаём задачу для отслеживания прогресса
        task = task_manager.create_task(
            task_type="collect_lldp",
            total_steps=1,
            total_items=len(devices),
        )
        task_manager.start_task(task.id, f"Сбор LLDP/CDP с {len(devices)} устройств")

        def _progress_callback(current: int, total: int, host: str, success: bool):
            """Callback для обновления прогресса по устройствам."""
            task_manager.update_item(task.id, current=current, name=host, total=total)

        def _collect():
            collector = LLDPCollector(
                protocol=request.protocol.value,
                credentials=self.credentials,
                max_workers=self._max_workers,
            )
            return collector.collect_dicts(devices, progress_callback=_progress_callback)

        # Async mode
        if request.async_mode:
            def _process_results(results):
                return {"total": len(results), "data": results}

            self._run_in_background(
                task_id=task.id,
                collect_func=_collect,
                process_results=_process_results,
                operation="lldp",
                devices=devices,
            )
            return LLDPResponse(success=True, neighbors=[], total=0, task_id=task.id)

        # Sync mode
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
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="lldp",
                status="success",
                devices=[d.host for d in devices],
                stats={"total": len(neighbors)},
                duration_ms=duration_ms,
            )
            task_manager.complete_task(
                task.id,
                result={"total": len(neighbors)},
                message=f"Собрано {len(neighbors)} соседей",
            )
            return LLDPResponse(success=True, neighbors=neighbors, total=len(neighbors), task_id=task.id)
        except Exception as e:
            logger.error(f"Ошибка сбора LLDP: {e}")
            duration_ms = int((time.time() - start_time) * 1000)
            history_service.add_entry(
                operation="lldp",
                status="error",
                devices=[d.host for d in devices],
                duration_ms=duration_ms,
                error=str(e),
            )
            task_manager.fail_task(task.id, str(e))
            return LLDPResponse(success=False, neighbors=[], total=0, errors=[str(e)], task_id=task.id)

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

        # Создаём задачу для отслеживания прогресса
        task = task_manager.create_task(
            task_type="collect_interfaces",
            total_steps=1,
            total_items=len(devices),
        )
        task_manager.start_task(task.id, f"Сбор интерфейсов с {len(devices)} устройств")

        def _progress_callback(current: int, total: int, host: str, success: bool):
            """Callback для обновления прогресса по устройствам."""
            task_manager.update_item(task.id, current=current, name=host, total=total)

        def _collect():
            collector = InterfaceCollector(credentials=self.credentials, max_workers=self._max_workers)
            return collector.collect_dicts(devices, progress_callback=_progress_callback)

        # Async mode
        if request.async_mode:
            def _process_results(results):
                return {"total": len(results), "data": results}

            self._run_in_background(
                task_id=task.id,
                collect_func=_collect,
                process_results=_process_results,
                operation="interfaces",
                devices=devices,
            )
            return InterfacesResponse(success=True, interfaces=[], total=0, task_id=task.id)

        # Sync mode
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
            task_manager.complete_task(
                task.id,
                result={"total": len(interfaces)},
                message=f"Собрано {len(interfaces)} интерфейсов",
            )
            return InterfacesResponse(
                success=True, interfaces=interfaces, total=len(interfaces), task_id=task.id
            )
        except Exception as e:
            logger.error(f"Ошибка сбора interfaces: {e}")
            task_manager.fail_task(task.id, str(e))
            return InterfacesResponse(
                success=False, interfaces=[], total=0, errors=[str(e)], task_id=task.id
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

        # Создаём задачу для отслеживания прогресса
        task = task_manager.create_task(
            task_type="collect_inventory",
            total_steps=1,
            total_items=len(devices),
        )
        task_manager.start_task(task.id, f"Сбор inventory с {len(devices)} устройств")

        def _progress_callback(current: int, total: int, host: str, success: bool):
            """Callback для обновления прогресса по устройствам."""
            task_manager.update_item(task.id, current=current, name=host, total=total)

        def _collect():
            collector = InventoryCollector(credentials=self.credentials, max_workers=self._max_workers)
            return collector.collect_dicts(devices, progress_callback=_progress_callback)

        # Async mode
        if request.async_mode:
            def _process_results(results):
                return {"total": len(results), "data": results}

            self._run_in_background(
                task_id=task.id,
                collect_func=_collect,
                process_results=_process_results,
                operation="inventory",
                devices=devices,
            )
            return InventoryResponse(success=True, items=[], total=0, task_id=task.id)

        # Sync mode
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
            task_manager.complete_task(
                task.id,
                result={"total": len(items)},
                message=f"Собрано {len(items)} элементов inventory",
            )
            return InventoryResponse(success=True, items=items, total=len(items), task_id=task.id)
        except Exception as e:
            logger.error(f"Ошибка сбора inventory: {e}")
            task_manager.fail_task(task.id, str(e))
            return InventoryResponse(success=False, items=[], total=0, errors=[str(e)], task_id=task.id)

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

        # Создаём задачу для отслеживания прогресса
        task = task_manager.create_task(
            task_type="backup",
            total_steps=1,
            total_items=len(devices),
        )

        # Удаляем старые бэкапы (храним последние 10)
        import shutil
        from pathlib import Path
        backups_dir = Path("backups")
        if backups_dir.exists():
            folders = sorted(
                [f for f in backups_dir.iterdir() if f.is_dir()],
                key=lambda f: f.name,
                reverse=True,
            )
            # Удаляем все кроме последних 9 (10-й будет новый)
            for old_folder in folders[9:]:
                shutil.rmtree(old_folder)

        # Генерируем папку с датой для этого backup
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_folder = f"backups/{timestamp}"

        task_manager.start_task(task.id, f"Backup конфигураций с {len(devices)} устройств")

        def _progress_callback(current: int, total: int, host: str, success: bool):
            """Callback для обновления прогресса по устройствам."""
            task_manager.update_item(task.id, current=current, name=host, total=total)

        def _collect():
            collector = ConfigBackupCollector(
                credentials=self.credentials,
            )
            # backup() возвращает List[BackupResult], конвертируем в dicts
            results = collector.backup(devices, output_folder=output_folder)
            return [
                {
                    "hostname": r.hostname,
                    "device_ip": r.device_ip,
                    "success": r.success,
                    "file_path": r.file_path,
                    "error": r.error,
                }
                for r in results
            ]

        # Async mode
        if request.async_mode:
            def _process_results(results):
                success_count = sum(1 for r in results if r.get("success", False))
                return {
                    "success": success_count,
                    "failed": len(results) - success_count,
                    "data": results,
                    "output_folder": output_folder,  # Для скачивания ZIP
                }

            self._run_in_background(
                task_id=task.id,
                collect_func=_collect,
                process_results=_process_results,
                operation="backup",
                devices=devices,
            )
            return BackupResponse(
                success=True, results=[], total_success=0, total_failed=0, task_id=task.id
            )

        # Sync mode
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
            task_manager.complete_task(
                task.id,
                result={"success": success_count, "failed": len(backup_results) - success_count},
                message=f"Backup завершён: {success_count} успешно, {len(backup_results) - success_count} ошибок",
            )
            return BackupResponse(
                success=True,
                results=backup_results,
                total_success=success_count,
                total_failed=len(backup_results) - success_count,
                task_id=task.id,
            )
        except Exception as e:
            logger.error(f"Ошибка backup: {e}")
            task_manager.fail_task(task.id, str(e))
            return BackupResponse(
                success=False,
                results=[],
                total_success=0,
                total_failed=len(devices),
                task_id=task.id,
            )
