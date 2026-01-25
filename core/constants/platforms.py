"""
Маппинг платформ для разных библиотек.

Scrapli, NTC Templates, Netmiko, NetBox.
"""

from typing import Dict, List

# =============================================================================
# МАППИНГ ПЛАТФОРМ
# =============================================================================

# Маппинг типов устройств для Scrapli
SCRAPLI_PLATFORM_MAP: Dict[str, str] = {
    # Cisco
    "cisco_ios": "cisco_iosxe",
    "cisco_iosxe": "cisco_iosxe",
    "cisco_nxos": "cisco_nxos",
    "cisco_iosxr": "cisco_iosxr",
    # Arista
    "arista_eos": "arista_eos",
    # Juniper
    "juniper_junos": "juniper_junos",
    "juniper": "juniper_junos",
    # QTech (используем generic для совместимости)
    "qtech": "cisco_iosxe",
    "qtech_qsw": "cisco_iosxe",
}

# Маппинг для NTC Templates
NTC_PLATFORM_MAP: Dict[str, str] = {
    "cisco_iosxe": "cisco_ios",
    "cisco_ios": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "cisco_iosxr": "cisco_xr",
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
    "qtech": "cisco_ios",
    "qtech_qsw": "cisco_ios",
}

# Маппинг для Netmiko (используется в ConfigPusher)
# Netmiko не знает cisco_iosxe - использует cisco_ios для IOS/IOS-XE
NETMIKO_PLATFORM_MAP: Dict[str, str] = {
    "cisco_iosxe": "cisco_ios",
    "cisco_ios": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "cisco_iosxr": "cisco_xr",
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
    "qtech": "cisco_ios",
    "qtech_qsw": "cisco_ios",
}

# Маппинг NetBox platform slug → Scrapli platform
# Используется при импорте устройств из NetBox
NETBOX_TO_SCRAPLI_PLATFORM: Dict[str, str] = {
    # Cisco (с дефисами - стандартные NetBox slugs)
    "cisco-ios": "cisco_ios",
    "cisco-ios-xe": "cisco_ios",
    "cisco-iosxe": "cisco_ios",
    "cisco-nxos": "cisco_nxos",
    "cisco-nx-os": "cisco_nxos",
    "cisco-iosxr": "cisco_iosxr",
    "cisco-ios-xr": "cisco_iosxr",
    # Cisco (с underscore - альтернативные варианты)
    "cisco_ios": "cisco_ios",
    "cisco_iosxe": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "cisco_iosxr": "cisco_iosxr",
    # Arista
    "arista-eos": "arista_eos",
    "arista_eos": "arista_eos",
    # Juniper
    "juniper-junos": "juniper_junos",
    "juniper_junos": "juniper_junos",
    "junos": "juniper_junos",
    # QTech
    "qtech": "cisco_ios",
    "qtech-qsw": "cisco_ios",
    "qtech_qsw": "cisco_ios",
    # Generic
    "linux": "linux",
}

# Маппинг вендоров по типу устройства
VENDOR_MAP: Dict[str, List[str]] = {
    "cisco": [
        "cisco_ios",
        "cisco_iosxe",
        "cisco_xe",
        "cisco_iosxr",
        "cisco_xr",
        "cisco_nxos",
        "cisco_asa",
    ],
    "arista": ["arista_eos"],
    "juniper": ["juniper", "juniper_junos"],
    "huawei": ["huawei", "huawei_vrp"],
    "eltex": ["eltex", "eltex_mes"],
    "mikrotik": ["mikrotik_routeros"],
    "fortinet": ["fortinet"],
    "paloalto": ["paloalto_panos"],
    "qtech": ["qtech", "qtech_qsw"],
}


def get_vendor_by_platform(platform: str) -> str:
    """
    Определяет вендора по платформе.

    Args:
        platform: Платформа устройства (cisco_ios, arista_eos, etc.)

    Returns:
        str: Название вендора
    """
    if not platform:
        return "unknown"

    platform_lower = platform.lower()
    for vendor, platforms in VENDOR_MAP.items():
        if platform_lower in platforms:
            return vendor

    # Пробуем извлечь из platform
    return platform.split("_")[0]
