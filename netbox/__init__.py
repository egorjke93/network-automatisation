"""
Модуль интеграции с NetBox.

Использует библиотеку pynetbox для работы с NetBox API.
Поддерживает синхронизацию устройств, интерфейсов, IP, MAC.

Пример использования:
    from network_collector.netbox import NetBoxClient
    
    client = NetBoxClient(url="https://netbox.example.com", token="xxx")
    
    # Получить устройства
    devices = client.get_devices()
    
    # Синхронизировать интерфейсы
    client.sync_interfaces(device_id=1, interfaces_data=data)
    
    # Обновить MAC-адреса
    client.update_mac_addresses(mac_data)
"""

from .client import NetBoxClient
from .sync import NetBoxSync

__all__ = ["NetBoxClient", "NetBoxSync"]

