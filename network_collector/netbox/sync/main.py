"""
Главный класс NetBoxSync, объединяющий все sync-операции.

Использует mixin-классы для организации кода по доменам:
- InterfacesSyncMixin: sync_interfaces
- CablesSyncMixin: sync_cables_from_lldp
- IPAddressesSyncMixin: sync_ip_addresses
- DevicesSyncMixin: create_device, sync_devices_from_inventory
- VLANsSyncMixin: sync_vlans_from_interfaces
- InventorySyncMixin: sync_inventory
"""

from typing import Optional

from .base import SyncBase, NetBoxClient, RunContext
from .interfaces import InterfacesSyncMixin
from .cables import CablesSyncMixin
from .ip_addresses import IPAddressesSyncMixin
from .devices import DevicesSyncMixin
from .vlans import VLANsSyncMixin
from .inventory import InventorySyncMixin


class NetBoxSync(
    InterfacesSyncMixin,
    CablesSyncMixin,
    IPAddressesSyncMixin,
    DevicesSyncMixin,
    VLANsSyncMixin,
    InventorySyncMixin,
    SyncBase,
):
    """
    Синхронизация данных с NetBox.

    ВАЖНО: Мы ТОЛЬКО ЧИТАЕМ с устройств и ЗАПИСЫВАЕМ в NetBox!
    Никаких изменений на сетевых устройствах.

    Attributes:
        client: NetBox клиент
        dry_run: Режим симуляции (без изменений)
        create_only: Только создавать новые объекты
        update_only: Только обновлять существующие

    Example:
        # Проверить что будет изменено
        sync = NetBoxSync(client, dry_run=True)
        sync.sync_interfaces("switch-01", interfaces)

        # Только создавать новое
        sync = NetBoxSync(client, create_only=True)
        sync.sync_cables_from_lldp(lldp_data)

    Доступные методы:
        - sync_interfaces(device_name, interfaces, ...)
        - sync_cables_from_lldp(lldp_data, ...)
        - sync_ip_addresses(device_name, ip_data, ...)
        - create_device(name, device_type, ...)
        - sync_devices_from_inventory(inventory_data, ...)
        - sync_vlans_from_interfaces(device_name, interfaces, ...)
        - sync_inventory(device_name, inventory_data)
    """

    def __init__(
        self,
        client: NetBoxClient,
        dry_run: bool = False,
        create_only: bool = False,
        update_only: bool = False,
        context: Optional[RunContext] = None,
    ):
        """
        Инициализация синхронизатора.

        Args:
            client: NetBox клиент
            dry_run: Режим симуляции (ничего не меняет)
            create_only: Только создавать новые объекты
            update_only: Только обновлять существующие
            context: Контекст выполнения
        """
        super().__init__(
            client=client,
            dry_run=dry_run,
            create_only=create_only,
            update_only=update_only,
            context=context,
        )
