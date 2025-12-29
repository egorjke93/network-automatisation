"""
Domain logic для MAC-адресов.

Нормализация, фильтрация и дедупликация MAC-таблицы.
Не зависит от SSH/collectors — работает с сырыми данными.
"""

import re
from typing import List, Dict, Any, Set, Tuple, Optional

from ..models import MACEntry
from ..constants import (
    ONLINE_PORT_STATUSES,
    normalize_interface_short,
    normalize_mac,
    normalize_mac_raw,
)


class MACNormalizer:
    """
    Нормализация MAC-таблицы.

    Преобразует сырые данные от парсера в типизированные модели.
    Фильтрует по интерфейсам и VLAN, дедуплицирует.

    Example:
        normalizer = MACNormalizer(
            mac_format="ieee",
            exclude_interfaces=["Po.*", "Vlan.*"],
            exclude_vlans=[1, 1000],
        )
        raw_data = [{"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"}]
        entries = normalizer.normalize(raw_data, interface_status={"Gi0/1": "connected"})
    """

    def __init__(
        self,
        mac_format: str = "ieee",
        normalize_interfaces: bool = True,
        exclude_interfaces: Optional[List[str]] = None,
        exclude_vlans: Optional[List[int]] = None,
    ):
        """
        Инициализация нормализатора.

        Args:
            mac_format: Формат MAC (cisco, ieee, unix)
            normalize_interfaces: Сокращать имена интерфейсов
            exclude_interfaces: Regex паттерны для исключения
            exclude_vlans: VLAN для исключения
        """
        self.mac_format = mac_format
        self.normalize_interfaces = normalize_interfaces
        self.exclude_interfaces = exclude_interfaces or []
        self.exclude_vlans = exclude_vlans or []

        # Компилируем паттерны
        self._exclude_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.exclude_interfaces
        ]

    def normalize(
        self,
        data: List[Dict[str, Any]],
        interface_status: Optional[Dict[str, str]] = None,
        hostname: str = "",
        device_ip: str = "",
    ) -> List[MACEntry]:
        """
        Нормализует список сырых данных в модели MACEntry.

        Args:
            data: Сырые данные от парсера
            interface_status: {interface: status} для online/offline
            hostname: Hostname устройства
            device_ip: IP устройства

        Returns:
            List[MACEntry]: Типизированные модели
        """
        normalized = self.normalize_dicts(data, interface_status, hostname, device_ip)
        return [MACEntry.from_dict(row) for row in normalized]

    def normalize_dicts(
        self,
        data: List[Dict[str, Any]],
        interface_status: Optional[Dict[str, str]] = None,
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Нормализует данные, оставляя как словари.

        Args:
            data: Сырые данные от парсера
            interface_status: {interface: status} для online/offline
            hostname: Hostname устройства
            device_ip: IP устройства

        Returns:
            List[Dict]: Нормализованные словари
        """
        interface_status = interface_status or {}
        result = []
        seen_macs: Set[Tuple[str, str, str]] = set()

        for row in data:
            normalized = self._normalize_row(row, interface_status)
            if normalized is None:
                continue  # Отфильтрован

            # Дедупликация
            mac_raw = normalize_mac_raw(normalized.get("mac", ""))
            vlan = normalized.get("vlan", "")
            interface = normalized.get("interface", "")
            key = (mac_raw, vlan, interface)

            if key in seen_macs:
                continue
            seen_macs.add(key)

            if hostname:
                normalized["hostname"] = hostname
            if device_ip:
                normalized["device_ip"] = device_ip

            result.append(normalized)

        return result

    def _normalize_row(
        self,
        row: Dict[str, Any],
        interface_status: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """
        Нормализует одну запись MAC.

        Args:
            row: Сырые данные
            interface_status: Статусы интерфейсов

        Returns:
            Dict или None если отфильтрован
        """
        result = dict(row)

        # Нормализуем интерфейс
        interface = row.get("interface", row.get("destination_port", ""))
        # NTC Templates может вернуть список (например ['CPU'])
        if isinstance(interface, list):
            interface = interface[0] if interface else ""
        if self.normalize_interfaces:
            interface = normalize_interface_short(interface)
        result["interface"] = interface

        # Проверяем исключения по интерфейсу
        if self._should_exclude_interface(interface):
            return None

        # Проверяем исключения по VLAN
        vlan = str(row.get("vlan", row.get("vlan_id", "")))
        if vlan:
            try:
                if int(vlan) in self.exclude_vlans:
                    return None
            except ValueError:
                pass
        result["vlan"] = vlan

        # Нормализуем MAC
        mac = row.get("mac", row.get("destination_address", ""))
        if mac:
            normalized_mac = normalize_mac(mac, format=self.mac_format)
            result["mac"] = normalized_mac if normalized_mac else mac

        # Тип MAC: dynamic или static
        raw_type = str(row.get("type", "")).lower()
        if "dynamic" in raw_type:
            result["type"] = "dynamic"
        else:
            result["type"] = "static"

        # Определяем status по состоянию порта
        port_status = interface_status.get(interface, "")
        if port_status.lower() in ONLINE_PORT_STATUSES:
            result["status"] = "online"
        elif port_status:
            result["status"] = "offline"
        else:
            result["status"] = "unknown"

        return result

    def _should_exclude_interface(self, interface: str) -> bool:
        """
        Проверяет, нужно ли исключить интерфейс.

        Args:
            interface: Имя интерфейса

        Returns:
            bool: True если нужно исключить
        """
        for pattern in self._exclude_patterns:
            if pattern.match(interface):
                return True
        return False

    def deduplicate(
        self,
        data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Финальная дедупликация по полному ключу.

        Удаляет дубликаты (hostname, mac, vlan, interface).

        Args:
            data: Список записей

        Returns:
            List[Dict]: Дедуплицированные записи
        """
        seen: Set[Tuple[str, str, str, str]] = set()
        result = []

        for row in data:
            hostname = row.get("hostname", "")
            mac = normalize_mac_raw(row.get("mac", ""))
            vlan = str(row.get("vlan", ""))
            interface = row.get("interface", "")

            key = (hostname, mac, vlan, interface)
            if key in seen:
                continue

            seen.add(key)
            result.append(row)

        return result

    def filter_trunk_ports(
        self,
        data: List[Dict[str, Any]],
        trunk_interfaces: Set[str],
    ) -> List[Dict[str, Any]]:
        """
        Фильтрует MAC с trunk портов.

        Args:
            data: Список записей
            trunk_interfaces: Множество trunk интерфейсов

        Returns:
            List[Dict]: Записи без trunk портов
        """
        return [
            row for row in data
            if row.get("interface", "") not in trunk_interfaces
        ]

    def merge_sticky_macs(
        self,
        mac_table: List[Dict[str, Any]],
        sticky_macs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Объединяет MAC-таблицу со sticky MAC из port-security.

        Sticky MAC которых нет в основной таблице добавляются как offline.

        Args:
            mac_table: Основная MAC-таблица
            sticky_macs: Sticky MAC из port-security

        Returns:
            List[Dict]: Объединённые данные
        """
        existing_macs = {
            normalize_mac_raw(row.get("mac", ""))
            for row in mac_table
        }

        result = list(mac_table)
        for sticky in sticky_macs:
            mac_raw = normalize_mac_raw(sticky.get("mac", ""))
            if mac_raw not in existing_macs:
                sticky["status"] = "offline"
                result.append(sticky)

        return result
