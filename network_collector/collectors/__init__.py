"""
Коллекторы данных с сетевых устройств.

Все коллекторы используют Scrapli для подключения
и NTC Templates для парсинга.

Коллекторы:
- DeviceCollector: Сбор инвентаризационных данных устройств
- MACCollector: Сбор MAC-адресов
- LLDPCollector: Сбор LLDP/CDP соседей
- InterfaceCollector: Сбор информации об интерфейсах
- ConfigBackupCollector: Резервное копирование конфигураций

Пример использования:
    from network_collector.collectors import MACCollector, DeviceCollector

    # Сбор MAC-адресов
    collector = MACCollector()
    data = collector.collect(devices)

    # Сбор инвентаризации
    inv_collector = DeviceCollector()
    devices_data = inv_collector.collect(devices)

    # Резервное копирование конфигураций
    backup = ConfigBackupCollector(credentials)
    results = backup.backup(devices)
"""

from .base import BaseCollector
from .mac import MACCollector
from .device import DeviceCollector, DeviceInventoryCollector
from .lldp import LLDPCollector
from .interfaces import InterfaceCollector
from .inventory import InventoryCollector
from .config_backup import ConfigBackupCollector, BackupResult

__all__ = [
    "BaseCollector",
    "MACCollector",
    "DeviceCollector",
    "DeviceInventoryCollector",
    "LLDPCollector",
    "InterfaceCollector",
    "InventoryCollector",
    "ConfigBackupCollector",
    "BackupResult",
]
