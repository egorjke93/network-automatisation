"""
Утилиты для работы с MAC-адресами и интерфейсами.
"""

import re
from .config import MAC_FORMAT, EXCLUDE_BY_NAME, EXCLUDE_INTERFACE_PATTERNS


def normalize_mac(mac: str) -> str:
    """
    Приводит MAC-адрес к единому формату для сравнения.
    Убирает разделители и приводит к нижнему регистру.
    
    Пример: 0011.2233.4455 -> 001122334455
    """
    return re.sub(r"[.:\-]", "", mac).lower()


def format_mac(mac: str) -> str:
    """
    Форматирует MAC-адрес согласно настройке MAC_FORMAT.
    
    Варианты:
        "colon"    -> 00:00:00:00:00:00
        "dash"     -> 00-00-00-00-00-00
        "cisco"    -> 0000.0000.0000
        "none"     -> 000000000000
        "original" -> оставить как есть
    """
    if MAC_FORMAT == "original":
        return mac

    # Убираем все разделители, приводим к нижнему регистру
    clean_mac = re.sub(r"[.:\-]", "", mac).lower()

    # Проверяем длину (должно быть 12 символов)
    if len(clean_mac) != 12:
        return mac  # Возвращаем как есть если формат некорректный

    if MAC_FORMAT == "colon":
        return ":".join(clean_mac[i : i + 2] for i in range(0, 12, 2))
    elif MAC_FORMAT == "dash":
        return "-".join(clean_mac[i : i + 2] for i in range(0, 12, 2))
    elif MAC_FORMAT == "cisco":
        return ".".join(clean_mac[i : i + 4] for i in range(0, 12, 4))
    elif MAC_FORMAT == "none":
        return clean_mac
    else:
        return mac


def normalize_interface_name(iface_name: str) -> str:
    """
    Приводит имя интерфейса к короткому формату.
    
    Примеры:
        GigabitEthernet0/1    -> Gi0/1
        FastEthernet0/1       -> Fa0/1
        TenGigabitEthernet1/0/1 -> Te1/0/1
        Ethernet0/1           -> Et0/1
    """
    replacements = [
        ("TenGigabitEthernet", "Te"),
        ("GigabitEthernet", "Gi"),
        ("FastEthernet", "Fa"),
        ("Ethernet", "Et"),
        ("Port-channel", "Po"),
        ("Vlan", "Vl"),
    ]

    result = iface_name
    for full, short in replacements:
        if result.startswith(full):
            result = short + result[len(full):]
            break

    return result


def get_interface_description(interfaces: dict, iface_name: str) -> str:
    """
    Получает description интерфейса, пробуя разные варианты имени.
    
    Args:
        interfaces: словарь {interface_name: description}
        iface_name: имя интерфейса (может быть полным или коротким)
    
    Returns:
        description или пустая строка
    """
    # Точное совпадение
    if iface_name in interfaces:
        return interfaces[iface_name]

    # Нормализованное имя
    short_name = normalize_interface_name(iface_name)
    if short_name in interfaces:
        return interfaces[short_name]

    return ""


def should_exclude_interface(interface_name: str) -> bool:
    """
    Проверяет, нужно ли исключить интерфейс из результатов.
    """
    if not EXCLUDE_BY_NAME:
        return False

    for pattern in EXCLUDE_INTERFACE_PATTERNS:
        if interface_name.startswith(pattern):
            return True
    return False


def natural_sort_key(interface_name: str) -> list:
    """
    Возвращает ключ для естественной сортировки интерфейсов.
    
    Результат: Gi0/1, Gi0/2, ..., Gi0/10 (а не Gi0/1, Gi0/10, Gi0/2)
    """
    parts = re.split(r"(\d+)", interface_name)
    result = []
    for part in parts:
        if part.isdigit():
            result.append(int(part))
        else:
            result.append(part)
    return result

