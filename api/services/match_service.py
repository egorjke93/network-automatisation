"""
Match Service - сопоставление MAC с хостами.

Использует DescriptionMatcher для сопоставления MAC-адресов
с данными из справочника хостов (Excel/CSV).
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..schemas import Credentials, MatchRequest, MatchResponse, MatchEntry
from network_collector.configurator import DescriptionMatcher

logger = logging.getLogger(__name__)


class MatchService:
    """Сервис сопоставления MAC с хостами."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self._executor = ThreadPoolExecutor(max_workers=2)

    async def _run_in_executor(self, func, *args):
        """Запускает синхронную функцию в executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    async def match(self, request: MatchRequest) -> MatchResponse:
        """
        Сопоставляет MAC-адреса с хостами.

        Args:
            request: Запрос с путями к файлам

        Returns:
            MatchResponse: Результаты сопоставления
        """
        try:
            result = await self._run_in_executor(self._do_match, request)
            return result
        except FileNotFoundError as e:
            logger.error(f"Файл не найден: {e}")
            return MatchResponse(
                success=False,
                entries=[],
                matched=0,
                unmatched=0,
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"Ошибка сопоставления: {e}")
            return MatchResponse(
                success=False,
                entries=[],
                matched=0,
                unmatched=0,
                errors=[str(e)],
            )

    def _do_match(self, request: MatchRequest) -> MatchResponse:
        """Синхронная логика сопоставления."""
        # Проверяем файл MAC
        mac_path = Path(request.mac_file)
        if not mac_path.exists():
            raise FileNotFoundError(f"MAC файл не найден: {request.mac_file}")

        # Загружаем MAC данные
        logger.info(f"Загрузка MAC данных из {mac_path}...")
        mac_df = pd.read_excel(mac_path)
        # Нормализуем имена колонок
        mac_df.columns = [col.lower().replace(" ", "_") for col in mac_df.columns]
        mac_data = mac_df.to_dict("records")
        logger.info(f"Загружено {len(mac_data)} записей MAC")

        # Создаём matcher
        matcher = DescriptionMatcher()

        # Загружаем справочник хостов в зависимости от источника
        if request.source in ("csv", "excel"):
            if request.hosts_folder:
                matcher.load_hosts_folder(
                    request.hosts_folder,
                    mac_column=request.mac_column,
                    name_column=request.name_column,
                )
            elif request.hosts_file:
                matcher.load_hosts_file(
                    request.hosts_file,
                    mac_column=request.mac_column,
                    name_column=request.name_column,
                )
            else:
                raise ValueError(
                    "Для source='excel'/'csv' требуется hosts_file или hosts_folder"
                )
        elif request.source == "glpi":
            # TODO: Реализовать интеграцию с GLPI API
            raise NotImplementedError("GLPI интеграция пока не реализована")
        elif request.source == "netbox":
            # TODO: Реализовать интеграцию с NetBox API
            raise NotImplementedError("NetBox интеграция пока не реализована")
        else:
            raise ValueError(f"Неизвестный источник: {request.source}")

        # Сопоставляем
        matched_entries = matcher.match_mac_data(
            mac_data,
            mac_field="mac",
            hostname_field="device",
            interface_field="port",
            vlan_field="vlan",
            description_field="description",
        )

        # Конвертируем в API формат
        entries = []
        for entry in matched_entries:
            entries.append(MatchEntry(
                mac=entry.mac,
                interface=entry.interface,
                vlan=entry.vlan,
                hostname=entry.hostname,
                device_ip=entry.device_ip,
                matched_host=entry.host_name if entry.matched else None,
                matched_ip=None,  # IP хоста не собираем
            ))

        # Статистика
        stats = matcher.get_stats()
        matched_count = stats["matched"]
        unmatched_count = stats["unmatched"]

        logger.info(
            f"Сопоставление завершено: {matched_count} совпадений, "
            f"{unmatched_count} без совпадений"
        )

        return MatchResponse(
            success=True,
            entries=entries,
            matched=matched_count,
            unmatched=unmatched_count,
        )
