"""
Domain logic для инвентаризации.

Нормализация данных inventory (модули, SFP, PSU).
Определение manufacturer по PID.

Примечание: manufacturer определяется ТОЛЬКО по PID, не по платформе устройства,
т.к. трансиверы и модули могут быть от разных производителей.
"""

from typing import List, Dict, Any, Optional

from ..models import InventoryItem


# Паттерны PID для определения manufacturer
PID_MANUFACTURER_PATTERNS: Dict[str, List[str]] = {
    "Cisco": ["WS-", "C9", "N9K", "N7K", "N5K", "ISR", "ASR", "SFP-", "GLC-", "XENPAK"],
    "Arista": ["DCS-", "ARISTA"],
    "Juniper": ["EX", "QFX", "MX"],
    "Finisar": ["FINISAR", "FTLX"],
    "Intel": ["INTEL"],
}


class InventoryNormalizer:
    """
    Нормализация данных инвентаризации.

    Преобразует сырые данные от парсера в типизированные модели.
    Определяет manufacturer по платформе и PID.

    Example:
        normalizer = InventoryNormalizer()
        raw_data = [{"name": "Chassis", "pid": "C9200L-24P-4X", "sn": "ABC123"}]
        items = normalizer.normalize(raw_data, platform="cisco_iosxe")
    """

    def normalize(
        self,
        data: List[Dict[str, Any]],
        platform: str = "",
        hostname: str = "",
        device_ip: str = "",
    ) -> List[InventoryItem]:
        """
        Нормализует список сырых данных в модели InventoryItem.

        Args:
            data: Сырые данные от парсера
            platform: Платформа устройства (для manufacturer)
            hostname: Hostname устройства
            device_ip: IP устройства

        Returns:
            List[InventoryItem]: Типизированные модели
        """
        normalized = self.normalize_dicts(data, platform, hostname, device_ip)
        return [InventoryItem.from_dict(row) for row in normalized]

    def normalize_dicts(
        self,
        data: List[Dict[str, Any]],
        platform: str = "",
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Нормализует данные, оставляя как словари.

        Args:
            data: Сырые данные от парсера
            platform: Платформа устройства (не используется для manufacturer)
            hostname: Hostname устройства
            device_ip: IP устройства

        Returns:
            List[Dict]: Нормализованные словари
        """
        result = []
        for row in data:
            normalized = self._normalize_row(row)
            if hostname:
                normalized["hostname"] = hostname
            if device_ip:
                normalized["device_ip"] = device_ip
            result.append(normalized)
        return result

    def _normalize_row(
        self,
        row: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Нормализует одну запись inventory.

        Manufacturer определяется ТОЛЬКО по PID (Product ID).
        Если PID не распознан — manufacturer остаётся пустым.

        Args:
            row: Сырые данные

        Returns:
            Dict: Нормализованные данные
        """
        pid = row.get("pid", "")

        # Унифицируем поля из NTC
        result = {
            "name": row.get("name", ""),
            "description": row.get("descr", row.get("description", "")),
            "pid": pid,
            "vid": row.get("vid", ""),
            "serial": row.get("sn", row.get("serial", "")),
            "manufacturer": self.detect_manufacturer_by_pid(pid),
        }

        return result

    def detect_manufacturer_by_pid(self, pid: str) -> str:
        """
        Определяет manufacturer по PID (Product ID).

        Args:
            pid: Product ID (например WS-C3750X-48P-S)

        Returns:
            str: Manufacturer или пустая строка
        """
        if not pid:
            return ""

        pid_upper = pid.upper()

        for manufacturer, patterns in PID_MANUFACTURER_PATTERNS.items():
            for pattern in patterns:
                if pattern in pid_upper or pid_upper.startswith(pattern):
                    return manufacturer

        return ""

    def normalize_transceivers(
        self,
        data: List[Dict[str, Any]],
        platform: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Конвертирует данные show interface transceiver в формат inventory.

        Manufacturer определяется по имени трансивера или PID.
        Если не распознан — остаётся пустым.

        Args:
            data: Данные от NTC парсера (show interface transceiver)
            platform: Платформа устройства (не используется для manufacturer)

        Returns:
            List[Dict]: Трансиверы в формате inventory
        """
        items = []

        for row in data:
            # Пропускаем интерфейсы без трансиверов
            transceiver_type = row.get("type", "")
            if not transceiver_type or "not present" in str(transceiver_type).lower():
                continue

            interface = row.get("interface", "")
            part_number = row.get("part_number", "")
            serial_number = row.get("serial", row.get("serial_number", ""))
            name = row.get("name", "")  # OEM, CISCO-FINISAR, etc.

            # Определяем manufacturer по name или PID
            item_manufacturer = self._detect_transceiver_manufacturer(name, part_number)

            items.append({
                "name": f"Transceiver {interface}",
                "description": transceiver_type,
                "pid": part_number,
                "serial": serial_number,
                "manufacturer": item_manufacturer,
            })

        return items

    def _detect_transceiver_manufacturer(
        self,
        name: str,
        part_number: str,
    ) -> str:
        """
        Определяет manufacturer трансивера.

        Определяется по имени (CISCO-FINISAR) или по PID.
        OEM трансиверы и неизвестные — пустой manufacturer.

        Args:
            name: Имя из show interface transceiver (OEM, CISCO-FINISAR)
            part_number: Part number

        Returns:
            str: Manufacturer или пустая строка
        """
        if name:
            name_upper = name.upper()
            if "CISCO" in name_upper:
                return "Cisco"
            if "FINISAR" in name_upper:
                return "Finisar"
            # OEM трансиверы — производитель неизвестен
            if "OEM" in name_upper:
                return ""

        return self.detect_manufacturer_by_pid(part_number)

    def merge_with_transceivers(
        self,
        inventory: List[Dict[str, Any]],
        transceivers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Объединяет inventory с трансиверами.

        Args:
            inventory: Основной inventory (show inventory)
            transceivers: Трансиверы (show interface transceiver)

        Returns:
            List[Dict]: Объединённый список
        """
        return inventory + transceivers

    def filter_with_serial(
        self,
        data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Фильтрует записи без серийного номера.

        Args:
            data: Список inventory

        Returns:
            List[Dict]: Записи с серийниками
        """
        return [row for row in data if row.get("serial")]
