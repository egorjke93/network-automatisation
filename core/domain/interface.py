"""
Domain logic для интерфейсов.

Нормализация, обогащение и валидация данных интерфейсов.
Не зависит от SSH/collectors — работает с сырыми данными.
"""

import logging
from typing import List, Dict, Any, Optional

from ..models import Interface

logger = logging.getLogger(__name__)
from ..constants import normalize_interface_short
from ..constants.interfaces import (
    get_interface_aliases,
    is_lag_name,
    MEDIA_TYPE_PORT_TYPE_MAP,
    HARDWARE_TYPE_PORT_TYPE_MAP,
    INTERFACE_NAME_PORT_TYPE_MAP,
    _SHORT_PORT_TYPE_PREFIXES,
    _UNKNOWN_SPEED_VALUES,
    get_nominal_speed_from_port_type,
)
from ..constants.netbox import (
    VIRTUAL_INTERFACE_PREFIXES,
    MGMT_INTERFACE_PATTERNS,
)
from ..domain.vlan import FULL_VLAN_RANGES


# Маппинг статусов из show interfaces в стандартные значения
STATUS_MAP: Dict[str, str] = {
    "connected": "up",
    "up": "up",
    "notconnect": "down",
    "notconnected": "down",
    "down": "down",
    "disabled": "disabled",
    "err-disabled": "error",
    "errdisabled": "error",  # вариант без дефиса
    "administratively down": "disabled",
    "admin down": "disabled",
    "down (administratively down)": "disabled",  # QTech формат
    "down (xcvr not inserted)": "disabled",  # трансивер не установлен
}


class InterfaceNormalizer:
    """
    Нормализация данных интерфейсов.

    Преобразует сырые данные от парсера в типизированные модели.
    Обогащает данные: port_type, mode, status.

    Example:
        normalizer = InterfaceNormalizer()
        raw_data = [{"interface": "Gi0/1", "link_status": "up"}]
        interfaces = normalizer.normalize(raw_data)
        # interfaces[0].status == "up"
    """

    def normalize(
        self,
        data: List[Dict[str, Any]],
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Interface]:
        """
        Нормализует список сырых данных в модели Interface.

        Args:
            data: Сырые данные от парсера
            hostname: Hostname устройства (добавляется к каждой записи)
            device_ip: IP устройства (добавляется к каждой записи)

        Returns:
            List[Interface]: Типизированные модели
        """
        result = []
        for row in data:
            normalized = self._normalize_row(row)
            if hostname:
                normalized["hostname"] = hostname
            if device_ip:
                normalized["device_ip"] = device_ip
            result.append(Interface.from_dict(normalized))
        return result

    def normalize_dicts(
        self,
        data: List[Dict[str, Any]],
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Нормализует данные, оставляя как словари (для совместимости).

        Args:
            data: Сырые данные от парсера
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

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Нормализует одну запись интерфейса.

        Args:
            row: Сырые данные одного интерфейса

        Returns:
            Dict: Нормализованные данные
        """
        result = dict(row)

        # Убираем пробелы в имени интерфейса (QTech: "TFGigabitEthernet 0/39" → "TFGigabitEthernet0/39")
        iface_name = row.get("interface", "")
        if iface_name:
            result["interface"] = iface_name.replace(" ", "")

        # Нормализуем статус
        status = row.get("link_status", row.get("status", ""))
        if status:
            result["status"] = self.normalize_status(status)

        # Унифицируем MAC из разных полей NTC
        if not result.get("mac"):
            for mac_field in ["mac_address", "address", "bia", "hardware_address"]:
                if row.get(mac_field):
                    result["mac"] = row[mac_field]
                    break

        # Унифицируем hardware_type и media_type
        if "hardware_type" not in result and "hardware" in row:
            result["hardware_type"] = row["hardware"]
        if "media_type" not in result and "media" in row:
            result["media_type"] = row["media"]

        # Определяем port_type если не задан
        if not result.get("port_type"):
            iface = result.get("interface", result.get("name", ""))
            result["port_type"] = self.detect_port_type(result, iface.lower())

        # LAG: bandwidth — агрегатная скорость (сумма member-линков)
        # speed для LAG показывает скорость одного member-а, а не всего LAG
        # Пример: Po1 с 4×1G: bandwidth="4000000 Kbit", speed="1000Mb/s"
        # Только для UP: для DOWN LAG bandwidth ненадёжен (как и для обычных портов)
        if (result.get("port_type") == "lag"
                and result.get("bandwidth")
                and result.get("status") == "up"):
            result["speed"] = result["bandwidth"]

        # Номинальная скорость для down-портов (когда speed пустой/unknown/auto)
        speed = result.get("speed", "")
        if speed.lower().strip() in _UNKNOWN_SPEED_VALUES:
            nominal = get_nominal_speed_from_port_type(result.get("port_type", ""))
            if nominal:
                result["speed"] = nominal

        return result

    def normalize_status(self, raw_status: str) -> str:
        """
        Нормализует статус интерфейса.

        Args:
            raw_status: Сырой статус (connected, up, notconnect, etc.)

        Returns:
            str: Нормализованный статус (up, down, disabled, error)
        """
        status_lower = str(raw_status).lower().strip()
        return STATUS_MAP.get(status_lower, status_lower)

    def detect_port_type(self, row: Dict[str, Any], iface_lower: str) -> str:
        """
        Определяет тип порта на основе данных интерфейса.

        Нормализует данные с разных платформ в единый формат:
        - "100g-qsfp28" - 100GE QSFP28
        - "40g-qsfp" - 40GE QSFP+
        - "25g-sfp28" - 25GE SFP28
        - "10g-sfp+" - 10GE SFP+
        - "1g-sfp" - 1GE SFP
        - "1g-rj45" - 1GE RJ45 (copper)
        - "100m-rj45" - 100M RJ45
        - "lag" - Port-channel/LAG
        - "virtual" - Vlan, Loopback, etc.

        Args:
            row: Данные интерфейса
            iface_lower: Имя интерфейса в нижнем регистре

        Returns:
            str: Тип порта или пустая строка
        """
        hardware_type = row.get("hardware_type", "").lower()
        media_type = row.get("media_type", "").lower()

        # LAG интерфейсы (Cisco Port-channel, QTech AggregatePort)
        if is_lag_name(iface_lower):
            return "lag"

        # Виртуальные интерфейсы (VIRTUAL_INTERFACE_PREFIXES из netbox.py)
        if iface_lower.startswith(VIRTUAL_INTERFACE_PREFIXES):
            return "virtual"

        # Management - обычно copper (MGMT_INTERFACE_PATTERNS из netbox.py)
        if iface_lower.startswith(MGMT_INTERFACE_PATTERNS):
            return "1g-rj45"

        # 1. По media_type (наиболее точный)
        # Пропускаем bare speed indicators из NX-OS "media type is 10G" —
        # это НЕ тип трансивера, а generic индикатор скорости порта.
        # Реальный media_type трансивера приходит из show interface transceiver/status
        # и содержит "base", "sfp" и т.д. (например "SFP-10GBase-SR")
        if media_type and media_type not in (
            "unknown", "not present", "",
            "10g", "25g", "40g", "100g", "1g",
            "fiber", "copper", "auto",
        ):
            port_type = self._detect_from_media_type(media_type)
            if port_type:
                return port_type

        # 2. По hardware_type (максимальная скорость порта)
        if hardware_type:
            port_type = self._detect_from_hardware_type(hardware_type)
            if port_type:
                return port_type

        # 3. По имени интерфейса
        return self._detect_from_interface_name(iface_lower)

    def _detect_from_media_type(self, media_type: str) -> str:
        """Определяет port_type из media_type через MEDIA_TYPE_PORT_TYPE_MAP."""
        for pattern, port_type in MEDIA_TYPE_PORT_TYPE_MAP.items():
            if pattern in media_type:
                return port_type
        return ""

    def _detect_from_hardware_type(self, hardware_type: str) -> str:
        """Определяет port_type из hardware_type через HARDWARE_TYPE_PORT_TYPE_MAP."""
        for pattern, port_type in HARDWARE_TYPE_PORT_TYPE_MAP.items():
            if pattern in hardware_type:
                # Для 1G: проверяем SFP в hardware_type
                if port_type == "1g-rj45" and "sfp" in hardware_type:
                    return "1g-sfp"
                return port_type
        return ""

    def _detect_from_interface_name(self, iface_lower: str) -> str:
        """Определяет port_type из имени интерфейса через INTERFACE_NAME_PORT_TYPE_MAP."""
        for prefix, port_type in INTERFACE_NAME_PORT_TYPE_MAP.items():
            if not iface_lower.startswith(prefix):
                continue
            # Короткие префиксы: после них должна быть цифра
            if prefix in _SHORT_PORT_TYPE_PREFIXES:
                if len(iface_lower) <= len(prefix) or not iface_lower[len(prefix)].isdigit():
                    continue
            return port_type
        return ""

    def enrich_with_lag(
        self,
        interfaces: List[Dict[str, Any]],
        lag_membership: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        Обогащает интерфейсы информацией о LAG membership.

        Args:
            interfaces: Список интерфейсов
            lag_membership: {member_interface: lag_name}

        Returns:
            List[Dict]: Обогащённые интерфейсы
        """
        for iface in interfaces:
            iface_name = iface.get("interface", "")
            if iface_name in lag_membership:
                iface["lag"] = lag_membership[iface_name]
        return interfaces

    @staticmethod
    def _resolve_trunk_mode(raw_vlans) -> tuple:
        """
        Определяет NetBox trunk mode из списка/строки VLAN.

        Логика: "all", пустые, "1-4094", "1-4093", "1-4095" → tagged-all.
        Конкретные VLAN → tagged.

        Args:
            raw_vlans: Строка или список VLAN из TextFSM/NTC

        Returns:
            tuple: (netbox_mode, cleaned_vlans)
                netbox_mode: "tagged-all" или "tagged"
                cleaned_vlans: Строка VLAN (пустая для tagged-all)
        """
        # Нормализуем: список → строка через запятую
        if isinstance(raw_vlans, list):
            vlans_str = ",".join(str(v) for v in raw_vlans).lower().strip()
        else:
            vlans_str = str(raw_vlans).lower().strip()

        # "all", пустые или полный диапазон → tagged-all
        if not vlans_str or vlans_str in FULL_VLAN_RANGES:
            return "tagged-all", ""

        return "tagged", vlans_str

    def normalize_switchport_data(
        self,
        parsed: List[Dict[str, Any]],
        platform: str,
    ) -> Dict[str, Dict[str, str]]:
        """
        Нормализует данные switchport из разных форматов TextFSM/NTC в единый.

        Обрабатывает форматы:
        - Cisco IOS/Arista NTC: admin_mode, native_vlan, access_vlan, trunking_vlans
        - NX-OS NTC: mode (operational), trunking_vlans (без admin_mode)
        - QTech custom: switchport=enabled, mode (ACCESS/TRUNK/HYBRID), vlan_lists

        Args:
            parsed: Распарсенные данные из TextFSM/NTC
            platform: Платформа устройства

        Returns:
            Dict: {interface: {mode, native_vlan, access_vlan, tagged_vlans}}
        """
        modes = {}

        for row in parsed:
            iface = row.get("interface", "")
            if not iface:
                continue

            # Определяем формат данных:
            # - Cisco NTC: admin_mode, trunking_vlans
            # - QTech custom: switchport (enabled/disabled), mode (ACCESS/TRUNK/HYBRID), vlan_lists
            switchport = row.get("switchport", "").lower()
            if switchport == "disabled":
                continue

            admin_mode = row.get("admin_mode", "").lower()
            native_vlan = row.get("native_vlan", row.get("trunking_native_vlan", ""))
            access_vlan = row.get("access_vlan", "")

            netbox_mode = ""
            trunking_vlans = ""

            if admin_mode:
                # Cisco IOS/Arista NTC формат (admin_mode — определяющее поле)
                if "access" in admin_mode:
                    netbox_mode = "access"
                elif "trunk" in admin_mode or "dynamic" in admin_mode:
                    raw_vlans = row.get("trunking_vlans", "")
                    netbox_mode, trunking_vlans = self._resolve_trunk_mode(raw_vlans)
            elif row.get("trunking_vlans") is not None and row.get("mode"):
                # NX-OS формат (mode + trunking_vlans, без admin_mode)
                nxos_mode = row.get("mode", "").lower()
                if "trunk" in nxos_mode:
                    raw_vlans = row.get("trunking_vlans", "")
                    netbox_mode, trunking_vlans = self._resolve_trunk_mode(raw_vlans)
                elif "access" in nxos_mode:
                    netbox_mode = "access"
            elif switchport == "enabled":
                # QTech формат (switchport=enabled, mode=ACCESS/TRUNK/HYBRID)
                qtech_mode = row.get("mode", "").upper()
                vlan_lists = row.get("vlan_lists", "")
                if qtech_mode == "ACCESS":
                    netbox_mode = "access"
                elif qtech_mode == "TRUNK":
                    vl = str(vlan_lists).strip().upper()
                    if not vl or vl == "ALL":
                        netbox_mode = "tagged-all"
                    else:
                        netbox_mode = "tagged"
                        trunking_vlans = str(vlan_lists).strip()
                elif qtech_mode == "HYBRID":
                    netbox_mode = "tagged"
                    vl = str(vlan_lists).strip().upper()
                    if vl and vl != "ALL":
                        trunking_vlans = str(vlan_lists).strip()

            mode_data = {
                "mode": netbox_mode,
                "native_vlan": str(native_vlan) if native_vlan else "",
                "access_vlan": str(access_vlan) if access_vlan else "",
                "tagged_vlans": trunking_vlans if netbox_mode == "tagged" else "",
            }
            modes[iface] = mode_data

            # Добавляем альтернативные имена через единый источник из constants
            for alias in get_interface_aliases(iface):
                if alias != iface:
                    modes[alias] = mode_data

        return modes

    def enrich_with_switchport(
        self,
        interfaces: List[Dict[str, Any]],
        switchport_modes: Dict[str, Dict[str, str]],
        lag_membership: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Обогащает интерфейсы информацией о switchport mode.

        Для LAG интерфейсов mode наследуется от member портов.

        Args:
            interfaces: Список интерфейсов
            switchport_modes: {interface: {mode, native_vlan, access_vlan}}
            lag_membership: {member_interface: lag_name} для наследования mode

        Returns:
            List[Dict]: Обогащённые интерфейсы
        """
        # Определяем mode для LAG на основе members
        lag_modes: Dict[str, str] = {}
        if lag_membership:
            for member_iface, lag_name in lag_membership.items():
                if member_iface in switchport_modes:
                    member_mode = switchport_modes[member_iface].get("mode", "")
                    # tagged-all имеет приоритет
                    if member_mode == "tagged-all":
                        lag_modes[lag_name] = "tagged-all"
                    elif member_mode == "tagged" and lag_modes.get(lag_name) != "tagged-all":
                        lag_modes[lag_name] = "tagged"

        for iface in interfaces:
            iface_name = iface.get("interface", "")
            iface_lower = iface_name.lower()

            # Пробуем найти интерфейс в switchport_modes по разным вариантам имени
            sw_data = None
            if iface_name in switchport_modes:
                sw_data = switchport_modes[iface_name]
            else:
                # Пробуем все варианты написания имени из constants
                for variant in get_interface_aliases(iface_name):
                    if variant in switchport_modes:
                        sw_data = switchport_modes[variant]
                        break

            if sw_data:
                iface["mode"] = sw_data.get("mode", "")
                iface["native_vlan"] = sw_data.get("native_vlan", "")
                iface["access_vlan"] = sw_data.get("access_vlan", "")
                iface["tagged_vlans"] = sw_data.get("tagged_vlans", "")
            elif is_lag_name(iface_lower):
                # Для LAG берём mode из members (Cisco Port-channel, QTech AggregatePort)
                for lag_name, lag_mode in lag_modes.items():
                    if self._is_same_lag(iface_lower, lag_name.lower()):
                        iface["mode"] = lag_mode
                        break

        return interfaces

    def _is_same_lag(self, iface_lower: str, lag_lower: str) -> bool:
        """
        Проверяет соответствие имён LAG через normalize_interface_short.

        Port-channel1 == Po1 (оба → po1)
        AggregatePort 1 == Ag1 (оба → ag1)
        """
        return (normalize_interface_short(iface_lower, lowercase=True) ==
                normalize_interface_short(lag_lower, lowercase=True))

    def enrich_with_media_type(
        self,
        interfaces: List[Dict[str, Any]],
        media_types: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        Обогащает интерфейсы точным media_type (из show interface status).

        Args:
            interfaces: Список интерфейсов
            media_types: {interface: media_type}

        Returns:
            List[Dict]: Обогащённые интерфейсы
        """
        enriched_count = 0
        not_found = []
        for iface in interfaces:
            iface_name = iface.get("interface", "")
            if iface_name in media_types and media_types[iface_name]:
                new_mt = media_types[iface_name].lower()
                # Перезаписываем если новый тип более информативен
                if "base" in new_mt or "sfp" in new_mt or "qsfp" in new_mt:
                    iface["media_type"] = media_types[iface_name]
                    # Пересчитываем port_type
                    iface["port_type"] = self.detect_port_type(
                        iface, iface_name.lower()
                    )
                    enriched_count += 1
            elif iface_name and not iface_name.lower().startswith(("vlan", "lo", "mgmt", "null")):
                not_found.append(iface_name)

        logger.debug(f"enrich_with_media_type: обогащено {enriched_count} из {len(interfaces)}")
        if not_found:
            logger.debug(f"enrich_with_media_type: не найдены в media_types (первые 5): {not_found[:5]}")
        return interfaces
