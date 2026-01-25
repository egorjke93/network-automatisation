"""
Нормализация MAC-адресов.

Поддерживаемые форматы: IEEE, Cisco, NetBox, Unix, raw.
"""


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
