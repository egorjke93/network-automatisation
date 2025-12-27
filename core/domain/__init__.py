"""
Domain Layer для Network Collector.

Бизнес-логика отделена от сбора данных (collectors).
Collectors только собирают сырые данные, Domain обрабатывает.

Normalizers:
- InterfaceNormalizer: нормализация интерфейсов
- MACNormalizer: нормализация MAC-таблицы
- LLDPNormalizer: нормализация LLDP/CDP соседей
- InventoryNormalizer: нормализация inventory (модули, SFP)

Использование:
    from network_collector.core.domain import InterfaceNormalizer

    normalizer = InterfaceNormalizer()
    interfaces = normalizer.normalize(raw_data)  # List[Interface]
"""

from .interface import InterfaceNormalizer
from .mac import MACNormalizer
from .lldp import LLDPNormalizer
from .inventory import InventoryNormalizer

__all__ = [
    "InterfaceNormalizer",
    "MACNormalizer",
    "LLDPNormalizer",
    "InventoryNormalizer",
]
