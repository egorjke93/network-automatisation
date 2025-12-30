"""
Domain logic для LLDP/CDP соседей.

Нормализация, объединение протоколов и идентификация соседей.
Не зависит от SSH/collectors — работает с сырыми данными.
"""

import re
from typing import List, Dict, Any

from ..models import LLDPNeighbor
from ..constants import normalize_interface_short


# Маппинг полей из NTC Templates к стандартным именам
# ВАЖНО: port_id обрабатывается отдельно (может быть MAC)
KEY_MAPPING: Dict[str, str] = {
    # Локальный интерфейс
    "local_intf": "local_interface",
    # Имя соседа
    "neighbor": "remote_hostname",
    "neighbor_name": "remote_hostname",
    "system_name": "remote_hostname",
    "device_id": "remote_hostname",
    # Порт соседа - port_id НЕ маппится (обрабатывается отдельно)
    "neighbor_interface": "remote_port",
    "neighbor_port_id": "remote_port",
    "port_description": "port_description",
    # IP соседа
    "mgmt_ip": "remote_ip",
    "mgmt_address": "remote_ip",
    "management_ip": "remote_ip",
    # Платформа
    "hardware": "remote_platform",
    "platform": "remote_platform",
    # MAC
    "chassis_id": "remote_mac",
}


class LLDPNormalizer:
    """
    Нормализация LLDP/CDP соседей.

    Преобразует сырые данные от парсера в типизированные модели.
    Объединяет данные LLDP и CDP для полной информации.

    Example:
        normalizer = LLDPNormalizer()
        raw_data = [{"local_intf": "Gi0/1", "neighbor": "switch2"}]
        neighbors = normalizer.normalize(raw_data)
    """

    def normalize(
        self,
        data: List[Dict[str, Any]],
        protocol: str = "lldp",
        hostname: str = "",
        device_ip: str = "",
    ) -> List[LLDPNeighbor]:
        """
        Нормализует список сырых данных в модели LLDPNeighbor.

        Args:
            data: Сырые данные от парсера
            protocol: Протокол (lldp, cdp, both)
            hostname: Hostname локального устройства
            device_ip: IP локального устройства

        Returns:
            List[LLDPNeighbor]: Типизированные модели
        """
        normalized = self.normalize_dicts(data, protocol, hostname, device_ip)
        return [LLDPNeighbor.from_dict(row) for row in normalized]

    def normalize_dicts(
        self,
        data: List[Dict[str, Any]],
        protocol: str = "lldp",
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Нормализует данные, оставляя как словари.

        Args:
            data: Сырые данные от парсера
            protocol: Протокол (lldp, cdp, both)
            hostname: Hostname локального устройства
            device_ip: IP локального устройства

        Returns:
            List[Dict]: Нормализованные словари
        """
        result = []
        for row in data:
            normalized = self._normalize_row(row)
            normalized["protocol"] = protocol.upper()
            if hostname:
                normalized["hostname"] = hostname
            if device_ip:
                normalized["device_ip"] = device_ip
            result.append(normalized)
        return result

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Нормализует одну запись соседа.

        Args:
            row: Сырые данные

        Returns:
            Dict: Нормализованные данные
        """
        result = {}
        port_id_value = None

        # Применяем маппинг ключей
        for key, value in row.items():
            key_lower = key.lower()
            # port_id обрабатываем отдельно (может быть MAC)
            if key_lower == "port_id":
                port_id_value = value
                continue
            new_key = KEY_MAPPING.get(key_lower, key_lower)
            result[new_key] = value

        # Определяем remote_port с приоритетом:
        # 1. remote_port (уже смаплен из neighbor_interface)
        # 2. port_id (если похож на интерфейс: Te/Gi/Fa/Et/Po)
        # 3. port_description (если похож на интерфейс)
        # 4. port_id (если не MAC) или port_description
        if not result.get("remote_port"):
            port_desc = result.get("port_description", "")

            if port_id_value:
                port_id_str = str(port_id_value).strip()

                # Если port_id похож на интерфейс — используем его
                if self._is_interface_name(port_id_str):
                    result["remote_port"] = port_id_str
                # Если port_id — это MAC, сохраняем в remote_mac
                elif self.is_mac_address(port_id_str):
                    if not result.get("remote_mac"):
                        result["remote_mac"] = port_id_str
                    # port_description как fallback для remote_port
                    if port_desc:
                        result["remote_port"] = port_desc
                # port_id не интерфейс и не MAC
                else:
                    # Если port_description — интерфейс, используем его
                    if port_desc and self._is_interface_name(port_desc):
                        result["remote_port"] = port_desc
                    # Иначе используем port_id как есть
                    else:
                        result["remote_port"] = port_id_str
            # Нет port_id — используем port_description
            elif port_desc:
                result["remote_port"] = port_desc

        # Определяем тип идентификации соседа
        result["neighbor_type"] = self.determine_neighbor_type(result)

        # Если hostname пустой — используем MAC или IP как идентификатор
        if not result.get("remote_hostname"):
            if result.get("remote_mac"):
                result["remote_hostname"] = f"[MAC:{result['remote_mac']}]"
            elif result.get("remote_ip"):
                result["remote_hostname"] = f"[IP:{result['remote_ip']}]"
            else:
                result["remote_hostname"] = "[unknown]"

        return result

    def determine_neighbor_type(self, neighbor: Dict[str, Any]) -> str:
        """
        Определяет тип идентификации соседа.

        Args:
            neighbor: Данные соседа

        Returns:
            str: Тип (hostname, mac, ip, unknown)
        """
        hostname = neighbor.get("remote_hostname", "")

        # Проверяем что hostname — реальное имя (не MAC и не placeholder)
        if hostname and not hostname.startswith("["):
            if self.is_mac_address(hostname):
                # Hostname содержит MAC-адрес
                return "mac"
            return "hostname"

        if neighbor.get("remote_mac"):
            return "mac"

        if neighbor.get("remote_ip"):
            return "ip"

        return "unknown"

    def is_mac_address(self, value: str) -> bool:
        """
        Проверяет является ли строка MAC-адресом.

        Args:
            value: Строка для проверки

        Returns:
            bool: True если это MAC
        """
        mac_patterns = [
            r"^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$",  # 00:11:22:33:44:55
            r"^([0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}$",    # 0011.2233.4455
            r"^[0-9a-fA-F]{12}$",                         # 001122334455
        ]
        return any(re.match(p, value) for p in mac_patterns)

    def _is_interface_name(self, value: str) -> bool:
        """
        Проверяет является ли строка именем интерфейса.

        Cisco/Arista/Juniper форматы:
        - GigabitEthernet0/1, Gi0/1
        - TenGigabitEthernet1/1/4, Te1/1/4
        - FastEthernet0/1, Fa0/1
        - Ethernet1/1, Et1/1
        - Port-channel1, Po1
        - mgmt0, Vlan100, Loopback0

        Args:
            value: Строка для проверки

        Returns:
            bool: True если похоже на интерфейс
        """
        if not value:
            return False

        value_lower = value.lower()

        # Префиксы интерфейсов
        interface_prefixes = (
            "gi", "te", "fa", "et", "po", "xe", "ge",  # Короткие
            "gigabit", "tengig", "fasteth", "ethernet", "port-channel",  # Полные
            "mgmt", "vlan", "loopback", "lo", "null",  # Специальные
            "hundredgig", "fortygig", "twentyfivegig",  # Высокоскоростные
        )

        # Проверяем начинается ли с префикса интерфейса
        for prefix in interface_prefixes:
            if value_lower.startswith(prefix):
                return True

        # Паттерн: буквы + цифры/слэши (например: eth1/1, swp1)
        # Минимум 2 буквы чтобы отличить от просто числа
        if re.match(r"^[a-zA-Z]{2,}\d+[/\d]*$", value):
            return True

        return False

    def merge_lldp_cdp(
        self,
        lldp_data: List[Dict[str, Any]],
        cdp_data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Объединяет данные LLDP и CDP.

        CDP имеет ПРИОРИТЕТ (проприетарный Cisco, надёжнее):
        - local_interface, remote_port, remote_hostname, remote_platform, remote_ip

        LLDP ДОПОЛНЯЕТ:
        - remote_mac (chassis_id) — главное что даёт LLDP

        Args:
            lldp_data: Нормализованные данные LLDP
            cdp_data: Нормализованные данные CDP

        Returns:
            List[Dict]: Объединённые данные
        """
        if not lldp_data:
            return cdp_data
        if not cdp_data:
            return lldp_data

        # Индекс LLDP по local_interface для поиска MAC
        lldp_by_interface = {}
        for lldp_row in lldp_data:
            local_intf = normalize_interface_short(
                lldp_row.get("local_interface", ""), lowercase=True
            )
            if local_intf:
                lldp_by_interface[local_intf] = lldp_row

        merged = []
        used_lldp_interfaces = set()

        # CDP как база
        for cdp_row in cdp_data:
            local_intf = normalize_interface_short(
                cdp_row.get("local_interface", ""), lowercase=True
            )
            lldp_row = lldp_by_interface.get(local_intf)

            if lldp_row:
                # CDP база, LLDP дополняет
                result = self._merge_cdp_with_lldp(cdp_row, lldp_row)
                used_lldp_interfaces.add(local_intf)
            else:
                result = dict(cdp_row)

            result["protocol"] = "BOTH"
            merged.append(result)

        # Добавляем LLDP соседей без CDP (например, не-Cisco устройства)
        for lldp_row in lldp_data:
            local_intf = normalize_interface_short(
                lldp_row.get("local_interface", ""), lowercase=True
            )
            if local_intf not in used_lldp_interfaces:
                lldp_row = dict(lldp_row)
                lldp_row["protocol"] = "BOTH"
                merged.append(lldp_row)

        return merged

    def _merge_cdp_with_lldp(
        self,
        cdp_row: Dict[str, Any],
        lldp_row: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Объединяет данные: CDP база, LLDP дополняет.

        CDP поля имеют ПРИОРИТЕТ:
        - local_interface
        - remote_port
        - remote_hostname
        - remote_platform
        - remote_ip

        LLDP ДОПОЛНЯЕТ:
        - remote_mac (главное что даёт LLDP)
        - capabilities (если нет в CDP)

        Args:
            cdp_row: Данные из CDP (приоритет)
            lldp_row: Данные из LLDP (дополнение)

        Returns:
            Dict: Объединённые данные
        """
        # CDP как база
        result = dict(cdp_row)

        # LLDP дополняет MAC (главная ценность LLDP)
        if not result.get("remote_mac") and lldp_row.get("remote_mac"):
            result["remote_mac"] = lldp_row["remote_mac"]

        # LLDP дополняет capabilities
        if not result.get("capabilities") and lldp_row.get("capabilities"):
            result["capabilities"] = lldp_row["capabilities"]

        # Если CDP не дал hostname, берём из LLDP
        if not result.get("remote_hostname"):
            lldp_hostname = lldp_row.get("remote_hostname", "")
            if lldp_hostname:
                result["remote_hostname"] = lldp_hostname
                # Если это MAC-fallback, сохраняем neighbor_type
                if lldp_hostname.startswith("["):
                    result["neighbor_type"] = lldp_row.get("neighbor_type", "mac")
                else:
                    result["neighbor_type"] = "hostname"

        return result

    def filter_by_local_interface(
        self,
        data: List[Dict[str, Any]],
        interfaces: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Фильтрует соседей по локальным интерфейсам.

        Args:
            data: Список соседей
            interfaces: Список интерфейсов для включения

        Returns:
            List[Dict]: Отфильтрованные соседи
        """
        interfaces_lower = {i.lower() for i in interfaces}
        return [
            row for row in data
            if row.get("local_interface", "").lower() in interfaces_lower
        ]
