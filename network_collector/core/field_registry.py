"""
Field Registry — единый источник правды для полей.

Централизованное описание всех полей:
- Канонические имена (используются в моделях)
- Алиасы из NTC Templates и разных платформ
- Display names по умолчанию
- NetBox API field names

Цепочка данных:
    NTC Templates → Normalizer → Model → Export/Sync
    (raw aliases)   (canonical)  (canonical)  (display/netbox)

Использование:
    from core.field_registry import FIELD_REGISTRY, get_canonical_name

    # Найти каноническое имя для любого алиаса
    canonical = get_canonical_name("lldp", "NEIGHBOR_NAME")  # → "remote_hostname"

    # Получить все алиасы
    aliases = get_all_aliases("lldp", "remote_hostname")  # → {"remote_hostname", "NEIGHBOR_NAME", ...}

    # Валидация fields.yaml
    from core.field_registry import validate_fields_config
    errors = validate_fields_config()
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class FieldDefinition:
    """
    Определение одного поля.

    Attributes:
        canonical: Каноническое имя (как в модели)
        aliases: Алиасы из NTC Templates и парсеров (SCREAMING_CASE, snake_case)
        display: Display name по умолчанию (для Excel/CSV)
        netbox_field: Имя поля в NetBox API (если отличается от canonical)
        description: Описание поля
    """
    canonical: str
    aliases: List[str] = field(default_factory=list)
    display: str = ""
    netbox_field: str = ""
    description: str = ""

    def __post_init__(self):
        if not self.display:
            self.display = self.canonical.replace("_", " ").title()

    def all_names(self) -> Set[str]:
        """Возвращает все имена (canonical + aliases)."""
        return {self.canonical} | set(self.aliases)


# =============================================================================
# FIELD REGISTRY — все поля по типам данных
# =============================================================================

FIELD_REGISTRY: Dict[str, Dict[str, FieldDefinition]] = {
    # -------------------------------------------------------------------------
    # LLDP/CDP соседи
    # -------------------------------------------------------------------------
    "lldp": {
        "local_interface": FieldDefinition(
            canonical="local_interface",
            aliases=["LOCAL_INTERFACE", "LOCAL_INTF", "local_intf", "local_port"],
            display="Local Port",
            description="Локальный интерфейс",
        ),
        "remote_hostname": FieldDefinition(
            canonical="remote_hostname",
            aliases=[
                "NEIGHBOR_NAME", "NEIGHBOR", "neighbor", "neighbor_name",
                "SYSTEM_NAME", "system_name", "DEVICE_ID", "device_id",
            ],
            display="Neighbor",
            description="Имя соседа (hostname)",
        ),
        "remote_port": FieldDefinition(
            canonical="remote_port",
            aliases=["NEIGHBOR_PORT_ID", "neighbor_port_id", "PORT_ID", "port_id"],
            display="Neighbor Port",
            description="Порт соседа",
        ),
        "remote_ip": FieldDefinition(
            canonical="remote_ip",
            aliases=[
                "MGMT_ADDRESS", "MGMT_IP", "mgmt_address", "mgmt_ip",
                "MANAGEMENT_IP", "management_ip",
            ],
            display="Neighbor IP",
            netbox_field="",  # Не синхронизируется напрямую
            description="Management IP соседа",
        ),
        "remote_mac": FieldDefinition(
            canonical="remote_mac",
            aliases=["CHASSIS_ID", "chassis_id"],
            display="Neighbor MAC",
            description="MAC-адрес соседа (Chassis ID)",
        ),
        "remote_platform": FieldDefinition(
            canonical="remote_platform",
            aliases=["PLATFORM", "platform", "HARDWARE", "hardware"],
            display="Platform",
            description="Платформа соседа",
        ),
        "capabilities": FieldDefinition(
            canonical="capabilities",
            aliases=["CAPABILITIES", "CAPABILITY", "capability"],
            display="Capabilities",
            description="Capabilities соседа (Router, Switch, etc)",
        ),
        "protocol": FieldDefinition(
            canonical="protocol",
            aliases=[],
            display="Protocol",
            description="Протокол обнаружения (LLDP, CDP, BOTH)",
        ),
        "neighbor_type": FieldDefinition(
            canonical="neighbor_type",
            aliases=[],
            display="ID Type",
            description="Тип идентификации соседа (hostname, mac, ip)",
        ),
        "port_description": FieldDefinition(
            canonical="port_description",
            aliases=["NEIGHBOR_INTERFACE", "neighbor_interface", "PORT_DESCRIPTION"],
            display="Port Description",
            description="Описание порта соседа (не путать с remote_port!)",
        ),
        # Общие поля (добавляются коллектором)
        "hostname": FieldDefinition(
            canonical="hostname",
            aliases=[],
            display="Device",
            description="Hostname локального устройства",
        ),
        "device_ip": FieldDefinition(
            canonical="device_ip",
            aliases=[],
            display="Device IP",
            description="IP локального устройства",
        ),
    },

    # -------------------------------------------------------------------------
    # MAC-адреса
    # -------------------------------------------------------------------------
    "mac": {
        "mac": FieldDefinition(
            canonical="mac",
            aliases=["MAC", "MAC_ADDRESS", "mac_address", "DESTINATION_ADDRESS", "destination_address"],
            display="MAC Address",
            description="MAC-адрес",
        ),
        "interface": FieldDefinition(
            canonical="interface",
            aliases=["INTERFACE", "DESTINATION_PORT", "destination_port", "PORT", "port"],
            display="Port",
            description="Интерфейс",
        ),
        "vlan": FieldDefinition(
            canonical="vlan",
            aliases=["VLAN", "VLAN_ID", "vlan_id"],
            display="VLAN",
            description="VLAN ID",
        ),
        "mac_type": FieldDefinition(
            canonical="mac_type",
            aliases=["TYPE", "type"],  # В fields.yaml это "type"
            display="Type",
            description="Тип записи (dynamic, static, sticky)",
        ),
        "status": FieldDefinition(
            canonical="status",
            aliases=[],
            display="Status",
            description="Статус порта (online, offline)",
        ),
        "vendor": FieldDefinition(
            canonical="vendor",
            aliases=["VENDOR"],
            display="Vendor",
            description="Производитель (OUI lookup)",
        ),
        # Общие поля
        "hostname": FieldDefinition(
            canonical="hostname",
            aliases=[],
            display="Device",
            description="Hostname устройства",
        ),
        "device_ip": FieldDefinition(
            canonical="device_ip",
            aliases=[],
            display="Device IP",
            description="IP устройства",
        ),
        "description": FieldDefinition(
            canonical="description",
            aliases=[],
            display="Description",
            description="Описание интерфейса (добавляется при обогащении)",
        ),
    },

    # -------------------------------------------------------------------------
    # Интерфейсы
    # -------------------------------------------------------------------------
    "interfaces": {
        "name": FieldDefinition(
            canonical="name",
            aliases=["INTERFACE", "interface", "PORT", "port", "INTF", "intf"],
            display="Interface",
            netbox_field="name",
            description="Имя интерфейса",
        ),
        "status": FieldDefinition(
            canonical="status",
            aliases=["LINK_STATUS", "link_status", "STATUS"],
            display="Status",
            netbox_field="enabled",  # up → true
            description="Статус интерфейса (up, down, disabled)",
        ),
        "description": FieldDefinition(
            canonical="description",
            aliases=["DESCRIPTION", "DESC", "desc"],
            display="Description",
            netbox_field="description",
            description="Описание интерфейса",
        ),
        "ip_address": FieldDefinition(
            canonical="ip_address",
            aliases=["IP_ADDRESS", "IP", "ip", "ADDRESS", "address"],
            display="IP Address",
            description="IP-адрес интерфейса",
        ),
        "mac": FieldDefinition(
            canonical="mac",
            aliases=[
                "MAC_ADDRESS", "mac_address", "ADDRESS", "BIA", "bia",
                "HARDWARE_ADDRESS", "hardware_address",
            ],
            display="MAC",
            netbox_field="mac_address",
            description="MAC-адрес интерфейса",
        ),
        "speed": FieldDefinition(
            canonical="speed",
            aliases=["SPEED", "BANDWIDTH", "bandwidth", "BW", "bw"],
            display="Speed",
            netbox_field="speed",
            description="Скорость интерфейса",
        ),
        "duplex": FieldDefinition(
            canonical="duplex",
            aliases=["DUPLEX"],
            display="Duplex",
            netbox_field="duplex",
            description="Дуплекс (full, half, auto)",
        ),
        "mtu": FieldDefinition(
            canonical="mtu",
            aliases=["MTU"],
            display="MTU",
            netbox_field="mtu",
            description="MTU",
        ),
        "mode": FieldDefinition(
            canonical="mode",
            aliases=["MODE", "SWITCHPORT_MODE", "switchport_mode"],
            display="Mode",
            netbox_field="mode",
            description="Режим switchport (access, tagged, tagged-all)",
        ),
        "port_type": FieldDefinition(
            canonical="port_type",
            aliases=[],
            display="Port Type",
            netbox_field="type",  # Конвертируется в NetBox type
            description="Тип порта (1g-rj45, 10g-sfp+, lag, virtual)",
        ),
        "media_type": FieldDefinition(
            canonical="media_type",
            aliases=["MEDIA_TYPE", "MEDIA", "media"],
            display="Media Type",
            description="Тип трансивера (SFP-10GBase-LR)",
        ),
        "hardware_type": FieldDefinition(
            canonical="hardware_type",
            aliases=["HARDWARE_TYPE", "HARDWARE", "hardware"],
            display="Hardware Type",
            description="Тип оборудования (Gigabit Ethernet)",
        ),
        "vlan": FieldDefinition(
            canonical="vlan",
            aliases=["VLAN", "ACCESS_VLAN", "access_vlan"],
            display="VLAN",
            description="VLAN ID (для access портов)",
        ),
        "native_vlan": FieldDefinition(
            canonical="native_vlan",
            aliases=["NATIVE_VLAN"],
            display="Native VLAN",
            netbox_field="untagged_vlan",
            description="Native VLAN (для trunk портов)",
        ),
        "tagged_vlans": FieldDefinition(
            canonical="tagged_vlans",
            aliases=["TAGGED_VLANS"],
            display="Tagged VLANs",
            netbox_field="tagged_vlans",
            description="Список tagged VLAN (для trunk портов)",
        ),
        "access_vlan": FieldDefinition(
            canonical="access_vlan",
            aliases=["ACCESS_VLAN"],
            display="Access VLAN",
            description="Access VLAN (для access портов)",
        ),
        "lag": FieldDefinition(
            canonical="lag",
            aliases=["LAG", "PORT_CHANNEL", "port_channel"],
            display="LAG",
            netbox_field="lag",
            description="Имя LAG интерфейса (если member)",
        ),
        # Общие поля
        "hostname": FieldDefinition(
            canonical="hostname",
            aliases=[],
            display="Device",
            description="Hostname устройства",
        ),
        "device_ip": FieldDefinition(
            canonical="device_ip",
            aliases=[],
            display="Device IP",
            description="IP устройства",
        ),
    },

    # -------------------------------------------------------------------------
    # Устройства (devices)
    # -------------------------------------------------------------------------
    "devices": {
        "hostname": FieldDefinition(
            canonical="hostname",
            aliases=["HOSTNAME", "NAME", "name", "DEVICE_NAME", "device_name"],
            display="Hostname",
            netbox_field="name",
            description="Hostname устройства",
        ),
        "ip_address": FieldDefinition(
            canonical="ip_address",
            aliases=["IP_ADDRESS", "IP", "ip", "HOST", "host", "MGMT_IP", "mgmt_ip"],
            display="IP Address",
            description="Management IP",
        ),
        "model": FieldDefinition(
            canonical="model",
            aliases=["MODEL", "HARDWARE", "hardware", "PLATFORM", "platform"],
            display="Model",
            netbox_field="device_type",
            description="Модель устройства",
        ),
        "serial": FieldDefinition(
            canonical="serial",
            aliases=["SERIAL", "SERIAL_NUMBER", "serial_number", "SN", "sn"],
            display="Serial",
            netbox_field="serial",
            description="Серийный номер",
        ),
        "version": FieldDefinition(
            canonical="version",
            aliases=["VERSION", "SOFTWARE_VERSION", "software_version", "OS_VERSION", "os_version"],
            display="Version",
            description="Версия ПО",
        ),
        "uptime": FieldDefinition(
            canonical="uptime",
            aliases=["UPTIME"],
            display="Uptime",
            description="Время работы",
        ),
        "manufacturer": FieldDefinition(
            canonical="manufacturer",
            aliases=["MANUFACTURER", "VENDOR", "vendor"],
            display="Manufacturer",
            netbox_field="manufacturer",
            description="Производитель",
        ),
        "platform": FieldDefinition(
            canonical="platform",
            aliases=["PLATFORM_TYPE", "platform_type"],
            display="Platform",
            netbox_field="platform",
            description="Платформа (cisco_ios, arista_eos)",
        ),
        "role": FieldDefinition(
            canonical="role",
            aliases=["ROLE", "DEVICE_ROLE", "device_role"],
            display="Role",
            netbox_field="role",
            description="Роль устройства (switch, router)",
        ),
        "site": FieldDefinition(
            canonical="site",
            aliases=["SITE", "LOCATION", "location"],
            display="Site",
            netbox_field="site",
            description="Сайт",
        ),
        "tenant": FieldDefinition(
            canonical="tenant",
            aliases=["TENANT"],
            display="Tenant",
            netbox_field="tenant",
            description="Арендатор",
        ),
        "status": FieldDefinition(
            canonical="status",
            aliases=["STATUS"],
            display="Status",
            netbox_field="status",
            description="Статус (active, planned, offline)",
        ),
        # asset_tag и comments — NetBox-only поля, не парсятся с устройств
        # Определены в SYNC_ONLY_FIELDS, не в модели DeviceInfo
    },

    # -------------------------------------------------------------------------
    # Inventory (модули, SFP, PSU)
    # -------------------------------------------------------------------------
    "inventory": {
        "name": FieldDefinition(
            canonical="name",
            aliases=["NAME", "COMPONENT", "component"],
            display="Component",
            netbox_field="name",
            description="Имя компонента",
        ),
        "pid": FieldDefinition(
            canonical="pid",
            aliases=["PID", "PART_ID", "part_id", "PRODUCT_ID", "product_id"],
            display="Part ID",
            netbox_field="part_id",
            description="Product ID (модель)",
        ),
        "serial": FieldDefinition(
            canonical="serial",
            aliases=["SERIAL", "SERIAL_NUMBER", "serial_number", "SN", "sn"],
            display="Serial",
            netbox_field="serial",
            description="Серийный номер",
        ),
        "vid": FieldDefinition(
            canonical="vid",
            aliases=["VID", "VERSION_ID", "version_id"],
            display="Version",
            description="Version ID",
        ),
        "description": FieldDefinition(
            canonical="description",
            aliases=["DESCRIPTION", "DESCR", "descr"],
            display="Description",
            netbox_field="description",
            description="Описание",
        ),
        "manufacturer": FieldDefinition(
            canonical="manufacturer",
            aliases=["MANUFACTURER", "VENDOR", "vendor"],
            display="Manufacturer",
            netbox_field="manufacturer",
            description="Производитель",
        ),
        # Общие поля
        "hostname": FieldDefinition(
            canonical="hostname",
            aliases=[],
            display="Device",
            description="Hostname устройства",
        ),
        "device_ip": FieldDefinition(
            canonical="device_ip",
            aliases=[],
            display="Device IP",
            description="IP устройства",
        ),
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_canonical_name(data_type: str, field_name: str) -> str:
    """
    Возвращает каноническое имя для любого алиаса.

    Args:
        data_type: Тип данных (lldp, mac, interfaces, devices, inventory)
        field_name: Имя поля (может быть каноническим или алиасом)

    Returns:
        str: Каноническое имя или исходное если не найдено

    Example:
        get_canonical_name("lldp", "NEIGHBOR_NAME")  # → "remote_hostname"
        get_canonical_name("mac", "destination_port")  # → "interface"
    """
    registry = FIELD_REGISTRY.get(data_type, {})

    # Прямое совпадение с каноническим именем
    if field_name in registry:
        return field_name

    # Поиск по алиасам (case-insensitive)
    field_lower = field_name.lower()
    for canonical, defn in registry.items():
        if field_lower == canonical.lower():
            return canonical
        for alias in defn.aliases:
            if field_lower == alias.lower():
                return canonical

    return field_name  # Не найдено — возвращаем как есть


def get_all_aliases(data_type: str, canonical: str) -> Set[str]:
    """
    Возвращает все имена для канонического поля.

    Args:
        data_type: Тип данных
        canonical: Каноническое имя поля

    Returns:
        Set[str]: Множество всех имён (canonical + aliases)
    """
    registry = FIELD_REGISTRY.get(data_type, {})
    if canonical in registry:
        return registry[canonical].all_names()
    return {canonical}


def get_field_definition(data_type: str, field_name: str) -> Optional[FieldDefinition]:
    """
    Возвращает определение поля.

    Args:
        data_type: Тип данных
        field_name: Имя поля (каноническое или алиас)

    Returns:
        FieldDefinition или None
    """
    canonical = get_canonical_name(data_type, field_name)
    registry = FIELD_REGISTRY.get(data_type, {})
    return registry.get(canonical)


def get_netbox_field(data_type: str, canonical: str) -> str:
    """
    Возвращает имя поля в NetBox API.

    Args:
        data_type: Тип данных
        canonical: Каноническое имя поля

    Returns:
        str: Имя поля в NetBox или canonical если не задано
    """
    defn = get_field_definition(data_type, canonical)
    if defn and defn.netbox_field:
        return defn.netbox_field
    return canonical


def get_display_name(data_type: str, field_name: str) -> str:
    """
    Возвращает display name для поля.

    Args:
        data_type: Тип данных
        field_name: Имя поля

    Returns:
        str: Display name
    """
    defn = get_field_definition(data_type, field_name)
    if defn:
        return defn.display
    return field_name.replace("_", " ").title()


# =============================================================================
# МАППИНГ ДЛЯ EXPORT (fields.yaml → Model)
# =============================================================================
# Поля в fields.yaml могут отличаться от канонических имён в моделях
# Этот маппинг используется для валидации

EXPORT_FIELD_MAPPING: Dict[str, Dict[str, str]] = {
    "mac": {
        "type": "mac_type",  # fields.yaml:type → Model:mac_type
    },
    "interfaces": {
        "interface": "name",  # fields.yaml:interface → Model:name
    },
}

# Поля которые добавляются при экспорте/нормализации (не в модели)
EXPORT_ONLY_FIELDS: Dict[str, Set[str]] = {
    "mac": {"description", "status"},  # status добавляется MACNormalizer
    "lldp": set(),
    "interfaces": {"protocol"},  # link protocol не хранится в Interface
    "devices": set(),
    "inventory": set(),
}

# Поля которые используются ТОЛЬКО в sync конфиге (не парсятся с устройств)
# Это NetBox-specific поля которые заполняются вручную или из внешних источников
SYNC_ONLY_FIELDS: Dict[str, Set[str]] = {
    "devices": {"asset_tag", "comments"},  # NetBox-only, не парсятся
    "interfaces": set(),
    "inventory": set(),
}


# =============================================================================
# VALIDATION
# =============================================================================

def validate_fields_config() -> List[str]:
    """
    Валидирует fields.yaml против моделей и реестра.

    Проверяет:
    - Все enabled поля существуют в моделях
    - Sync source поля существуют в моделях
    - Предупреждает о неизвестных полях

    Returns:
        List[str]: Список ошибок и предупреждений
    """
    from dataclasses import fields as dataclass_fields
    from .models import Interface, MACEntry, LLDPNeighbor, InventoryItem, DeviceInfo

    MODELS = {
        "lldp": LLDPNeighbor,
        "mac": MACEntry,
        "devices": DeviceInfo,
        "interfaces": Interface,
        "inventory": InventoryItem,
    }

    errors = []

    try:
        from ..fields_config import _load_yaml
        config = _load_yaml()
    except Exception as e:
        return [f"Cannot load fields.yaml: {e}"]

    # 1. Проверяем export секции
    for section, model in MODELS.items():
        model_fields = {f.name for f in dataclass_fields(model)}
        section_config = config.get(section, {})
        field_mapping = EXPORT_FIELD_MAPPING.get(section, {})
        export_only = EXPORT_ONLY_FIELDS.get(section, set())

        for field_name, field_cfg in section_config.items():
            if not isinstance(field_cfg, dict):
                continue
            if not field_cfg.get("enabled", False):
                continue

            # Применяем маппинг
            mapped_name = field_mapping.get(field_name, field_name)
            canonical = get_canonical_name(section, mapped_name)

            # Проверяем в модели
            if canonical not in model_fields:
                if field_name not in export_only:
                    errors.append(
                        f"[{section}] Export field '{field_name}' "
                        f"(→'{canonical}') not in {model.__name__}. "
                        f"Add to EXPORT_ONLY_FIELDS or fix the name."
                    )

    # 2. Проверяем sync секцию
    sync_config = config.get("sync", {})
    for entity, entity_cfg in sync_config.items():
        if entity not in MODELS:
            continue

        model = MODELS[entity]
        model_fields = {f.name for f in dataclass_fields(model)}
        sync_only = SYNC_ONLY_FIELDS.get(entity, set())
        fields = entity_cfg.get("fields", {})

        for netbox_field, field_cfg in fields.items():
            if not isinstance(field_cfg, dict):
                continue
            if not field_cfg.get("enabled", True):
                continue

            source = field_cfg.get("source", netbox_field)

            # Пропускаем sync-only поля (NetBox-specific, не парсятся)
            if source in sync_only:
                continue
            canonical = get_canonical_name(entity, source)

            if canonical not in model_fields:
                errors.append(
                    f"[sync.{entity}] Source '{source}' for NetBox field "
                    f"'{netbox_field}' not in {model.__name__}"
                )

    return errors


def print_field_registry(data_type: Optional[str] = None):
    """
    Выводит реестр полей в читаемом формате.

    Args:
        data_type: Тип данных (если None — все типы)
    """
    types_to_print = [data_type] if data_type else FIELD_REGISTRY.keys()

    for dtype in types_to_print:
        if dtype not in FIELD_REGISTRY:
            print(f"Unknown data type: {dtype}")
            continue

        print(f"\n{'='*60}")
        print(f" {dtype.upper()}")
        print(f"{'='*60}")

        for canonical, defn in FIELD_REGISTRY[dtype].items():
            aliases_str = ", ".join(defn.aliases[:3])
            if len(defn.aliases) > 3:
                aliases_str += f", ... (+{len(defn.aliases)-3})"

            print(f"\n  {canonical}")
            print(f"    Display: {defn.display}")
            if defn.netbox_field:
                print(f"    NetBox:  {defn.netbox_field}")
            if defn.aliases:
                print(f"    Aliases: {aliases_str}")
            if defn.description:
                print(f"    Desc:    {defn.description}")
