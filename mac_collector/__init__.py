"""
MAC Collector - модуль для сбора MAC-адресов с сетевого оборудования.

Поддерживаемые вендоры:
- Cisco IOS/IOS-XE/NX-OS
- Arista EOS
- Juniper
- Eltex

Использование:
    from mac_collector import collect_from_device, save_to_excel
    
    devices = [
        {
            "device_type": "cisco_ios",
            "host": "192.168.1.1",
            "username": "admin",
            "password": "password",
        },
    ]
    
    all_data = []
    for device in devices:
        data, hostname = collect_from_device(device)
        all_data.extend(data)
    
    save_to_excel(all_data)
"""

from .config import (
    EXCLUDE_TRUNK_PORTS,
    EXCLUDE_BY_NAME,
    EXCLUDE_INTERFACE_PATTERNS,
    COLLECT_STICKY_MAC,
    COLLECT_DYNAMIC_MAC,
    SAVE_PER_DEVICE,
    OUTPUT_FOLDER,
    MAC_FORMAT,
    SHOW_DEVICE_STATUS,
)

from .collector import collect_from_device, merge_mac_data
from .excel_writer import save_to_excel
from .parsers import get_parser

__version__ = "1.0.0"
__author__ = "Your Name"

__all__ = [
    # Основные функции
    "collect_from_device",
    "merge_mac_data",
    "save_to_excel",
    "get_parser",
    # Настройки
    "EXCLUDE_TRUNK_PORTS",
    "EXCLUDE_BY_NAME",
    "EXCLUDE_INTERFACE_PATTERNS",
    "COLLECT_STICKY_MAC",
    "COLLECT_DYNAMIC_MAC",
    "SAVE_PER_DEVICE",
    "OUTPUT_FOLDER",
    "MAC_FORMAT",
    "SHOW_DEVICE_STATUS",
]

