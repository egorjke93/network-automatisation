"""
Core модули Network Collector.

Содержит базовые классы для работы с устройствами:
- Device: Представление сетевого устройства
- ConnectionManager: Управление SSH подключениями через Scrapli
- CredentialsManager: Безопасное управление учётными данными
- constants: Константы и маппинги
"""

from .device import Device, DeviceStatus
from .connection import ConnectionManager
from .credentials import CredentialsManager, Credentials

__all__ = [
    "Device",
    "DeviceStatus",
    "ConnectionManager",
    "CredentialsManager",
    "Credentials",
]

