"""
Коллектор инвентаризации оборудования.

Собирает информацию о модулях, трансиверах, блоках питания.
Использует команду show inventory.

Данные для NetBox:
- name: Имя компонента
- pid: Product ID (модель)
- serial: Серийный номер
- description: Описание

Пример использования:
    collector = InventoryCollector()
    data = collector.collect(devices)
"""

import re
from typing import List, Dict, Any

from .base import BaseCollector
from ..core.device import Device
from ..core.models import InventoryItem
from ..core.domain.inventory import InventoryNormalizer
from ..core.constants import COLLECTOR_COMMANDS
from ..core.constants.commands import SECONDARY_COMMANDS
from ..core.logging import get_logger
from ..core.exceptions import (
    ConnectionError,
    AuthenticationError,
    TimeoutError,
    format_error_for_log,
)
from ..parsers.textfsm_parser import NTCParser

logger = get_logger(__name__)


class InventoryCollector(BaseCollector):
    """
    Коллектор инвентаризации оборудования.

    Собирает модули, трансиверы, блоки питания с серийниками.

    Example:
        collector = InventoryCollector()
        inventory = collector.collect(devices)  # List[Dict]

        # Или типизированные модели
        items = collector.collect_models(devices)  # List[InventoryItem]
    """

    # Типизированная модель
    model_class = InventoryItem

    # Команды для разных платформ (из централизованного хранилища)
    platform_commands = COLLECTOR_COMMANDS.get("inventory", {})

    # Команды для трансиверов (из централизованного хранилища commands.py)
    transceiver_commands = SECONDARY_COMMANDS.get("transceiver", {})

    def __init__(
        self,
        collect_transceivers: bool = True,
        **kwargs,
    ):
        """
        Инициализация коллектора инвентаризации.

        Args:
            collect_transceivers: Собирать трансиверы (для NX-OS из show interface transceiver)
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.collect_transceivers = collect_transceivers
        self._normalizer = InventoryNormalizer()
        self._parser = NTCParser()

    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show inventory.

        Возвращает сырые данные, нормализация в _collect_from_device.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Сырые данные компонентов
        """
        # Пробуем NTC Templates
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return data  # Raw data, normalization in _collect_from_device

        # Fallback на regex
        return self._parse_with_regex(output)

    def _parse_with_regex(self, output: str) -> List[Dict[str, Any]]:
        """
        Парсит вывод с помощью regex.

        Args:
            output: Сырой вывод

        Returns:
            List[Dict]: Компоненты
        """
        items = []

        # Паттерн для Cisco show inventory
        # NAME: "Chassis", DESCR: "Cisco ..."
        # PID: WS-C3750X-48P-S, VID: V02, SN: FDO1234X5YZ
        pattern = re.compile(
            r'NAME:\s*"([^"]+)".*?DESCR:\s*"([^"]*)".*?'
            r'PID:\s*(\S+).*?(?:VID:\s*(\S+).*?)?SN:\s*(\S+)',
            re.DOTALL | re.IGNORECASE
        )

        for match in pattern.finditer(output):
            name, descr, pid, vid, serial = match.groups()

            items.append({
                "name": name.strip(),
                "description": descr.strip() if descr else "",
                "pid": pid.strip() if pid else "",
                "vid": vid.strip() if vid else "",
                "serial": serial.strip() if serial else "",
            })

        return items

    def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
        """
        Собирает данные инвентаризации с устройства.

        Для NX-OS/QTech дополнительно собирает трансиверы из show interface transceiver.
        QTech: show inventory отсутствует, инвентаризация только через transceiver.

        Args:
            device: Устройство

        Returns:
            List[Dict]: Данные инвентаризации
        """
        command = self._get_command(device)
        tr_cmd = self.transceiver_commands.get(device.platform) if self.collect_transceivers else None

        # Нет ни основной команды, ни transceiver
        if not command and not tr_cmd:
            logger.warning(f"Нет команды inventory для {device.platform}")
            return []

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                hostname = self._init_device_connection(conn, device)

                # 1. Парсим сырые данные show inventory (если команда есть)
                raw_data = []
                if command:
                    response = conn.send_command(command)
                    raw_data = self._parse_output(response.result, device)

                # --format parsed: сырые данные TextFSM, без нормализации
                if self._skip_normalize:
                    self._add_metadata_to_rows(raw_data, hostname, device.host)
                    logger.info(f"{hostname}: собрано {len(raw_data)} компонентов (parsed, без нормализации)")
                    return raw_data

                # 2. Domain Layer: нормализация
                data = self._normalizer.normalize_dicts(
                    raw_data,
                    platform=device.platform,
                    hostname=hostname,
                    device_ip=device.host,
                )

                # 3. Собираем трансиверы (NX-OS, QTech)
                transceiver_items = []
                if tr_cmd:
                    try:
                        tr_response = conn.send_command(tr_cmd)
                        # Парсим через NTCParser (поддержка кастомных шаблонов)
                        parsed = self._parser.parse(
                            output=tr_response.result,
                            platform=device.platform,
                            command=tr_cmd,
                            normalize=False,
                        )
                        # Domain Layer: нормализация трансиверов
                        transceiver_items = self._normalizer.normalize_transceivers(
                            parsed,
                            platform=device.platform,
                        )
                        # Добавляем hostname/device_ip
                        self._add_metadata_to_rows(transceiver_items, hostname, device.host)
                    except Exception as e:
                        logger.debug(f"Ошибка получения transceivers: {e}")

                # 4. Domain Layer: merge inventory + transceivers
                all_items = self._normalizer.merge_with_transceivers(data, transceiver_items)

                if transceiver_items:
                    logger.info(f"{hostname}: собрано {len(all_items)} компонентов inventory (+{len(transceiver_items)} трансиверов)")
                else:
                    logger.info(f"{hostname}: собрано {len(all_items)} компонентов inventory")
                return all_items

        except Exception as e:
            return self._handle_collection_error(e, device)
