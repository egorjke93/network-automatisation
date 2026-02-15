"""
Команды коллекторов (централизованные).

Все платформо-зависимые команды для коллекторов.
"""

from typing import Dict

# =============================================================================
# КОМАНДЫ КОЛЛЕКТОРОВ
# =============================================================================

COLLECTOR_COMMANDS: Dict[str, Dict[str, str]] = {
    # MAC-адреса
    "mac": {
        "cisco_ios": "show mac address-table",
        "cisco_iosxe": "show mac address-table",
        "cisco_nxos": "show mac address-table",
        "arista_eos": "show mac address-table",
        "juniper_junos": "show ethernet-switching table",
        "juniper": "show ethernet-switching table",
        "qtech": "show mac address-table",
        "qtech_qsw": "show mac address-table",
    },
    # Интерфейсы
    "interfaces": {
        "cisco_ios": "show interfaces",
        "cisco_iosxe": "show interfaces",
        "cisco_nxos": "show interface",
        "arista_eos": "show interfaces",
        "juniper_junos": "show interfaces extensive",
        "juniper": "show interfaces extensive",
        "qtech": "show interface",
        "qtech_qsw": "show interface",
    },
    # Inventory
    "inventory": {
        "cisco_ios": "show inventory",
        "cisco_iosxe": "show inventory",
        "cisco_nxos": "show inventory",
        "arista_eos": "show inventory",
        "juniper_junos": "show chassis hardware",
        "juniper": "show chassis hardware",
    },
    # LLDP
    "lldp": {
        "cisco_ios": "show lldp neighbors detail",
        "cisco_iosxe": "show lldp neighbors detail",
        "cisco_nxos": "show lldp neighbors detail",
        "arista_eos": "show lldp neighbors detail",
        "juniper_junos": "show lldp neighbors",
        "juniper": "show lldp neighbors",
        "qtech": "show lldp neighbors detail",
        "qtech_qsw": "show lldp neighbors detail",
    },
    # CDP
    "cdp": {
        "cisco_ios": "show cdp neighbors detail",
        "cisco_iosxe": "show cdp neighbors detail",
        "cisco_nxos": "show cdp neighbors detail",
        "arista_eos": "show lldp neighbors detail",  # Arista: CDP → LLDP
        "qtech": "show cdp neighbors detail",
        "qtech_qsw": "show cdp neighbors detail",
    },
    # Devices (show version)
    "devices": {
        "cisco_ios": "show version",
        "cisco_iosxe": "show version",
        "cisco_nxos": "show version",
        "arista_eos": "show version",
        "juniper_junos": "show version",
        "juniper": "show version",
        "qtech": "show version",
        "qtech_qsw": "show version",
    },
}


# =============================================================================
# ВТОРИЧНЫЕ КОМАНДЫ КОЛЛЕКТОРОВ
# =============================================================================
# Дополнительные команды, которые коллекторы вызывают помимо основной.
# Централизованы здесь, чтобы не дублировать в каждом коллекторе.
# =============================================================================

SECONDARY_COMMANDS: Dict[str, Dict[str, str]] = {
    # Ошибки интерфейсов
    "interface_errors": {
        "cisco_ios": "show interfaces | include errors|CRC|input|output",
        "cisco_iosxe": "show interfaces | include errors|CRC|input|output",
        "cisco_nxos": "show interface counters errors",
        "arista_eos": "show interfaces counters errors",
    },
    # LAG (etherchannel/port-channel/aggregatePort)
    "lag": {
        "cisco_ios": "show etherchannel summary",
        "cisco_iosxe": "show etherchannel summary",
        "cisco_nxos": "show port-channel summary",
        "arista_eos": "show port-channel summary",
        "qtech": "show aggregatePort summary",
        "qtech_qsw": "show aggregatePort summary",
    },
    # Switchport mode
    "switchport": {
        "cisco_ios": "show interfaces switchport",
        "cisco_iosxe": "show interfaces switchport",
        "cisco_nxos": "show interface switchport",
        "arista_eos": "show interfaces switchport",
        "qtech": "show interface switchport",
        "qtech_qsw": "show interface switchport",
    },
    # Media type (тип трансивера из show interface status / show interface transceiver)
    # Cisco IOS/IOS-XE: НЕ нужен — media_type уже приходит из основной show interfaces
    # NX-OS: нужен — show interface возвращает только "10G", а не полный тип
    # QTech: нужен — show interface не возвращает media_type
    "media_type": {
        "cisco_nxos": "show interface status",
        "qtech": "show interface transceiver",
        "qtech_qsw": "show interface transceiver",
    },
    # Трансиверы для inventory
    "transceiver": {
        "cisco_nxos": "show interface transceiver",
        "qtech": "show interface transceiver",
        "qtech_qsw": "show interface transceiver",
    },
    # LLDP summary (для local interface)
    "lldp_summary": {
        "cisco_ios": "show lldp neighbors",
        "cisco_iosxe": "show lldp neighbors",
        "cisco_nxos": "show lldp neighbors",
        "arista_eos": "show lldp neighbors",
    },
}


def get_secondary_command(group: str, platform: str) -> str:
    """
    Возвращает вторичную команду для группы и платформы.

    Args:
        group: Группа команд (lag, switchport, transceiver, etc.)
        platform: Платформа устройства

    Returns:
        str: Команда для выполнения или пустая строка
    """
    commands = SECONDARY_COMMANDS.get(group, {})
    return commands.get(platform, "")


def get_collector_command(collector: str, platform: str) -> str:
    """
    Возвращает команду для коллектора и платформы.

    Args:
        collector: Тип коллектора (mac, interfaces, lldp, cdp, inventory, devices)
        platform: Платформа устройства (cisco_ios, arista_eos, etc.)

    Returns:
        str: Команда для выполнения или пустая строка

    Examples:
        >>> get_collector_command("mac", "cisco_ios")
        'show mac address-table'
        >>> get_collector_command("lldp", "arista_eos")
        'show lldp neighbors detail'
    """
    commands = COLLECTOR_COMMANDS.get(collector, {})
    return commands.get(platform, "")


# =============================================================================
# КАСТОМНЫЕ TEXTFSM ШАБЛОНЫ
# =============================================================================
# Для платформ с нестандартным выводом (QTech, Eltex и др.)
# Формат: (platform, command) → имя файла шаблона в папке templates/
# =============================================================================

CUSTOM_TEXTFSM_TEMPLATES: Dict[tuple, str] = {
    # Port-Security (парсинг sticky MAC из show running-config)
    ("cisco_ios", "port-security"): "cisco_ios_port_security.textfsm",
    ("cisco_iosxe", "port-security"): "cisco_ios_port_security.textfsm",
    # QTech шаблоны
    ("qtech", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech_qsw", "show mac address-table"): "qtech_show_mac_address_table.textfsm",
    ("qtech", "show version"): "qtech_show_version.textfsm",
    ("qtech_qsw", "show version"): "qtech_show_version.textfsm",
    ("qtech", "show interface"): "qtech_show_interface.textfsm",
    ("qtech_qsw", "show interface"): "qtech_show_interface.textfsm",
    ("qtech", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
    ("qtech_qsw", "show lldp neighbors detail"): "qtech_show_lldp_neighbors_detail.textfsm",
    ("qtech", "show interface status"): "qtech_show_interface_status.textfsm",
    ("qtech_qsw", "show interface status"): "qtech_show_interface_status.textfsm",
    ("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech_qsw", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech", "show interface transceiver"): "qtech_show_interface_transceiver.textfsm",
    ("qtech_qsw", "show interface transceiver"): "qtech_show_interface_transceiver.textfsm",
    # QTech LAG (AggregatePort)
    ("qtech", "show aggregateport summary"): "qtech_show_aggregatePort_summary.textfsm",
    ("qtech_qsw", "show aggregateport summary"): "qtech_show_aggregatePort_summary.textfsm",
}
