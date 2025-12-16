"""
Коллектор информации об интерфейсах.

Собирает статус, описание, MAC, IP-адреса, ошибки интерфейсов.
Включает Vlan SVI интерфейсы с IP-адресами.
Поддерживает Cisco, Arista, Juniper.

Пример использования:
    collector = InterfaceCollector()
    data = collector.collect(devices)

    # Только определённые поля
    collector = InterfaceCollector(
        textfsm_fields=["interface", "status", "ip_address"]
    )
"""

import re
import logging
from typing import List, Dict, Any, Optional

from .base import BaseCollector
from ..core.device import Device

logger = logging.getLogger(__name__)


class InterfaceCollector(BaseCollector):
    """
    Коллектор информации об интерфейсах.
    
    Собирает статус, описание, VLAN, ошибки.
    
    Attributes:
        include_errors: Собирать статистику ошибок
        
    Example:
        collector = InterfaceCollector(include_errors=True)
        interfaces = collector.collect(devices)
    """
    
    # Команды для разных платформ
    # Используем "show interfaces" для получения полной информации:
    # статус, MAC, IP-адреса (включая Vlan SVI), description
    platform_commands = {
        "cisco_ios": "show interfaces",
        "cisco_iosxe": "show interfaces",
        "cisco_nxos": "show interface",
        "arista_eos": "show interfaces",
        "juniper_junos": "show interfaces extensive",
    }

    # Команды для ошибок
    error_commands = {
        "cisco_ios": "show interfaces | include errors|CRC|input|output",
        "cisco_iosxe": "show interfaces | include errors|CRC|input|output",
        "cisco_nxos": "show interface counters errors",
        "arista_eos": "show interfaces counters errors",
    }
    
    def __init__(
        self,
        include_errors: bool = False,
        **kwargs,
    ):
        """
        Инициализация коллектора интерфейсов.
        
        Args:
            include_errors: Собирать статистику ошибок
            **kwargs: Аргументы для BaseCollector
        """
        super().__init__(**kwargs)
        self.include_errors = include_errors
    
    def _parse_output(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды show interfaces.

        Args:
            output: Сырой вывод команды
            device: Устройство

        Returns:
            List[Dict]: Список интерфейсов с полями:
                - interface: имя интерфейса
                - status: up/down/disabled
                - mac: MAC-адрес интерфейса
                - ip_address: IP-адрес (если есть)
                - prefix_length: маска сети
                - description: описание
                - speed, duplex, mtu и др.
        """
        # Пробуем TextFSM
        if self.use_ntc:
            data = self._parse_with_textfsm(output, device)
            if data:
                return self._normalize_data(data)

        # Fallback на regex
        return self._parse_with_regex(output, device)
    
    def _parse_with_regex(
        self,
        output: str,
        device: Device,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод show interfaces с помощью regex (fallback).

        Args:
            output: Сырой вывод
            device: Устройство

        Returns:
            List[Dict]: Интерфейсы
        """
        interfaces = []
        current_interface = None

        # Паттерны для Cisco IOS "show interfaces"
        intf_pattern = re.compile(r"^(\S+)\s+is\s+(up|down|administratively down)", re.MULTILINE)
        ip_pattern = re.compile(r"Internet address is (\d+\.\d+\.\d+\.\d+)/(\d+)")
        mac_pattern = re.compile(r"address is ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})")
        desc_pattern = re.compile(r"Description: (.+)")
        mtu_pattern = re.compile(r"MTU (\d+) bytes")

        for line in output.splitlines():
            # Новый интерфейс
            intf_match = intf_pattern.match(line)
            if intf_match:
                if current_interface:
                    interfaces.append(current_interface)
                current_interface = {
                    "interface": intf_match.group(1),
                    "status": intf_match.group(2),
                    "ip_address": "",
                    "prefix_length": "",
                    "mac": "",
                    "description": "",
                    "mtu": "",
                }
                continue

            if current_interface:
                # IP-адрес
                ip_match = ip_pattern.search(line)
                if ip_match:
                    current_interface["ip_address"] = ip_match.group(1)
                    current_interface["prefix_length"] = ip_match.group(2)

                # MAC-адрес
                mac_match = mac_pattern.search(line)
                if mac_match:
                    current_interface["mac"] = mac_match.group(1)

                # Description
                desc_match = desc_pattern.search(line)
                if desc_match:
                    current_interface["description"] = desc_match.group(1).strip()

                # MTU
                mtu_match = mtu_pattern.search(line)
                if mtu_match:
                    current_interface["mtu"] = mtu_match.group(1)

        # Последний интерфейс
        if current_interface:
            interfaces.append(current_interface)

        return self._normalize_data(interfaces)
    
    def _normalize_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Нормализует данные интерфейсов.

        Args:
            data: Сырые данные

        Returns:
            List[Dict]: Нормализованные данные
        """
        # Маппинг статусов из show interfaces
        status_map = {
            "connected": "up",
            "up": "up",
            "notconnect": "down",
            "down": "down",
            "disabled": "disabled",
            "err-disabled": "error",
            "administratively down": "disabled",
        }

        for row in data:
            # Нормализуем статус (link_status из NTC или status)
            status = row.get("link_status", row.get("status", ""))
            if status:
                status_lower = str(status).lower()
                row["status"] = status_map.get(status_lower, status_lower)

            # Унифицируем имена полей из NTC шаблона
            if "mac_address" in row and "mac" not in row:
                row["mac"] = row["mac_address"]

        return data
