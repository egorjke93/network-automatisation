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

VLAN:
- parse_vlan_range: парсинг строки "10,20,30-50" в список [10,20,30,31,...,50]
- VlanSet: множество VLAN для сравнения и операций

Использование:
    from network_collector.core.domain import InterfaceNormalizer, SyncComparator

    normalizer = InterfaceNormalizer()
    interfaces = normalizer.normalize(raw_data)  # List[Interface]

    comparator = SyncComparator()
    diff = comparator.compare_interfaces(local, remote)

    from network_collector.core.domain import parse_vlan_range, VlanSet
    vids = parse_vlan_range("10,20,30-50")  # [10, 20, 30, 31, ..., 50]
"""

from .interface import InterfaceNormalizer
from .mac import MACNormalizer
from .lldp import LLDPNormalizer
from .inventory import InventoryNormalizer
from .sync import SyncComparator, SyncDiff, SyncItem, ChangeType, FieldChange, get_cable_endpoints
from .vlan import parse_vlan_range, is_full_vlan_range, VlanSet, FULL_VLAN_RANGES

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
    # VLAN
    "parse_vlan_range",
    "is_full_vlan_range",
    "VlanSet",
    "FULL_VLAN_RANGES",
]
