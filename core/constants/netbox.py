"""
Маппинг типов интерфейсов для NetBox.

Определение типа интерфейса по media_type, hardware_type, имени.
"""

import re
from typing import Any, Dict

# =============================================================================
# МАППИНГ ТИПОВ ИНТЕРФЕЙСОВ ДЛЯ NETBOX
# =============================================================================
# Форматы типов NetBox:
#   - Медь (RJ45): 1000base-t, 10gbase-t, 2.5gbase-t, 5gbase-t
#   - SFP (1G): 1000base-x-sfp, 1000base-sx, 1000base-lx, 1000base-zx
#   - SFP+ (10G): 10gbase-x-sfpp, 10gbase-sr, 10gbase-lr, 10gbase-er
#   - SFP28 (25G): 25gbase-x-sfp28
#   - QSFP+ (40G): 40gbase-x-qsfpp, 40gbase-sr4, 40gbase-lr4
#   - QSFP28 (100G): 100gbase-x-qsfp28, 100gbase-sr4, 100gbase-lr4
#   - Virtual: virtual
# =============================================================================

# Маппинг media_type → NetBox interface type
# Порядок важен! Более специфичные паттерны должны быть первыми
NETBOX_INTERFACE_TYPE_MAP: Dict[str, str] = {
    # === 100G ===
    "qsfp 100g lr4": "100gbase-lr4",
    "qsfp-100g-cr4": "100gbase-sr4",
    "qsfp 100g sr4": "100gbase-sr4",
    "qsfp 100g er4": "100gbase-er4",
    "qsfp 40/100ge srbd": "100gbase-sr1.2",  # BiDi
    "100gbase-sr4": "100gbase-sr4",
    "100g-sr4": "100gbase-sr4",
    "100gbase-lr4": "100gbase-lr4",
    "100g-lr4": "100gbase-lr4",
    "100gbase-er4": "100gbase-er4",
    "100g-er4": "100gbase-er4",
    "qsfp28": "100gbase-x-qsfp28",
    "qsfp-100g": "100gbase-x-qsfp28",
    # === 40G ===
    "qsfp 40g cu3m": "40gbase-cr4",
    "qsfp-40g-cr4": "40gbase-sr4",
    "qsfp 40g cu": "40gbase-x-qsfpp",  # DAC
    "40gbase-sr4": "40gbase-sr4",
    "40g-sr4": "40gbase-sr4",
    "40gbase-lr4": "40gbase-lr4",
    "40g-lr4": "40gbase-lr4",
    "qsfp-40g": "40gbase-x-qsfpp",
    "qsfp 40g": "40gbase-x-qsfpp",
    # === 25G ===
    "sfp-25gbase-aoc": "25gbase-sr",
    "sfp-25gbase-sr": "25gbase-sr",
    "sfp-25gbase-lr": "25gbase-lr",
    "sfp-25gbase": "25gbase-x-sfp28",
    "25gbase-sr": "25gbase-sr",
    "25gbase-lr": "25gbase-lr",
    "sfp28": "25gbase-x-sfp28",
    "sfp-25g": "25gbase-x-sfp28",
    # === 10G Оптика ===
    "sfp-10gbase-lrm": "10gbase-lrm",
    "sfp-10gbase-lr": "10gbase-lr",
    "sfp-10gbase-sr": "10gbase-sr",
    "sfp-10gbase-er": "10gbase-er",
    "10gbase-lr": "10gbase-lr",
    "10gbase-sr": "10gbase-sr",
    "10gbase-er": "10gbase-er",
    "10g-sr": "10gbase-sr",
    "10g-lr": "10gbase-lr",
    "10g-er": "10gbase-er",
    "10gbase-zr": "10gbase-zr",
    "10g-zr": "10gbase-zr",
    "10gbase-lx4": "10gbase-lx4",
    "10gbase-lrm": "10gbase-lrm",
    "10gbase-cu": "10gbase-cx4",
    "10g-cu": "10gbase-cx4",
    "sfp+": "10gbase-x-sfpp",
    "sfp-10g": "10gbase-x-sfpp",
    "sfpp": "10gbase-x-sfpp",
    "sfp-h10gb": "10gbase-x-sfpp",
    # === 10G Медь ===
    "10gbaset": "10gbase-t",
    "10gbase-t": "10gbase-t",
    # === 1G SFP (оптика) ===
    "1000basesx": "1000base-sx",
    "1000base-sx": "1000base-sx",
    "1000baselx": "1000base-lx",
    "1000base-lx": "1000base-lx",
    "1000baselh": "1000base-lx",
    "1000base-lh": "1000base-lx",
    "1000basezx": "1000base-zx",
    "1000base-zx": "1000base-zx",
    "1000baseex": "1000base-ex",
    "1000base-ex": "1000base-ex",
    "1000basebx10u": "1000base-bx10-u",
    "1000basebx10d": "1000base-bx10-d",
    "1000basebx": "1000base-bx10-d",
    "1000base-bx": "1000base-bx10-d",
    "1000basecx": "1000base-cx",
    "1000base-cx": "1000base-cx",
    "1000base sfp": "1000base-x-sfp",
    # === 100M SFP ===
    "100basefx": "100base-fx",
    "100base-fx": "100base-fx",
    "100basefx-fe sfp": "100base-fx",
    "100basefx-fe": "100base-fx",
    "100baselx": "100base-fx",
    "100base-lx": "100base-fx",
    "100baselx-fe sfp": "100base-fx",
    "100baselx-fe": "100base-fx",
    # === Медные (RJ45) ===
    "basetx": "1000base-t",
    "base-tx": "1000base-t",
    "rj45": "1000base-t",
    "10/100/1000baset": "1000base-t",
    "10/100/1000": "1000base-t",
    "10/100": "100base-tx",
    "1000baset": "1000base-t",
    "100baset": "100base-tx",
    "10baset": "10base-t",
    # === 2.5G / 5G ===
    "2.5gbase": "2.5gbase-t",
    "5gbase": "5gbase-t",
}

# Маппинг hardware_type → NetBox interface type
NETBOX_HARDWARE_TYPE_MAP: Dict[str, str] = {
    # NX-OS multi-speed ports
    "100/1000/10000": "10gbase-x-sfpp",
    "1000/10000": "10gbase-x-sfpp",
    "100/1000": "1000base-t",
    # 100G
    "hundred gig": "100gbase-x-qsfp28",
    "hundredgig": "100gbase-x-qsfp28",
    "100g": "100gbase-x-qsfp28",
    # 40G
    "forty gig": "40gbase-x-qsfpp",
    "fortygig": "40gbase-x-qsfpp",
    "40g": "40gbase-x-qsfpp",
    # 25G
    "twenty five gig": "25gbase-x-sfp28",
    "twenty-five": "25gbase-x-sfp28",
    "twentyfive": "25gbase-x-sfp28",
    "25g": "25gbase-x-sfp28",
    # 10G
    "ten gig": "10gbase-x-sfpp",
    "tengig": "10gbase-x-sfpp",
    "tfgigabitethernet": "10gbase-x-sfpp",  # QTech 10G
    "10g": "10gbase-x-sfpp",
    # 1G - SFP на Cisco 6500
    "c6k 1000mb 802.3": "1000base-x-sfp",
    "c6k 1000mb": "1000base-x-sfp",
    # 1G - медные
    "gigabit": "1000base-t",
    "gige": "1000base-t",
    "igbe": "1000base-t",
    "1g": "1000base-t",
    "1000mb": "1000base-t",
    # 100M
    "fast ethernet": "100base-tx",
    "fastethernet": "100base-tx",
    "powerpc fastethernet": "100base-tx",
    "powerpc fast": "100base-tx",
    "100m": "100base-tx",
    "100base": "100base-tx",
}

# Виртуальные интерфейсы (префиксы имён)
VIRTUAL_INTERFACE_PREFIXES: tuple = (
    "vlan",
    "loopback",
    "lo",
    "null",
    "tunnel",
)

# Management интерфейсы (всегда медь)
MGMT_INTERFACE_PATTERNS: tuple = (
    "mgmt",
    "management",
    "oob",
    "fxp",
)

# Маппинг нормализованного port_type → NetBox interface type
PORT_TYPE_MAP: Dict[str, str] = {
    "100g-qsfp28": "100gbase-x-qsfp28",
    "40g-qsfp": "40gbase-x-qsfpp",
    "25g-sfp28": "25gbase-x-sfp28",
    "10g-sfp+": "10gbase-x-sfpp",
    "1g-sfp": "1000base-x-sfp",
    "1g-rj45": "1000base-t",
    "100m-rj45": "100base-tx",
    "lag": "lag",
    "virtual": "virtual",
}

# Маппинг префикса имени интерфейса → NetBox interface type
INTERFACE_NAME_PREFIX_MAP: Dict[str, str] = {
    # 100G
    "hundredgig": "100gbase-x-qsfp28",
    "hu": "100gbase-x-qsfp28",
    # 40G
    "fortygig": "40gbase-x-qsfpp",
    "fo": "40gbase-x-qsfpp",
    # 25G
    "twentyfive": "25gbase-x-sfp28",
    "twe": "25gbase-x-sfp28",
    # 10G
    "tengig": "10gbase-x-sfpp",
    "tfgigabitethernet": "10gbase-x-sfpp",  # QTech 10G
    "tf": "10gbase-x-sfpp",  # QTech 10G короткий
    "te": "10gbase-x-sfpp",  # Te1/1 короткий
    # 1G
    "gigabit": "1000base-t",
    "gi": "1000base-t",
    # 100M
    "fastethernet": "100base-tx",
    "fa": "100base-tx",
}


# Короткие префиксы, требующие проверки цифры после (чтобы "gi" не совпал с "gigabit...")
_SHORT_PREFIXES = {"hu", "fo", "twe", "tf", "te", "gi", "fa"}


def _detect_type_by_name_prefix(
    name_lower: str,
    media_lower: str = "",
    hw_lower: str = "",
) -> str:
    """
    Определяет тип интерфейса NetBox по префиксу имени.

    Использует INTERFACE_NAME_PREFIX_MAP как единый источник маппинга.
    Для GigabitEthernet учитывает SFP/медь на основе media_type/hardware_type.

    Args:
        name_lower: Имя интерфейса в нижнем регистре
        media_lower: media_type в нижнем регистре (для определения SFP у Gi)
        hw_lower: hardware_type в нижнем регистре (для определения SFP у Gi)

    Returns:
        str: Тип интерфейса для NetBox или пустая строка
    """
    for prefix, netbox_type in INTERFACE_NAME_PREFIX_MAP.items():
        if not name_lower.startswith(prefix):
            continue

        # Короткие префиксы: после них должна быть цифра
        if prefix in _SHORT_PREFIXES:
            if len(name_lower) <= len(prefix) or not name_lower[len(prefix)].isdigit():
                continue

        # GigabitEthernet/Gi: SFP или медь
        if prefix in ("gigabit", "gi"):
            is_sfp = "sfp" in media_lower or "sfp" in hw_lower or "no transceiver" in media_lower
            return "1000base-x-sfp" if is_sfp else netbox_type

        return netbox_type

    return ""


def _parse_speed_to_mbps(speed_str: str) -> int:
    """
    Парсит строку скорости в Mbps.

    Args:
        speed_str: Строка скорости ("1 Gbit", "10000 Kbit", "auto")

    Returns:
        int: Скорость в Mbps или 0 если не удалось распарсить
    """
    if not speed_str:
        return 0

    speed_lower = speed_str.lower().strip()
    if speed_lower in ("auto", "unknown", ""):
        return 0

    match = re.match(r"(\d+)\s*(k|m|g)?", speed_lower)
    if not match:
        return 0

    value = int(match.group(1))
    unit = match.group(2) or ""

    if "g" in unit or "gb" in speed_lower:
        return value * 1000
    elif "k" in unit or "kb" in speed_lower:
        return value // 1000
    else:
        return value


def get_netbox_interface_type(
    interface_name: str = "",
    media_type: str = "",
    hardware_type: str = "",
    port_type: str = "",
    speed_mbps: int = 0,
    *,
    interface: Any = None,
) -> str:
    """
    Определяет тип интерфейса для NetBox.

    Приоритет определения:
    1. LAG/Virtual по имени или port_type
    2. Management интерфейсы → медь
    3. media_type (наиболее точный: "SFP-10GBase-LR")
    4. port_type (нормализованный в коллекторе)
    5. hardware_type ("Gigabit Ethernet", "Ten Gigabit Ethernet SFP+")
    6. interface_name (Gi0/1, Te1/1)
    7. speed (fallback)

    Args:
        interface_name: Имя интерфейса (Gi0/1, TenGigabitEthernet1/1)
        media_type: Тип трансивера (SFP-10GBase-SR)
        hardware_type: Тип оборудования (Gigabit Ethernet)
        port_type: Нормализованный тип (10g-sfp+, 1g-rj45)
        speed_mbps: Скорость в Mbps
        interface: Interface модель (альтернатива отдельным параметрам)

    Returns:
        str: Тип интерфейса для NetBox API

    Examples:
        >>> get_netbox_interface_type("Port-channel1")
        'lag'
        >>> get_netbox_interface_type("Gi0/1", media_type="SFP-10GBase-SR")
        '10gbase-sr'
        >>> get_netbox_interface_type("Te1/1")
        '10gbase-x-sfpp'
    """
    # Если передана модель Interface, извлекаем поля
    if interface is not None:
        interface_name = getattr(interface, "name", "") or ""
        media_type = getattr(interface, "media_type", "") or ""
        hardware_type = getattr(interface, "hardware_type", "") or ""
        port_type = getattr(interface, "port_type", "") or ""
        speed_str = getattr(interface, "speed", "") or ""
        speed_mbps = _parse_speed_to_mbps(speed_str)

    name_lower = interface_name.lower() if interface_name else ""
    media_lower = media_type.lower() if media_type else ""
    hw_lower = hardware_type.lower() if hardware_type else ""

    # 1. LAG интерфейсы (Cisco Port-channel, QTech AggregatePort)
    if name_lower.startswith(("port-channel", "po", "aggregateport")) or port_type == "lag":
        return "lag"
    # QTech: Ag1, Ag10 (короткое имя AggregatePort)
    if (len(name_lower) >= 3 and name_lower[:2] == "ag"
            and name_lower[2].isdigit()):
        return "lag"

    # 2. Виртуальные интерфейсы
    if name_lower.startswith(VIRTUAL_INTERFACE_PREFIXES) or port_type == "virtual":
        return "virtual"

    # 3. Management интерфейсы - всегда медь
    if any(x in name_lower for x in MGMT_INTERFACE_PATTERNS):
        return "1000base-t"

    # 4. media_type - ВЫСШИЙ ПРИОРИТЕТ
    if media_lower and media_lower not in (
        "unknown",
        "not present",
        "no transceiver",
        "",
    ):
        for pattern, netbox_type in NETBOX_INTERFACE_TYPE_MAP.items():
            if pattern in media_lower:
                return netbox_type
        # Универсальный SFP для 1G
        if "sfp" in media_lower and ("1000base" in media_lower or "1g" in media_lower):
            if "baset" in media_lower:
                return "1000base-t"
            return "1000base-x-sfp"

    # 5. port_type - нормализованный тип из коллектора
    if port_type and port_type in PORT_TYPE_MAP:
        return PORT_TYPE_MAP[port_type]

    # 6. hardware_type
    if hw_lower and hw_lower not in ("amdp2", "ethersvi", ""):
        for pattern, netbox_type in NETBOX_HARDWARE_TYPE_MAP.items():
            if pattern in hw_lower:
                # Для 10G проверяем SFP в названии
                if "10g" in pattern and "sfp" in hw_lower:
                    return "10gbase-x-sfpp"
                # Для 1G проверяем SFP
                if pattern in ("gigabit", "gige", "igbe", "1g") and "sfp" in hw_lower:
                    return "1000base-x-sfp"
                return netbox_type

    # 7. По имени интерфейса (через INTERFACE_NAME_PREFIX_MAP)
    netbox_type = _detect_type_by_name_prefix(name_lower, media_lower, hw_lower)
    if netbox_type:
        return netbox_type

    # Ethernet (NX-OS) — особый случай: определяем по hardware_type/скорости
    if name_lower.startswith(("eth", "ethernet")) and not name_lower.startswith(
        "ethersvi"
    ):
        if "10000" in hw_lower or "10g" in hw_lower:
            return "10gbase-x-sfpp"
        elif "25000" in hw_lower or "25g" in hw_lower:
            return "25gbase-x-sfp28"
        elif "40000" in hw_lower or "40g" in hw_lower:
            return "40gbase-x-qsfpp"
        elif "100000" in hw_lower or "100g" in hw_lower:
            return "100gbase-x-qsfp28"
        elif speed_mbps:
            if speed_mbps <= 1000:
                return "1000base-t"
            elif speed_mbps <= 10000:
                return "10gbase-x-sfpp"
            elif speed_mbps <= 25000:
                return "25gbase-x-sfp28"

    # 8. Fallback по скорости
    if speed_mbps:
        is_sfp = "sfp" in media_lower or "sfp" in hw_lower
        if speed_mbps <= 100:
            return "100base-tx"
        elif speed_mbps <= 1000:
            return "1000base-x-sfp" if is_sfp else "1000base-t"
        elif speed_mbps <= 2500:
            return "2.5gbase-t"
        elif speed_mbps <= 5000:
            return "5gbase-t"
        elif speed_mbps <= 10000:
            return "10gbase-x-sfpp" if is_sfp else "10gbase-t"
        elif speed_mbps <= 25000:
            return "25gbase-x-sfp28"
        elif speed_mbps <= 40000:
            return "40gbase-x-qsfpp"
        elif speed_mbps <= 100000:
            return "100gbase-x-qsfp28"

    # Default
    return "1000base-t"
