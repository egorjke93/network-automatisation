"""
Модуль синхронизации с NetBox.

Разбит на логические части:
- base: Базовые методы и утилиты
- interfaces: Синхронизация интерфейсов
- cables: Синхронизация кабелей из LLDP/CDP
- ip_addresses: Синхронизация IP-адресов
- devices: Синхронизация устройств
- vlans: Синхронизация VLAN
- inventory: Синхронизация inventory

Backward compatibility:
    from netbox.sync import NetBoxSync  # OK
    from netbox.sync.main import NetBoxSync  # OK
"""

from .main import NetBoxSync

__all__ = ["NetBoxSync"]
