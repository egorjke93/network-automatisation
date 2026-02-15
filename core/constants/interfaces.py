"""
Нормализация имён интерфейсов.

Функции для сокращения и расширения имён интерфейсов.
"""

from typing import Dict, List

# =============================================================================
# LAG-ИНТЕРФЕЙСЫ
# =============================================================================

# Префиксы LAG-интерфейсов (все варианты написания, lowercase)
LAG_PREFIXES = ("port-channel", "po", "aggregateport", "ag")


def is_lag_name(interface: str) -> bool:
    """
    Проверяет, является ли интерфейс LAG по имени.

    Поддерживает все форматы: Port-channel1, Po1, AggregatePort 1, Ag1.

    Args:
        interface: Имя интерфейса в любом регистре

    Returns:
        bool: True если это LAG-интерфейс
    """
    if not interface:
        return False
    iface_lower = interface.lower().replace(" ", "")
    # Длинные префиксы — простой startswith
    if iface_lower.startswith(("port-channel", "aggregateport")):
        return True
    # Короткие (po, ag) — после них должна быть цифра
    for prefix in ("po", "ag"):
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
