"""
Domain logic для интерфейсов.

Нормализация, обогащение и валидация данных интерфейсов.
Не зависит от SSH/collectors — работает с сырыми данными.
"""

from typing import List, Dict, Any, Optional

from ..models import Interface
from ..constants import normalize_interface_short


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
        if iface_lower.startswith(("port-channel", "po", "aggregateport")):
            return "lag"
        # QTech: Ag1, Ag10 (короткое имя AggregatePort)
        if (len(iface_lower) >= 3 and iface_lower[:2] == "ag"
                and iface_lower[2].isdigit()):
            return "lag"

        # Виртуальные интерфейсы
        if iface_lower.startswith(("vlan", "loopback", "null", "tunnel", "nve")):
            return "virtual"

        # Management - обычно copper
        if iface_lower.startswith(("mgmt", "management")):
            return "1g-rj45"

        # 1. По media_type (наиболее точный)
        if media_type and media_type not in ("unknown", "not present", ""):
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
        """Определяет port_type из media_type."""
        if "100gbase" in media_type or "100g" in media_type:
            return "100g-qsfp28"
        if "40gbase" in media_type or "40g" in media_type:
            return "40g-qsfp"
        if "25gbase" in media_type or "25g" in media_type:
            return "25g-sfp28"
        if "10gbase" in media_type or "10g" in media_type:
            return "10g-sfp+"
        if "1000base-t" in media_type or "rj45" in media_type:
            return "1g-rj45"
        if "1000base" in media_type or "sfp" in media_type:
            return "1g-sfp"
        return ""

    def _detect_from_hardware_type(self, hardware_type: str) -> str:
        """Определяет port_type из hardware_type."""
        # NX-OS: "100/1000/10000 Ethernet" = SFP+
        if "100000" in hardware_type or "100g" in hardware_type or "hundred" in hardware_type:
            return "100g-qsfp28"
        if "40000" in hardware_type or "40g" in hardware_type or "forty" in hardware_type:
            return "40g-qsfp"
        if "25000" in hardware_type or "25g" in hardware_type or "twenty five" in hardware_type:
            return "25g-sfp28"
        if "10000" in hardware_type or "10g" in hardware_type or "ten gig" in hardware_type:
            return "10g-sfp+"
        # QTech: "Broadcom TFGigabitEthernet" = 10G SFP+
        if "tfgigabitethernet" in hardware_type:
            return "10g-sfp+"
        # Только 1G без 10G (Gigabit Ethernet, 1000 Ethernet)
        if ("1000" in hardware_type or "gigabit" in hardware_type) and "10000" not in hardware_type:
            if "sfp" in hardware_type:
                return "1g-sfp"
            return "1g-rj45"
        return ""

    def _detect_from_interface_name(self, iface_lower: str) -> str:
        """Определяет port_type из имени интерфейса."""
        if iface_lower.startswith(("hundredgig", "hu")):
            return "100g-qsfp28"
        if iface_lower.startswith(("fortygig", "fo")):
            return "40g-qsfp"
        if iface_lower.startswith(("twentyfivegig", "twe")):
            return "25g-sfp28"
        # QTech TFGigabitEthernet (10G)
        if iface_lower.startswith("tfgigabitethernet"):
            return "10g-sfp+"
        # TF0/1 - короткий формат QTech 10G
        if len(iface_lower) >= 3 and iface_lower[:2] == "tf" and iface_lower[2].isdigit():
            return "10g-sfp+"
        if iface_lower.startswith("tengig"):
            return "10g-sfp+"
        # Te1/1 - короткий формат
        if len(iface_lower) >= 3 and iface_lower[:2] == "te" and iface_lower[2].isdigit():
            return "10g-sfp+"
        if iface_lower.startswith(("gigabit", "gi")):
            return "1g-rj45"
        if iface_lower.startswith(("fastethernet", "fa")):
            return "100m-rj45"
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
                # Пробуем нормализованные варианты имени
                normalized_names = self._get_interface_name_variants(iface_name)
                for variant in normalized_names:
                    if variant in switchport_modes:
                        sw_data = switchport_modes[variant]
                        break

            if sw_data:
                iface["mode"] = sw_data.get("mode", "")
                iface["native_vlan"] = sw_data.get("native_vlan", "")
                iface["access_vlan"] = sw_data.get("access_vlan", "")
                iface["tagged_vlans"] = sw_data.get("tagged_vlans", "")
            elif iface_lower.startswith(("po", "port-channel", "aggregateport")) or (
                len(iface_lower) >= 3 and iface_lower[:2] == "ag" and iface_lower[2].isdigit()
            ):
                # Для LAG берём mode из members (Cisco Port-channel, QTech AggregatePort)
                for lag_name, lag_mode in lag_modes.items():
                    if self._is_same_lag(iface_lower, lag_name.lower()):
                        iface["mode"] = lag_mode
                        break

        return interfaces

    def _is_same_lag(self, iface_lower: str, lag_lower: str) -> bool:
        """Проверяет соответствие имён LAG (Cisco Port-channel, QTech AggregatePort)."""
        if iface_lower == lag_lower:
            return True
        # Cisco: Po1 == Port-channel1
        if f"po{lag_lower}" == iface_lower:
            return True
        if lag_lower.replace("po", "port-channel") == iface_lower:
            return True
        # QTech: AggregatePort 1 == Ag1 (с учётом пробела)
        iface_nospace = iface_lower.replace(" ", "")
        lag_nospace = lag_lower.replace(" ", "")
        if iface_nospace == lag_nospace:
            return True
        if iface_nospace.startswith("aggregateport") and lag_nospace.startswith("ag"):
            # aggregateport1 == ag1
            iface_num = iface_nospace.replace("aggregateport", "")
            lag_num = lag_nospace.replace("ag", "")
            if iface_num == lag_num:
                return True
        if lag_nospace.startswith("aggregateport") and iface_nospace.startswith("ag"):
            lag_num = lag_nospace.replace("aggregateport", "")
            iface_num = iface_nospace.replace("ag", "")
            if iface_num == lag_num:
                return True
        return False

    def _get_interface_name_variants(self, name: str) -> List[str]:
        """
        Возвращает варианты имени интерфейса для сопоставления.

        Например GigabitEthernet0/1 -> ['Gi0/1', 'GigabitEthernet0/1']

        Args:
            name: Имя интерфейса

        Returns:
            List[str]: Варианты имени
        """
        variants = [name]

        # Полные имена -> сокращённые
        abbrev_map = {
            "GigabitEthernet": "Gi",
            "TenGigabitEthernet": "Te",
            "TFGigabitEthernet": "TF",  # QTech 10G
            "TwentyFiveGigE": "Twe",
            "TwentyFiveGigabitEthernet": "Twe",
            "FortyGigabitEthernet": "Fo",
            "HundredGigE": "Hu",
            "HundredGigabitEthernet": "Hu",
            "FastEthernet": "Fa",
            "AggregatePort": "Ag",  # QTech LAG
            "Ethernet": "Eth",
            "Port-channel": "Po",
            "Port-Channel": "Po",
        }

        # Сокращённые -> полные
        full_map = {v: k for k, v in abbrev_map.items()}

        for full, short in abbrev_map.items():
            if name.startswith(full):
                suffix = name[len(full):]
                variants.append(f"{short}{suffix}")
                break

        for short, full in full_map.items():
            if name.startswith(short) and not name.startswith(full):
                suffix = name[len(short):]
                variants.append(f"{full}{suffix}")
                break

        return variants

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
        return interfaces
