"""
Domain Layer для Network Collector.

Бизнес-логика отделена от сбора данных (collectors) и инфраструктуры (netbox).
Collectors только собирают сырые данные, Domain обрабатывает.

Normalizers:
- InterfaceNormalizer: нормализация интерфейсов
- MACNormalizer: нормализация MAC-таблицы
- LLDPNormalizer: нормализация LLDP/CDP соседей
- InventoryNormalizer: нормализация inventory (модули, SFP)

Sync:
- SyncComparator: сравнение локальных и удалённых данных
- SyncDiff: результат сравнения (to_create, to_update, to_delete)

Использование:
    from network_collector.core.domain import InterfaceNormalizer, SyncComparator

    normalizer = InterfaceNormalizer()
    interfaces = normalizer.normalize(raw_data)  # List[Interface]

    comparator = SyncComparator()
    diff = comparator.compare_interfaces(local, remote)
"""

from .interface import InterfaceNormalizer
from .mac import MACNormalizer
from .lldp import LLDPNormalizer
from .inventory import InventoryNormalizer
from .sync import SyncComparator, SyncDiff, SyncItem, ChangeType, FieldChange, get_cable_endpoints

__all__ = [
    "InterfaceNormalizer",
    "MACNormalizer",
    "LLDPNormalizer",
    "InventoryNormalizer",
    "SyncComparator",
    "SyncDiff",
    "SyncItem",
    "ChangeType",
    "FieldChange",
    "get_cable_endpoints",
]
