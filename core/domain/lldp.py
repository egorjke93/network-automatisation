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
        # 2. port_description (имя интерфейса)
        # 3. port_id (если не похож на MAC)
        if not result.get("remote_port"):
            if result.get("port_description"):
                result["remote_port"] = result["port_description"]
            elif port_id_value:
                # Если port_id похож на MAC - сохраняем в remote_mac
                if self.is_mac_address(str(port_id_value)):
                    if not result.get("remote_mac"):
                        result["remote_mac"] = port_id_value
                else:
                    result["remote_port"] = port_id_value

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

    def merge_lldp_cdp(
        self,
        lldp_data: List[Dict[str, Any]],
        cdp_data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Объединяет данные LLDP и CDP.

        LLDP берётся как база (есть MAC chassis_id), дополняется из CDP:
        - remote_hostname (если LLDP не дал system_name)
        - remote_platform
        - remote_ip
        - remote_port

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

        # Индекс CDP по local_interface
        cdp_by_interface = {}
        for cdp_row in cdp_data:
            local_intf = normalize_interface_short(
                cdp_row.get("local_interface", ""), lowercase=True
            )
            if local_intf:
                cdp_by_interface[local_intf] = cdp_row

        merged = []
        for lldp_row in lldp_data:
            local_intf = normalize_interface_short(
                lldp_row.get("local_interface", ""), lowercase=True
            )
            cdp_row = cdp_by_interface.get(local_intf)

            if cdp_row:
                lldp_row = self._merge_neighbor(lldp_row, cdp_row)
                del cdp_by_interface[local_intf]

            lldp_row["protocol"] = "BOTH"
            merged.append(lldp_row)

        # Добавляем CDP соседей без LLDP
        for cdp_row in cdp_by_interface.values():
            cdp_row["protocol"] = "BOTH"
            merged.append(cdp_row)

        return merged

    def _merge_neighbor(
        self,
        lldp_row: Dict[str, Any],
        cdp_row: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Объединяет данные одного соседа из LLDP и CDP.

        Args:
            lldp_row: Данные из LLDP
            cdp_row: Данные из CDP

        Returns:
            Dict: Объединённые данные
        """
        result = dict(lldp_row)

        # Hostname из CDP если LLDP не дал
        lldp_hostname = result.get("remote_hostname", "")
        if not lldp_hostname or lldp_hostname.startswith("["):
            cdp_hostname = cdp_row.get("remote_hostname", "")
            if cdp_hostname and not cdp_hostname.startswith("["):
                result["remote_hostname"] = cdp_hostname
                result["neighbor_type"] = "hostname"

        # Дополняем пустые поля
        if not result.get("remote_platform") and cdp_row.get("remote_platform"):
            result["remote_platform"] = cdp_row["remote_platform"]

        if not result.get("remote_ip") and cdp_row.get("remote_ip"):
            result["remote_ip"] = cdp_row["remote_ip"]

        # remote_port: проверяем что это интерфейс
        lldp_port = result.get("remote_port", "")
        cdp_port = cdp_row.get("remote_port", "")

        if self._should_use_cdp_port(lldp_port, cdp_port):
            result["remote_port"] = cdp_port

        return result

    def _should_use_cdp_port(self, lldp_port: str, cdp_port: str) -> bool:
        """
        Определяет нужно ли использовать port из CDP.

        LLDP port иногда содержит hostname вместо интерфейса.

        Args:
            lldp_port: Port из LLDP
            cdp_port: Port из CDP

        Returns:
            bool: True если использовать CDP
        """
        if not cdp_port:
            return False

        if not lldp_port:
            return True

        # Если LLDP port похож на hostname (нет / и много букв)
        if "/" not in lldp_port and len(lldp_port) > 15:
            prefix = lldp_port[:2].lower()
            if prefix not in ("gi", "fa", "te", "et", "po"):
                return True

        return False

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
