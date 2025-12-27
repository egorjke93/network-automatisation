"""
Константы и маппинги для Network Collector.

Централизованное хранение всех констант, используемых в проекте.
"""

import re
from typing import Any, Dict, List

# =============================================================================
# МАППИНГ ИНТЕРФЕЙСОВ
# =============================================================================

# Сокращения интерфейсов: полное имя (lowercase) → короткое
# Порядок важен! Более длинные паттерны первыми
INTERFACE_SHORT_MAP: List[tuple] = [
    # Полные имена (от длинных к коротким)
    ("twentyfivegigabitethernet", "Twe"),
    ("twentyfivegige", "Twe"),
    ("hundredgigabitethernet", "Hu"),
    ("hundredgige", "Hu"),
    ("fortygigabitethernet", "Fo"),
    ("tengigabitethernet", "Te"),
    ("gigabitethernet", "Gi"),
    ("fastethernet", "Fa"),
    ("ethernet", "Eth"),  # NX-OS полное: Ethernet1/1 → Eth1/1
    ("port-channel", "Po"),
    ("vlan", "Vl"),
    ("loopback", "Lo"),
    # Уже короткие формы (не менять)
    ("eth", "Eth"),  # Eth1/1 → Eth1/1 (без изменений)
    ("twe", "Twe"),  # Twe1/0/17 (уже короткий)
    ("ten", "Te"),   # Ten 1/1/4 (CDP формат)
]

# Обратный маппинг: короткое имя → полное
INTERFACE_FULL_MAP: Dict[str, str] = {
    "Gi": "GigabitEthernet",
    "Fa": "FastEthernet",
    "Te": "TenGigabitEthernet",
    "Twe": "TwentyFiveGigE",
    "Fo": "FortyGigabitEthernet",
    "Hu": "HundredGigE",
    "Eth": "Ethernet",
    "Et": "Ethernet",  # Et1/1 → Ethernet1/1
    "Po": "Port-channel",
    "Vl": "Vlan",
    "Lo": "Loopback",
}


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


def normalize_interface_short(interface: str, lowercase: bool = False) -> str:
    """
    Сокращает имя интерфейса.

    GigabitEthernet0/1 -> Gi0/1 (или gi0/1 с lowercase=True)

    Поддерживает:
    - Полные имена: GigabitEthernet, TenGigabitEthernet, etc.
    - CDP/LLDP форматы: "Ten 1/1/4" -> "Te1/1/4"
    - Пробелы в именах интерфейсов

    Args:
        interface: Полное имя интерфейса
        lowercase: Приводить к нижнему регистру для сравнения

    Returns:
        str: Сокращённое имя
    """
    if not interface:
        return ""

    # Убираем пробелы между типом и номером (CDP/LLDP формат: "Ten 1/1/4")
    result = interface.replace(" ", "").strip()
    result_lower = result.lower()

    # Ищем совпадение в маппинге (порядок важен — длинные первыми)
    for full_lower, short in INTERFACE_SHORT_MAP:
        if result_lower.startswith(full_lower):
            result = short + result[len(full_lower):]
            break

    return result.lower() if lowercase else result


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
# НОРМАЛИЗАЦИЯ MAC-АДРЕСОВ
# =============================================================================


def normalize_mac_raw(mac: str) -> str:
    """
    Нормализует MAC-адрес в сырой формат (12 символов, нижний регистр).

    Используется для сравнения MAC-адресов.

    Args:
        mac: MAC-адрес в любом формате

    Returns:
        str: 12 символов в нижнем регистре (aabbccddeeff) или ""
    """
    if not mac:
        return ""
    # Убираем все разделители
    mac_clean = mac.strip().lower()
    for char in [":", "-", ".", " "]:
        mac_clean = mac_clean.replace(char, "")
    # Проверяем длину
    if len(mac_clean) != 12:
        return ""
    return mac_clean


def normalize_mac_ieee(mac: str) -> str:
    """
    Нормализует MAC-адрес в IEEE формат (aa:bb:cc:dd:ee:ff).

    Args:
        mac: MAC-адрес в любом формате

    Returns:
        str: MAC в формате aa:bb:cc:dd:ee:ff (или пустая строка)
    """
    clean = normalize_mac_raw(mac)
    if not clean:
        return ""
    return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


def normalize_mac_netbox(mac: str) -> str:
    """
    Нормализует MAC-адрес в формат NetBox (AA:BB:CC:DD:EE:FF).

    Args:
        mac: MAC-адрес в любом формате

    Returns:
        str: MAC в формате AA:BB:CC:DD:EE:FF (или пустая строка)
    """
    clean = normalize_mac_raw(mac)
    if not clean:
        return ""
    return ":".join(clean[i : i + 2].upper() for i in range(0, 12, 2))


def normalize_mac_cisco(mac: str) -> str:
    """
    Нормализует MAC-адрес в формат Cisco (aabb.ccdd.eeff).

    Args:
        mac: MAC-адрес в любом формате

    Returns:
        str: MAC в формате aabb.ccdd.eeff (или пустая строка)
    """
    clean = normalize_mac_raw(mac)
    if not clean:
        return ""
    return f"{clean[0:4]}.{clean[4:8]}.{clean[8:12]}"


def normalize_mac(mac: str, format: str = "ieee") -> str:
    """
    Нормализует MAC-адрес в указанный формат.

    Args:
        mac: MAC-адрес в любом формате
        format: Формат вывода:
            - "raw": aabbccddeeff (12 символов, нижний регистр)
            - "ieee": aa:bb:cc:dd:ee:ff
            - "netbox": AA:BB:CC:DD:EE:FF
            - "cisco": aabb.ccdd.eeff
            - "unix": aa-bb-cc-dd-ee-ff

    Returns:
        str: MAC в указанном формате (или пустая строка)
    """
    clean = normalize_mac_raw(mac)
    if not clean:
        return ""

    if format == "raw":
        return clean
    elif format == "cisco":
        return f"{clean[0:4]}.{clean[4:8]}.{clean[8:12]}"
    elif format == "netbox":
        return ":".join(clean[i : i + 2].upper() for i in range(0, 12, 2))
    elif format == "unix":
        return "-".join(clean[i : i + 2] for i in range(0, 12, 2))
    else:  # ieee (default)
        return ":".join(clean[i : i + 2] for i in range(0, 12, 2))


# =============================================================================
# SLUG GENERATION
# =============================================================================


def slugify(name: str) -> str:
    """
    Генерирует slug для NetBox из имени.

    Преобразует:
    - Пробелы в дефисы
    - Подчёркивания в дефисы
    - Слэши в дефисы
    - Всё в нижний регистр

    Args:
        name: Исходное имя

    Returns:
        str: Slug для NetBox

    Examples:
        >>> slugify("Main Office")
        'main-office'
        >>> slugify("C9200L-24P/4X")
        'c9200l-24p-4x'
    """
    if not name:
        return ""
    return name.lower().replace(" ", "-").replace("_", "-").replace("/", "-")


# Таблица транслитерации кириллицы в латиницу
_TRANSLIT_TABLE: Dict[str, str] = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def transliterate_to_slug(name: str) -> str:
    """
    Транслитерирует кириллицу в латиницу и создаёт валидный slug.

    Args:
        name: Имя (может содержать кириллицу)

    Returns:
        str: Валидный slug (только латиница, цифры, дефисы, подчёркивания)

    Examples:
        >>> transliterate_to_slug("Москва")
        'moskva'
        >>> transliterate_to_slug("Офис №1")
        'ofis-1'
    """
    result = []
    for char in name.lower():
        if char in _TRANSLIT_TABLE:
            result.append(_TRANSLIT_TABLE[char])
        elif char.isalnum() or char in '-_':
            result.append(char)
        elif char == ' ':
            result.append('-')
        # Другие символы пропускаем
    return ''.join(result)


# =============================================================================
# NETWORK UTILITIES
# =============================================================================


def mask_to_prefix(mask: str) -> int:
    """
    Конвертирует маску сети в длину префикса.

    Args:
        mask: Маска в формате 255.255.255.0 или уже числовой префикс

    Returns:
        int: Длина префикса (например, 24)

    Examples:
        >>> mask_to_prefix("255.255.255.0")
        24
        >>> mask_to_prefix("255.255.0.0")
        16
        >>> mask_to_prefix("24")
        24
    """
    if not mask:
        return 24
    # Если уже число (строка или int)
    if str(mask).isdigit():
        return int(mask)
    try:
        octets = [int(x) for x in mask.split(".")]
        binary = "".join(format(x, "08b") for x in octets)
        return binary.count("1")
    except Exception:
        return 24


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
    "qsfp 100g lr4": "100gbase-lr4",  # QSFP 100G LR4
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
    "qsfp 40g cu": "40gbase-x-qsfpp",  # QSFP 40G CU3M (DAC)
    "40gbase-sr4": "40gbase-sr4",
    "40g-sr4": "40gbase-sr4",
    "40gbase-lr4": "40gbase-lr4",
    "40g-lr4": "40gbase-lr4",
    "qsfp-40g": "40gbase-x-qsfpp",
    "qsfp 40g": "40gbase-x-qsfpp",  # QSFP 40G ...
    # === 25G ===
    "sfp-25gbase-aoc": "25gbase-x-sfp28",  # SFP-25GBase-AOC3M
    "sfp-25gbase-sr": "25gbase-sr",  # SFP-25GBase-SR (must be before generic sfp-25gbase!)
    "sfp-25gbase-lr": "25gbase-lr",  # SFP-25GBase-LR
    "sfp-25gbase": "25gbase-x-sfp28",  # SFP-25GBase-... (generic)
    "25gbase-sr": "25gbase-sr",
    "25gbase-lr": "25gbase-lr",
    "sfp28": "25gbase-x-sfp28",
    "sfp-25g": "25gbase-x-sfp28",
    # === 10G Оптика ===
    "sfp-10gbase-lrm": "10gbase-lrm",  # SFP-10GBase-LRM (must be before LR!)
    "sfp-10gbase-lr": "10gbase-lr",  # SFP-10GBase-LR
    "sfp-10gbase-sr": "10gbase-sr",  # SFP-10GBase-SR
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
    "10gbase-cu": "10gbase-cx4",  # DAC кабель
    "10g-cu": "10gbase-cx4",
    "sfp+": "10gbase-x-sfpp",
    "sfp-10g": "10gbase-x-sfpp",
    "sfpp": "10gbase-x-sfpp",
    "sfp-h10gb": "10gbase-x-sfpp",
    # === 10G Медь ===
    "10gbaset": "10gbase-t",
    "10gbase-t": "10gbase-t",
    # === 1G SFP (оптика) ===
    "1000basesx": "1000base-sx",  # 1000BaseSX (Cisco 6509 format)
    "1000base-sx": "1000base-sx",
    "1000baselx": "1000base-lx",  # 1000BaseLX
    "1000base-lx": "1000base-lx",
    "1000baselh": "1000base-lx",  # 1000BaseLH = Long Haul ≈ LX
    "1000base-lh": "1000base-lx",
    "1000basezx": "1000base-zx",
    "1000base-zx": "1000base-zx",
    "1000baseex": "1000base-ex",
    "1000base-ex": "1000base-ex",
    "1000basebx10u": "1000base-bx10-u",  # 1000BaseBX10U (BiDi upstream)
    "1000basebx10d": "1000base-bx10-d",  # 1000BaseBX10D (BiDi downstream)
    "1000basebx": "1000base-bx10-d",
    "1000base-bx": "1000base-bx10-d",
    "1000basecx": "1000base-cx",
    "1000base-cx": "1000base-cx",
    "1000base sfp": "1000base-x-sfp",  # Generic SFP
    # === 100M SFP (FastEthernet оптика) ===
    "100basefx": "100base-fx",  # 100BaseFX (multi-mode)
    "100base-fx": "100base-fx",
    "100basefx-fe sfp": "100base-fx",  # Cisco format
    "100basefx-fe": "100base-fx",
    "100baselx": "100base-lx10",  # 100BaseLX (single-mode, 10km)
    "100base-lx": "100base-lx10",
    "100baselx-fe sfp": "100base-lx10",  # Cisco format
    "100baselx-fe": "100base-lx10",
    "100base-lx10": "100base-lx10",
    # === Медные (RJ45) ===
    "basetx": "1000base-t",
    "base-tx": "1000base-t",
    "rj45": "1000base-t",
    "10/100/1000baset": "1000base-t",  # 10/100/1000BaseT
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
    "1000/10000": "10gbase-x-sfpp",  # NX-OS 10G SFP+ port
    "100/1000": "1000base-t",  # NX-OS 1G copper port
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

# Маппинг нормализованного port_type → NetBox interface type
# Используется когда коллектор определил тип порта платформонезависимо
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
# Порядок важен! Более длинные префиксы первыми
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
    # 10G (полные имена)
    "tengig": "10gbase-x-sfpp",
    # 1G
    "gigabit": "1000base-t",  # default, SFP определяется отдельно
    "gi": "1000base-t",
    # 100M
    "fastethernet": "100base-tx",
    "fa": "100base-tx",
}


def _parse_speed_to_mbps(speed_str: str) -> int:
    """
    Парсит строку скорости в Mbps.

    Args:
        speed_str: Строка скорости ("1 Gbit", "10000 Kbit", "auto")

    Returns:
        int: Скорость в Mbps или 0 если не удалось распарсить

    Examples:
        >>> _parse_speed_to_mbps("1 Gbit")
        1000
        >>> _parse_speed_to_mbps("10000 Kbit")
        10
        >>> _parse_speed_to_mbps("100 Mbit")
        100
    """
    if not speed_str:
        return 0

    speed_lower = speed_str.lower().strip()
    if speed_lower in ("auto", "unknown", ""):
        return 0

    # Пытаемся извлечь число и единицу
    match = re.match(r"(\d+)\s*(k|m|g)?", speed_lower)
    if not match:
        return 0

    value = int(match.group(1))
    unit = match.group(2) or ""

    if "g" in unit or "gb" in speed_lower:
        return value * 1000  # Gbit → Mbit
    elif "k" in unit or "kb" in speed_lower:
        return value // 1000  # Kbit → Mbit
    else:
        return value  # Already Mbit


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
        >>> get_netbox_interface_type(interface=some_interface)  # Interface model
        '10gbase-x-sfpp'
    """
    # Если передана модель Interface, извлекаем поля
    if interface is not None:
        interface_name = getattr(interface, "name", "") or ""
        media_type = getattr(interface, "media_type", "") or ""
        hardware_type = getattr(interface, "hardware_type", "") or ""
        port_type = getattr(interface, "port_type", "") or ""
        speed_str = getattr(interface, "speed", "") or ""
        # Парсим скорость из строки
        speed_mbps = _parse_speed_to_mbps(speed_str)
    name_lower = interface_name.lower() if interface_name else ""
    media_lower = media_type.lower() if media_type else ""
    hw_lower = hardware_type.lower() if hardware_type else ""

    # 1. LAG интерфейсы
    if name_lower.startswith(("port-channel", "po")) or port_type == "lag":
        return "lag"

    # 2. Виртуальные интерфейсы
    if name_lower.startswith(VIRTUAL_INTERFACE_PREFIXES) or port_type == "virtual":
        return "virtual"

    # 3. Management интерфейсы - всегда медь
    if any(x in name_lower for x in MGMT_INTERFACE_PATTERNS):
        return "1000base-t"

    # 4. media_type - ВЫСШИЙ ПРИОРИТЕТ (самая точная информация о трансивере)
    if media_lower and media_lower not in ("unknown", "not present", "no transceiver", ""):
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

    # 7. По имени интерфейса
    is_sfp_port = "sfp" in media_lower or "sfp" in hw_lower or "no transceiver" in media_lower

    # HundredGigE (100G)
    if name_lower.startswith(("hu", "hundredgig")):
        return "100gbase-x-qsfp28"

    # FortyGigE (40G)
    if name_lower.startswith(("fo", "fortygig")):
        return "40gbase-x-qsfpp"

    # TwentyFiveGigE (25G)
    if name_lower.startswith(("twe", "twentyfive")):
        return "25gbase-x-sfp28"

    # TenGigabitEthernet (10G)
    if name_lower.startswith("tengig"):
        return "10gbase-x-sfpp"
    # Te1/1, Te2/0/1 - короткий формат
    if len(name_lower) >= 3 and name_lower[:2] == "te" and name_lower[2].isdigit():
        return "10gbase-x-sfpp"

    # GigabitEthernet (1G)
    if name_lower.startswith(("gi", "gigabit")):
        return "1000base-x-sfp" if is_sfp_port else "1000base-t"

    # FastEthernet (100M)
    if name_lower.startswith(("fa", "fastethernet")):
        return "100base-tx"

    # Ethernet (NX-OS) - проверяем hardware_type на максимальную скорость
    if name_lower.startswith(("eth", "ethernet")) and not name_lower.startswith("ethersvi"):
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
