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
import logging
from typing import List, Dict, Any

from .base import BaseCollector
from ..core.device import Device

logger = logging.getLogger(__name__)


class InventoryCollector(BaseCollector):
    """
    Коллектор инвентаризации оборудования.

    Собирает модули, трансиверы, блоки питания с серийниками.

    Example:
        collector = InventoryCollector()
        inventory = collector.collect(devices)
    """

    # Команды для разных платформ
    platform_commands = {
        "cisco_ios": "show inventory",
        "cisco_iosxe": "show inventory",
        "cisco_nxos": "show inventory",
        "arista_eos": "show inventory",
    }

    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show inventory.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Список компонентов
        """
        # Пробуем NTC Templates
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return self._normalize_data(data, device)

        # Fallback на regex
        items = self._parse_with_regex(output)
        # Добавляем manufacturer
        manufacturer = self._detect_manufacturer(device)
        for item in items:
            item["manufacturer"] = self._detect_manufacturer_by_pid(item.get("pid", "")) or manufacturer
        return items

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

    def _normalize_data(
        self,
        data: List[Dict[str, Any]],
        device: Device = None,
    ) -> List[Dict[str, Any]]:
        """
        Нормализует данные инвентаризации.

        Args:
            data: Сырые данные
            device: Устройство (для определения manufacturer)

        Returns:
            List[Dict]: Нормализованные данные
        """
        normalized = []

        # Определяем manufacturer по платформе устройства
        manufacturer = self._detect_manufacturer(device)

        for row in data:
            pid = row.get("pid", "")
            item = {
                "name": row.get("name", ""),
                "description": row.get("descr", row.get("description", "")),
                "pid": pid,
                "vid": row.get("vid", ""),
                "serial": row.get("sn", row.get("serial", "")),
                "manufacturer": self._detect_manufacturer_by_pid(pid) or manufacturer,
            }
            normalized.append(item)

        return normalized

    def _detect_manufacturer(self, device: Device = None) -> str:
        """
        Определяет производителя по платформе устройства.

        Args:
            device: Устройство

        Returns:
            str: Название производителя
        """
        if not device:
            return ""

        platform = device.device_type.lower()

        if "cisco" in platform:
            return "Cisco"
        elif "arista" in platform:
            return "Arista"
        elif "juniper" in platform:
            return "Juniper"
        elif "huawei" in platform:
            return "Huawei"
        elif "qtech" in platform:
            return "QTech"

        return ""

    def _detect_manufacturer_by_pid(self, pid: str) -> str:
        """
        Определяет производителя по PID (Product ID).

        Args:
            pid: Product ID

        Returns:
            str: Название производителя или пустая строка
        """
        if not pid:
            return ""

        pid_upper = pid.upper()

        # Cisco PIDs
        if any(x in pid_upper for x in ["WS-", "C9", "N9K", "N7K", "N5K", "ISR", "ASR", "SFP-", "GLC-", "XENPAK"]):
            return "Cisco"

        # Arista
        if pid_upper.startswith("DCS-") or "ARISTA" in pid_upper:
            return "Arista"

        # Juniper
        if pid_upper.startswith("EX") or pid_upper.startswith("QFX") or pid_upper.startswith("MX"):
            return "Juniper"

        return ""
