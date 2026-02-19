"""
Нормализация имён интерфейсов.

Функции для сокращения и расширения имён интерфейсов.
"""

from typing import Dict, List

# =============================================================================
# LAG-ИНТЕРФЕЙСЫ
# =============================================================================

# Длинные LAG-префиксы (startswith достаточно)
_LAG_LONG_PREFIXES = ("port-channel", "aggregateport")
# Короткие LAG-префиксы (после них нужна цифра)
_LAG_SHORT_PREFIXES = ("po", "ag")
# Все LAG-префиксы (для документации и реэкспорта)
LAG_PREFIXES = _LAG_LONG_PREFIXES + _LAG_SHORT_PREFIXES


def is_lag_name(interface: str) -> bool:
    """
    Проверяет, является ли интерфейс LAG по имени.

    Поддерживает все форматы: Port-channel1, Po1, AggregatePort 1, Ag1.
    Использует LAG_PREFIXES как единый источник.

    Args:
        interface: Имя интерфейса в любом регистре

    Returns:
        bool: True если это LAG-интерфейс
    """
    if not interface:
        return False
    iface_lower = interface.lower().replace(" ", "")
    # Длинные префиксы — простой startswith
    if iface_lower.startswith(_LAG_LONG_PREFIXES):
        return True
    # Короткие (po, ag) — после них должна быть цифра
    for prefix in _LAG_SHORT_PREFIXES:
        if (iface_lower.startswith(prefix)
                and len(iface_lower) > len(prefix)
                and iface_lower[len(prefix)].isdigit()):
            return True
    return False


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
    ("tfgigabitethernet", "TF"),  # QTech 10G
    ("tengigabitethernet", "Te"),
    ("gigabitethernet", "Gi"),
    ("fastethernet", "Fa"),
    ("aggregateport", "Ag"),  # QTech LAG
    ("ethernet", "Eth"),  # NX-OS полное: Ethernet1/1 → Eth1/1
    ("port-channel", "Po"),
    ("vlan", "Vl"),
    ("loopback", "Lo"),
    # Уже короткие формы (не менять)
    ("eth", "Eth"),  # Eth1/1 → Eth1/1 (без изменений)
    ("twe", "Twe"),  # Twe1/0/17 (уже короткий)
    ("ten", "Te"),  # Ten 1/1/4 (CDP формат)
]

# Обратный маппинг: короткое имя → полное
INTERFACE_FULL_MAP: Dict[str, str] = {
    "Gi": "GigabitEthernet",
    "Fa": "FastEthernet",
    "Te": "TenGigabitEthernet",
    "TF": "TFGigabitEthernet",  # QTech 10G
    "Twe": "TwentyFiveGigE",
    "Fo": "FortyGigabitEthernet",
    "Hu": "HundredGigE",
    "Eth": "Ethernet",
    "Et": "Ethernet",  # Et1/1 → Ethernet1/1
    "Ag": "AggregatePort",  # QTech LAG
    "Po": "Port-channel",
    "Vl": "Vlan",
    "Lo": "Loopback",
}


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
            result = short + result[len(full_lower) :]
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
    # Убираем пробелы между типом и номером (QTech: "TFGigabitEthernet 0/48" → "TFGigabitEthernet0/48")
    interface = interface.replace(" ", "").strip()

    for short_name, full_name in INTERFACE_FULL_MAP.items():
        if (
            interface.startswith(short_name)
            and not interface.startswith(full_name)
            # Убеждаемся что после сокращения идёт цифра (Hu0/55, не HundredGig...)
            and len(interface) > len(short_name)
            and interface[len(short_name)].isdigit()
        ):
            return interface.replace(short_name, full_name, 1)
    return interface


def get_interface_aliases(interface: str) -> List[str]:
    """
    Возвращает все возможные варианты написания интерфейса.

    Используется для маппинга статусов интерфейсов, где разные команды
    могут возвращать разные форматы имён.

    Args:
        interface: Имя интерфейса в любом формате

    Returns:
        List[str]: Все варианты написания (включая исходный)

    Examples:
        >>> get_interface_aliases("GigabitEthernet0/1")
        ['GigabitEthernet0/1', 'Gi0/1', 'Gig0/1']
        >>> get_interface_aliases("Te1/0/1")
        ['Te1/0/1', 'TenGigabitEthernet1/0/1', 'Ten1/0/1']
    """
    if not interface:
        return []

    aliases = {interface}  # Используем set для уникальности
    clean = interface.replace(" ", "")
    aliases.add(clean)

    # Добавляем короткую форму
    short = normalize_interface_short(clean)
    if short != clean:
        aliases.add(short)

    # Добавляем полную форму
    full = normalize_interface_full(clean)
    if full != clean:
        aliases.add(full)

    # Дополнительные альтернативные сокращения
    clean_lower = clean.lower()

    # Маппинг дополнительных форм
    EXTRA_ALIASES = {
        "gigabitethernet": ["Gig"],
        "tengigabitethernet": ["Ten"],
        "ethernet": ["Et", "Eth"],
    }

    for prefix, extras in EXTRA_ALIASES.items():
        if clean_lower.startswith(prefix):
            suffix = clean[len(prefix):]
            for extra in extras:
                aliases.add(f"{extra}{suffix}")

    # Обратные маппинги для коротких форм
    SHORT_TO_EXTRA = {
        "gi": ["Gig"],
        "te": ["Ten"],
        "hu": ["HundredGigabitEthernet"],  # QTech полное имя
        "eth": ["Et"],
        "et": ["Eth"],
    }

    for short_prefix, extras in SHORT_TO_EXTRA.items():
        if clean_lower.startswith(short_prefix) and len(clean) > len(short_prefix):
            next_char = clean[len(short_prefix)]
            if next_char.isdigit():
                suffix = clean[len(short_prefix):]
                for extra in extras:
                    aliases.add(f"{extra}{suffix}")

    return list(aliases)


# =============================================================================
# МАППИНГ PORT_TYPE (упрощённая категория скорости)
# =============================================================================
# Используется в domain layer (detect_port_type) для единообразного определения
# типа порта. Порядок ключей критичен — более специфичные паттерны первыми.

# media_type паттерн → port_type
# Пример: "SFP-10GBase-SR" содержит "10gbase" → "10g-sfp+"
MEDIA_TYPE_PORT_TYPE_MAP: Dict[str, str] = {
    "100gbase": "100g-qsfp28",
    "100g": "100g-qsfp28",
    "40gbase": "40g-qsfp",
    "40g": "40g-qsfp",
    "25gbase": "25g-sfp28",
    "25g": "25g-sfp28",
    "10gbase": "10g-sfp+",
    "10g": "10g-sfp+",
    "1000base-t": "1g-rj45",
    "rj45": "1g-rj45",
    "1000base": "1g-sfp",
    "sfp": "1g-sfp",
}

# hardware_type паттерн → port_type
# Порядок: NX-OS multi-speed → 100G → 40G → 25G → 10G → 1G
# "10000" перед "1000" чтобы не было ложного совпадения
HARDWARE_TYPE_PORT_TYPE_MAP: Dict[str, str] = {
    # NX-OS multi-speed (должны быть первыми)
    "100/1000/10000": "10g-sfp+",
    # 100G
    "100000": "100g-qsfp28",
    "100g": "100g-qsfp28",
    "hundred": "100g-qsfp28",
    # 40G
    "40000": "40g-qsfp",
    "40g": "40g-qsfp",
    "forty": "40g-qsfp",
    # 25G
    "25000": "25g-sfp28",
    "25g": "25g-sfp28",
    "twenty five": "25g-sfp28",
    "twentyfive": "25g-sfp28",  # без пробела
    "twenty-five": "25g-sfp28",  # через дефис
    # 10G
    "10000": "10g-sfp+",
    "10g": "10g-sfp+",
    "ten gig": "10g-sfp+",
    "tengig": "10g-sfp+",  # без пробела (NX-OS, Arista)
    "tfgigabitethernet": "10g-sfp+",  # QTech 10G
    # 1G (после 10G, чтобы "10000" не матчил "1000")
    "1000": "1g-rj45",
    "gigabit": "1g-rj45",
}

# Префикс имени интерфейса → port_type
# Короткие префиксы (hu, fo, twe, tf, te, gi, fa) требуют цифру после
INTERFACE_NAME_PORT_TYPE_MAP: Dict[str, str] = {
    "hundredgig": "100g-qsfp28",
    "hu": "100g-qsfp28",
    "fortygig": "40g-qsfp",
    "fo": "40g-qsfp",
    "twentyfivegig": "25g-sfp28",
    "twe": "25g-sfp28",
    "tfgigabitethernet": "10g-sfp+",  # QTech 10G
    "tf": "10g-sfp+",  # QTech 10G короткий
    "tengig": "10g-sfp+",
    "te": "10g-sfp+",
    "gigabit": "1g-rj45",
    "gi": "1g-rj45",
    "fastethernet": "100m-rj45",
    "fa": "100m-rj45",
}

# Короткие префиксы, требующие цифры после (для port_type detection)
_SHORT_PORT_TYPE_PREFIXES = {"hu", "fo", "twe", "tf", "te", "gi", "fa"}
