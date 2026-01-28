"""
NetBox Client - модуль для работы с NetBox API.

Использует библиотеку pynetbox для взаимодействия с NetBox.
Предоставляет удобные методы для работы с устройствами,
интерфейсами, IP-адресами и MAC-адресами.

Пример использования:
    from network_collector.netbox.client import NetBoxClient

    client = NetBoxClient(
        url="https://netbox.example.com",
        token="your-api-token"
    )

    # Получить все устройства
    devices = client.get_devices()

    # Найти устройство по имени
    device = client.get_device_by_name("switch-01")

    # Получить интерфейсы устройства
    interfaces = client.get_interfaces(device_id=1)

Модуль разбит на компоненты:
    - base.py         - базовый класс, инициализация
    - devices.py      - работа с устройствами
    - interfaces.py   - работа с интерфейсами
    - ip_addresses.py - работа с IP и кабелями
    - vlans.py        - работа с VLAN
    - inventory.py    - работа с inventory items
    - dcim.py         - device types, manufacturers, roles, sites, platforms
    - main.py         - NetBoxClient (объединяет все mixins)
"""

from .main import NetBoxClient
from .base import NetBoxClientBase, PYNETBOX_AVAILABLE

__all__ = [
    "NetBoxClient",
    "NetBoxClientBase",
    "PYNETBOX_AVAILABLE",
]
