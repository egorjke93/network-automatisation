"""
Константы и маппинги для Network Collector.

Централизованное хранение всех констант, используемых в проекте.
Модуль разбит на подмодули для удобства поддержки.

Импорт:
    # Импорт всего (обратная совместимость)
    from network_collector.core.constants import normalize_mac_ieee, get_netbox_interface_type

    # Импорт из конкретного модуля
    from network_collector.core.constants.mac import normalize_mac_ieee
    from network_collector.core.constants.netbox import get_netbox_interface_type
"""

# =============================================================================
# RE-EXPORTS (обратная совместимость)
# =============================================================================

# Интерфейсы
from .interfaces import (
    INTERFACE_SHORT_MAP,
    INTERFACE_FULL_MAP,
    normalize_interface_short,
    normalize_interface_full,
    get_interface_aliases,
)

# Платформы
from .platforms import (
    SCRAPLI_PLATFORM_MAP,
    NTC_PLATFORM_MAP,
    NETMIKO_PLATFORM_MAP,
    NETBOX_TO_SCRAPLI_PLATFORM,
    VENDOR_MAP,
    get_vendor_by_platform,
)

# MAC
from .mac import (
    normalize_mac_raw,
    normalize_mac_ieee,
    normalize_mac_netbox,
    normalize_mac_cisco,
    normalize_mac,
)

# Утилиты
from .utils import (
    DEFAULT_OUTPUT_FOLDER,
    DEFAULT_BACKUP_FOLDER,
    DEFAULT_PREFIX_LENGTH,
    MAX_EXCEL_COLUMN_WIDTH,
    ONLINE_PORT_STATUSES,
    OFFLINE_PORT_STATUSES,
    slugify,
    transliterate_to_slug,
    mask_to_prefix,
)

# NetBox
from .netbox import (
    NETBOX_INTERFACE_TYPE_MAP,
    NETBOX_HARDWARE_TYPE_MAP,
    VIRTUAL_INTERFACE_PREFIXES,
    MGMT_INTERFACE_PATTERNS,
    PORT_TYPE_MAP,
    INTERFACE_NAME_PREFIX_MAP,
    get_netbox_interface_type,
)

# Устройства
from .devices import (
    CISCO_LICENSE_SUFFIXES,
    MODEL_PREFIXES_TO_REMOVE,
    normalize_device_model,
)

# Команды
from .commands import (
    COLLECTOR_COMMANDS,
    CUSTOM_TEXTFSM_TEMPLATES,
    get_collector_command,
)

__all__ = [
    # Интерфейсы
    "INTERFACE_SHORT_MAP",
    "INTERFACE_FULL_MAP",
    "normalize_interface_short",
    "normalize_interface_full",
    "get_interface_aliases",
    # Платформы
    "SCRAPLI_PLATFORM_MAP",
    "NTC_PLATFORM_MAP",
    "NETMIKO_PLATFORM_MAP",
    "NETBOX_TO_SCRAPLI_PLATFORM",
    "VENDOR_MAP",
    "get_vendor_by_platform",
    # MAC
    "normalize_mac_raw",
    "normalize_mac_ieee",
    "normalize_mac_netbox",
    "normalize_mac_cisco",
    "normalize_mac",
    # Утилиты
    "DEFAULT_OUTPUT_FOLDER",
    "DEFAULT_BACKUP_FOLDER",
    "DEFAULT_PREFIX_LENGTH",
    "MAX_EXCEL_COLUMN_WIDTH",
    "ONLINE_PORT_STATUSES",
    "OFFLINE_PORT_STATUSES",
    "slugify",
    "transliterate_to_slug",
    "mask_to_prefix",
    # NetBox
    "NETBOX_INTERFACE_TYPE_MAP",
    "NETBOX_HARDWARE_TYPE_MAP",
    "VIRTUAL_INTERFACE_PREFIXES",
    "MGMT_INTERFACE_PATTERNS",
    "PORT_TYPE_MAP",
    "INTERFACE_NAME_PREFIX_MAP",
    "get_netbox_interface_type",
    # Устройства
    "CISCO_LICENSE_SUFFIXES",
    "MODEL_PREFIXES_TO_REMOVE",
    "normalize_device_model",
    # Команды
    "COLLECTOR_COMMANDS",
    "CUSTOM_TEXTFSM_TEMPLATES",
    "get_collector_command",
]
