"""
Константы и маппинги для Network Collector.

Централизованное хранение всех констант, используемых в проекте.
"""

from typing import Dict, List

# =============================================================================
# МАППИНГ ИНТЕРФЕЙСОВ
# =============================================================================

# Сокращения интерфейсов: полное имя → короткое
INTERFACE_SHORT_MAP: Dict[str, str] = {
    "GigabitEthernet": "Gi",
    "FastEthernet": "Fa",
    "TenGigabitEthernet": "Te",
    "TwentyFiveGigE": "Twe",
    "FortyGigabitEthernet": "Fo",
    "HundredGigE": "Hu",
    "Ethernet": "Et",  # Et0/0 - формат из show mac address-table
    "Port-channel": "Po",
    "Vlan": "Vl",
    "Loopback": "Lo",
}

# Обратный маппинг: короткое имя → полное
INTERFACE_FULL_MAP: Dict[str, str] = {v: k for k, v in INTERFACE_SHORT_MAP.items()}


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

# Маппинг вендоров по типу устройства
VENDOR_MAP: Dict[str, List[str]] = {
    "cisco": [
        "cisco_ios", "cisco_iosxe", "cisco_xe",
        "cisco_iosxr", "cisco_xr", "cisco_nxos", "cisco_asa",
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


# =============================================================================
# ДЕФОЛТНЫЕ ЗНАЧЕНИЯ
# =============================================================================

# Дефолтная папка для отчётов
DEFAULT_OUTPUT_FOLDER: str = "reports"

# Дефолтная папка для бэкапов
DEFAULT_BACKUP_FOLDER: str = "backups"

# Дефолтная длина маски подсети (если не указана)
DEFAULT_PREFIX_LENGTH: int = 24

# Максимальная ширина колонки в Excel
MAX_EXCEL_COLUMN_WIDTH: int = 50


# =============================================================================
# СТАТУСЫ
# =============================================================================

# Статусы портов, означающие "online"
ONLINE_PORT_STATUSES: List[str] = ["connected", "connect", "up"]

# Статусы портов, означающие "offline"
OFFLINE_PORT_STATUSES: List[str] = ["notconnect", "notconnected", "down", "disabled"]


# =============================================================================
# ФУНКЦИИ-ПОМОЩНИКИ
# =============================================================================


def normalize_interface_short(interface: str) -> str:
    """
    Сокращает имя интерфейса.

    GigabitEthernet0/1 -> Gi0/1

    Args:
        interface: Полное имя интерфейса

    Returns:
        str: Сокращённое имя
    """
    for full_name, short_name in INTERFACE_SHORT_MAP.items():
        if interface.startswith(full_name):
            return interface.replace(full_name, short_name, 1)
    return interface


def normalize_interface_full(interface: str) -> str:
    """
    Расширяет сокращённое имя интерфейса.

    Gi0/1 -> GigabitEthernet0/1

    Args:
        interface: Сокращённое имя интерфейса

    Returns:
        str: Полное имя
    """
    for short_name, full_name in INTERFACE_FULL_MAP.items():
        if interface.startswith(short_name) and not interface.startswith(full_name):
            return interface.replace(short_name, full_name, 1)
    return interface


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


# =============================================================================
# МАППИНГ ТИПОВ ИНТЕРФЕЙСОВ ДЛЯ NETBOX
# =============================================================================
# Используется для автоопределения типа интерфейса по media_type/hardware_type
#
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
    "qsfp 100g lr4": "100gbase-lr4",       # QSFP 100G LR4
    "qsfp 100g sr4": "100gbase-sr4",
    "qsfp 100g er4": "100gbase-er4",
    "qsfp 40/100ge srbd": "100gbase-x-qsfp28",  # QSFP 40/100GE SRBD (BiDi)
    "100gbase-sr4": "100gbase-sr4",
    "100g-sr4": "100gbase-sr4",
    "100gbase-lr4": "100gbase-lr4",
    "100g-lr4": "100gbase-lr4",
    "100gbase-er4": "100gbase-er4",
    "100g-er4": "100gbase-er4",
    "qsfp28": "100gbase-x-qsfp28",
    "qsfp-100g": "100gbase-x-qsfp28",
    # === 40G ===
    "qsfp 40g cu": "40gbase-x-qsfpp",      # QSFP 40G CU3M (DAC)
    "40gbase-sr4": "40gbase-sr4",
    "40g-sr4": "40gbase-sr4",
    "40gbase-lr4": "40gbase-lr4",
    "40g-lr4": "40gbase-lr4",
    "qsfp-40g": "40gbase-x-qsfpp",
    "qsfp 40g": "40gbase-x-qsfpp",         # QSFP 40G ...
    # === 25G ===
    "sfp-25gbase-aoc": "25gbase-x-sfp28",  # SFP-25GBase-AOC3M
    "sfp-25gbase-sr": "25gbase-sr",        # SFP-25GBase-SR (must be before generic sfp-25gbase!)
    "sfp-25gbase-lr": "25gbase-lr",        # SFP-25GBase-LR
    "sfp-25gbase": "25gbase-x-sfp28",      # SFP-25GBase-... (generic)
    "25gbase-sr": "25gbase-sr",
    "25gbase-lr": "25gbase-lr",
    "sfp28": "25gbase-x-sfp28",
    "sfp-25g": "25gbase-x-sfp28",
    # === 10G Оптика ===
    "sfp-10gbase-lrm": "10gbase-lrm",      # SFP-10GBase-LRM (must be before LR!)
    "sfp-10gbase-lr": "10gbase-lr",        # SFP-10GBase-LR
    "sfp-10gbase-sr": "10gbase-sr",        # SFP-10GBase-SR
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
    "10gbase-cu": "10gbase-cx4",           # DAC кабель
    "10g-cu": "10gbase-cx4",
    "sfp+": "10gbase-x-sfpp",
    "sfp-10g": "10gbase-x-sfpp",
    "sfpp": "10gbase-x-sfpp",
    "sfp-h10gb": "10gbase-x-sfpp",
    # === 10G Медь ===
    "10gbaset": "10gbase-t",
    "10gbase-t": "10gbase-t",
    # === 1G SFP (оптика) ===
    "1000basesx": "1000base-sx",           # 1000BaseSX (Cisco 6509 format)
    "1000base-sx": "1000base-sx",
    "1000baselx": "1000base-lx",           # 1000BaseLX
    "1000base-lx": "1000base-lx",
    "1000baselh": "1000base-lx",           # 1000BaseLH = Long Haul ≈ LX
    "1000base-lh": "1000base-lx",
    "1000basezx": "1000base-zx",
    "1000base-zx": "1000base-zx",
    "1000baseex": "1000base-ex",
    "1000base-ex": "1000base-ex",
    "1000basebx10u": "1000base-bx10-u",    # 1000BaseBX10U (BiDi upstream)
    "1000basebx10d": "1000base-bx10-d",    # 1000BaseBX10D (BiDi downstream)
    "1000basebx": "1000base-bx10-d",
    "1000base-bx": "1000base-bx10-d",
    "1000basecx": "1000base-cx",
    "1000base-cx": "1000base-cx",
    "1000base sfp": "1000base-x-sfp",      # Generic SFP
    # === 100M SFP (FastEthernet оптика) ===
    "100basefx": "100base-fx",             # 100BaseFX (multi-mode)
    "100base-fx": "100base-fx",
    "100basefx-fe sfp": "100base-fx",      # Cisco format
    "100basefx-fe": "100base-fx",
    "100baselx": "100base-lx10",           # 100BaseLX (single-mode, 10km)
    "100base-lx": "100base-lx10",
    "100baselx-fe sfp": "100base-lx10",    # Cisco format
    "100baselx-fe": "100base-lx10",
    "100base-lx10": "100base-lx10",
    # === Медные (RJ45) ===
    "basetx": "1000base-t",
    "base-tx": "1000base-t",
    "rj45": "1000base-t",
    "10/100/1000baset": "1000base-t",      # 10/100/1000BaseT
    "10/100/1000": "1000base-t",
    "10/100": "100base-tx",
    "1000baset": "1000base-t",
    "100baset": "100base-tx",
    "10baset": "10base-t",
    # === 2.5G / 5G ===
    "2.5gbase": "2.5gbase-t",
    "5gbase": "5gbase-t",
}

# Маппинг hardware_type → NetBox interface type (менее специфичный)
NETBOX_HARDWARE_TYPE_MAP: Dict[str, str] = {
    # NX-OS multi-speed ports (check first, more specific)
    "100/1000/10000": "10gbase-x-sfpp",  # NX-OS 10G SFP+ port
    "1000/10000": "10gbase-x-sfpp",       # NX-OS 10G SFP+ port
    "100/1000": "1000base-t",             # NX-OS 1G copper port
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
    "10g": "10gbase-x-sfpp",
    # 1G - SFP порты на Cisco 6500 серии
    "c6k 1000mb 802.3": "1000base-x-sfp",  # Cisco 6500 SFP порт
    "c6k 1000mb": "1000base-x-sfp",
    # 1G - медные
    "gigabit": "1000base-t",
    "gige": "1000base-t",
    "igbe": "1000base-t",
    "1g": "1000base-t",
    "1000mb": "1000base-t",
    # 100M (FastEthernet) - NetBox использует 100base-tx
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


# =============================================================================
# НОРМАЛИЗАЦИЯ МОДЕЛЕЙ УСТРОЙСТВ
# =============================================================================
# Убираем лишние префиксы и суффиксы лицензий для NetBox
#
# Примеры:
#   WS-C2960C-8TC-L → C2960C-8TC
#   WS-C3850-24P-S → C3850-24P
#   C9300-48P-E → C9300-48P
# =============================================================================

# Лицензионные суффиксы Cisco (убираются)
CISCO_LICENSE_SUFFIXES: tuple = (
    "-L",  # LAN Base
    "-S",  # IP Base / Standard
    "-E",  # IP Services / Enterprise
    "-A",  # Advanced
    "-K9",  # Crypto
)

# Префиксы для удаления
MODEL_PREFIXES_TO_REMOVE: tuple = ("WS-",)  # Cisco legacy


def normalize_device_model(model: str) -> str:
    """
    Нормализует модель устройства для NetBox.

    Убирает:
    - WS- префикс
    - Лицензионные суффиксы (-L, -S, -E, -A, -K9)

    Оставляет:
    - Порты (-8TC, -24P, -48T и т.д.)

    Args:
        model: Сырая модель из show version (например "WS-C2960C-8TC-L")

    Returns:
        str: Нормализованная модель (например "C2960C-8TC")

    Examples:
        >>> normalize_device_model("WS-C2960C-8TC-L")
        'C2960C-8TC'
        >>> normalize_device_model("WS-C3850-24P-S")
        'C3850-24P'
        >>> normalize_device_model("C9300-48P-E")
        'C9300-48P'
        >>> normalize_device_model("N9K-C93180YC-EX")
        'N9K-C93180YC-EX'
    """
    if not model:
        return model

    result = model.strip().upper()

    # Убираем префиксы
    for prefix in MODEL_PREFIXES_TO_REMOVE:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break

    # Убираем лицензионные суффиксы (только в конце)
    for suffix in CISCO_LICENSE_SUFFIXES:
        if result.endswith(suffix):
            result = result[: -len(suffix)]
            break

    return result


# =============================================================================
# КАСТОМНЫЕ TEXTFSM ШАБЛОНЫ
# =============================================================================
# Для платформ с нестандартным выводом (QTech, Eltex и др.)
# Если вывод отличается от Cisco, добавь маппинг здесь.
#
# Формат: (platform, command) → имя файла шаблона в папке templates/
# Шаблоны ищутся в network_collector/templates/
#
# Пример использования:
#   1. Добавь маппинг: ("qtech", "show mac address-table"): "qtech_show_mac.textfsm"
#   2. Создай шаблон: templates/qtech_show_mac.textfsm
#   3. Готово! Парсер автоматически использует кастомный шаблон для qtech
# =============================================================================

CUSTOM_TEXTFSM_TEMPLATES: Dict[tuple, str] = {
    # =========================================================================
    # Port-Security (парсинг sticky MAC из show running-config)
    # =========================================================================
    # Виртуальный ключ "port-security" — парсит show run для извлечения sticky MACs
    # Одна команда show run, разные шаблоны для разных целей
    ("cisco_ios", "port-security"): "cisco_ios_port_security.textfsm",
    ("cisco_iosxe", "port-security"): "cisco_ios_port_security.textfsm",
    # Для других вендоров добавить свои шаблоны:
    # ("arista_eos", "port-security"): "arista_eos_port_security.textfsm",
    # ("qtech", "port-security"): "qtech_port_security.textfsm",

    # =========================================================================
    # QTech примеры (раскомментируй и создай шаблоны если нужно)
    # =========================================================================
    # ("qtech", "show mac address-table"): "qtech_show_mac.textfsm",
    # ("qtech", "show version"): "qtech_show_version.textfsm",
    # ("qtech", "show interfaces"): "qtech_show_interfaces.textfsm",

    # =========================================================================
    # Eltex примеры
    # =========================================================================
    # ("eltex", "show mac address-table"): "eltex_show_mac.textfsm",
}
