"""
Push Service - push описаний интерфейсов на устройства.

Использует DescriptionPusher для применения описаний
из результатов сопоставления (match).
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..schemas import (
    Credentials,
    PushDescriptionsRequest,
    PushDescriptionsResponse,
    PushResult,
)
from network_collector.configurator import DescriptionPusher
from network_collector.core.device import Device

logger = logging.getLogger(__name__)


class PushService:
    """Сервис push описаний на устройства."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def _run_in_executor(self, func, *args):
        """Запускает синхронную функцию в executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    async def push(self, request: PushDescriptionsRequest) -> PushDescriptionsResponse:
        """
        Отправляет описания на устройства.

        Args:
            request: Запрос с файлом описаний и опциями

        Returns:
            PushDescriptionsResponse: Результаты применения
        """
        try:
            result = await self._run_in_executor(self._do_push, request)
            return result
        except FileNotFoundError as e:
            logger.error(f"Файл не найден: {e}")
            return PushDescriptionsResponse(
                success=False,
                dry_run=request.dry_run,
                results=[],
                total_success=0,
                total_failed=0,
                total_skipped=0,
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"Ошибка push описаний: {e}")
            return PushDescriptionsResponse(
                success=False,
                dry_run=request.dry_run,
                results=[],
                total_success=0,
                total_failed=0,
                total_skipped=0,
                errors=[str(e)],
            )

    def _do_push(self, request: PushDescriptionsRequest) -> PushDescriptionsResponse:
        """Синхронная логика push описаний."""
        # Проверяем файл
        source_path = Path(request.source_file)
        if not source_path.exists():
            raise FileNotFoundError(f"Файл не найден: {request.source_file}")

        # Загружаем данные
        logger.info(f"Загрузка данных из {source_path}...")
        df = pd.read_excel(source_path)

        # Фильтруем только сопоставленные записи
        if "Matched" in df.columns:
            matched_df = df[df["Matched"] == "Yes"]
        else:
            # Если нет колонки Matched, используем все записи с Host_Name
            matched_df = df[df["Host_Name"].notna() & (df["Host_Name"] != "")]

        if matched_df.empty:
            logger.warning("Нет сопоставленных записей для применения")
            return PushDescriptionsResponse(
                success=True,
                dry_run=request.dry_run,
                results=[],
                total_success=0,
                total_failed=0,
                total_skipped=0,
            )

        # Генерируем команды и результаты
        commands: Dict[str, List[str]] = {}
        device_names: Dict[str, str] = {}
        push_results: List[PushResult] = []
        skipped_count = 0

        for _, row in matched_df.iterrows():
            hostname = row.get("Device", "")
            device_ip = row.get("IP", "")
            interface = row.get("Interface", "")
            host_name = row.get("Host_Name", "")
            current_desc = row.get("Current_Description", "")

            if not device_ip or not interface or not host_name:
                continue

            # Проверяем условия
            is_empty = pd.isna(current_desc) or str(current_desc).strip() == ""

            if request.only_empty and not is_empty:
                skipped_count += 1
                continue

            if not request.overwrite and not is_empty:
                skipped_count += 1
                continue

            # Пропускаем если текущее описание совпадает с новым
            if str(current_desc).strip() == str(host_name).strip():
                skipped_count += 1
                continue

            # Добавляем команды
            if device_ip not in commands:
                commands[device_ip] = []
                device_names[device_ip] = hostname

            commands[device_ip].append(f"interface {interface}")
            commands[device_ip].append(f"description {host_name}")

            # Добавляем в результаты (для отображения)
            push_results.append(PushResult(
                device=f"{hostname} ({device_ip})" if hostname else device_ip,
                interface=interface,
                old_description=str(current_desc) if pd.notna(current_desc) else None,
                new_description=str(host_name),
                success=True,  # Будет обновлено после push
                error=None,
            ))

        if not commands:
            logger.warning("Нет команд для применения")
            return PushDescriptionsResponse(
                success=True,
                dry_run=request.dry_run,
                results=push_results,
                total_success=0,
                total_failed=0,
                total_skipped=skipped_count,
            )

        total_interfaces = sum(len(cmds) // 2 for cmds in commands.values())
        logger.info(
            f"Будет обновлено {total_interfaces} интерфейсов на {len(commands)} устройствах"
        )

        # Dry-run режим
        if request.dry_run:
            logger.info("=== DRY RUN (команды не будут применены) ===")
            for device_ip, cmds in commands.items():
                display_name = device_names.get(device_ip, device_ip)
                logger.info(f"\n{display_name} ({device_ip}):")
                for cmd in cmds:
                    logger.info(f"  {cmd}")

            return PushDescriptionsResponse(
                success=True,
                dry_run=True,
                results=push_results,
                total_success=len(push_results),
                total_failed=0,
                total_skipped=skipped_count,
            )

        # Получаем устройства
        devices = self._get_devices(request.devices, list(commands.keys()))

        # Применяем
        pusher = DescriptionPusher(self.credentials)
        config_results = pusher.push_descriptions(devices, commands, dry_run=False)

        # Обновляем результаты
        success_devices: Set[str] = set()
        failed_devices: Dict[str, str] = {}

        for result in config_results:
            if result.success:
                success_devices.add(result.device)
            else:
                failed_devices[result.device] = result.error

        # Обновляем статус в push_results
        success_count = 0
        failed_count = 0

        for pr in push_results:
            # Извлекаем IP из device строки
            device_ip = pr.device.split("(")[-1].rstrip(")") if "(" in pr.device else pr.device

            if device_ip in success_devices:
                pr.success = True
                success_count += 1
            elif device_ip in failed_devices:
                pr.success = False
                pr.error = failed_devices[device_ip]
                failed_count += 1
            else:
                # Устройство не найдено
                pr.success = False
                pr.error = "Устройство не найдено в списке"
                failed_count += 1

        logger.info(f"=== РЕЗУЛЬТАТЫ ===")
        logger.info(f"Успешно: {success_count}")
        logger.info(f"Ошибки: {failed_count}")
        logger.info(f"Пропущено: {skipped_count}")

        return PushDescriptionsResponse(
            success=failed_count == 0,
            dry_run=False,
            results=push_results,
            total_success=success_count,
            total_failed=failed_count,
            total_skipped=skipped_count,
        )

    def _get_devices(
        self,
        device_list: Optional[List[str]],
        required_ips: List[str],
    ) -> List[Device]:
        """
        Получает список устройств для push.

        Args:
            device_list: Явно указанный список IP
            required_ips: IP, на которые нужно отправить команды

        Returns:
            List[Device]: Список устройств
        """
        from .common import get_devices_for_operation

        # Если явно указан список - используем его с обогащением из device_service
        if device_list:
            return get_devices_for_operation(device_list)

        # Иначе используем IP из файла с обогащением
        return get_devices_for_operation(required_ips)
