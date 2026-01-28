"""
NetBox Client - объединяет все mixins.
"""

from .base import NetBoxClientBase
from .devices import DevicesMixin
from .interfaces import InterfacesMixin
from .ip_addresses import IPAddressesMixin
from .vlans import VLANsMixin
from .inventory import InventoryMixin
from .dcim import DCIMMixin


class NetBoxClient(
    DevicesMixin,
    InterfacesMixin,
    IPAddressesMixin,
    VLANsMixin,
    InventoryMixin,
    DCIMMixin,
    NetBoxClientBase,
):
    """
    Клиент для работы с NetBox API через pynetbox.

    Предоставляет методы для CRUD операций с объектами NetBox:
    - Устройства (devices)
    - Интерфейсы (interfaces)
    - IP-адреса (ip_addresses)
    - Префиксы (prefixes)
    - VLAN
    - Inventory Items
    - Device Types, Manufacturers, Roles, Sites, Platforms

    Attributes:
        url: URL NetBox сервера
        api: Объект pynetbox.api

    Example:
        client = NetBoxClient(
            url="https://netbox.example.com",
            token="xxx"
        )

        # Получить устройства
        for device in client.get_devices():
            print(device.name)

        # Найти устройство по IP
        device = client.get_device_by_ip("10.0.0.1")

        # Создать интерфейс
        client.create_interface(
            device_id=1,
            name="GigabitEthernet0/1",
            interface_type="1000base-t",
        )
    """

    pass
