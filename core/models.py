"""
Data Models для Network Collector.

Типизированные dataclasses вместо Dict[str, Any].
Обеспечивают:
- Автокомплит в IDE
- Валидацию типов
- Документацию полей
- Сериализацию в dict/JSON

Использование:
    from network_collector.core.models import Interface, MACEntry

    # Создание из dict (например, от парсера)
    intf = Interface.from_dict(parsed_data)

    # Доступ к полям с автокомплитом
    print(intf.name, intf.ip_address, intf.status)

    # Сериализация обратно в dict
    data = intf.to_dict()
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Any, Dict, Union
from enum import Enum

from .constants import mask_to_prefix


class InterfaceStatus(str, Enum):
    """Статус интерфейса."""
    UP = "up"
    DOWN = "down"
    ADMIN_DOWN = "administratively down"
    UNKNOWN = "unknown"


class SwitchportMode(str, Enum):
    """Режим switchport (802.1Q)."""
    ACCESS = "access"
    TAGGED = "tagged"
    TAGGED_ALL = "tagged-all"


class NeighborType(str, Enum):
    """Тип идентификации соседа LLDP/CDP."""
    HOSTNAME = "hostname"
    MAC = "mac"
    IP = "ip"
    UNKNOWN = "unknown"


@dataclass
class Interface:
    """
    Данные интерфейса устройства.

    Attributes:
        name: Имя интерфейса (GigabitEthernet0/1)
        description: Описание интерфейса
        status: Статус (up/down)
        ip_address: IP-адрес (если есть)
        mac: MAC-адрес интерфейса
        speed: Скорость (1 Gbit, 10 Gbit)
        duplex: Дуплекс (full, half, auto)
        mtu: MTU
        vlan: VLAN ID (для access портов)
        mode: Режим switchport (access, tagged, tagged-all)
        port_type: Тип порта (1g-rj45, 10g-sfp+, lag, virtual)
        media_type: Тип трансивера (SFP-10GBase-LR)
        hardware_type: Hardware тип (Gigabit Ethernet)
        lag: Имя LAG интерфейса (если member)
        hostname: Hostname устройства
        device_ip: IP устройства
    """
    name: str
    description: str = ""
    status: str = "unknown"
    ip_address: str = ""
    mac: str = ""
    speed: str = ""
    duplex: str = ""
    mtu: Optional[int] = None
    vlan: str = ""
    mode: str = ""
    port_type: str = ""
    media_type: str = ""
    hardware_type: str = ""
    lag: str = ""
    hostname: str = ""
    device_ip: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Interface":
        """Создаёт Interface из словаря."""
        return cls(
            name=data.get("interface") or data.get("name") or "",
            description=data.get("description") or "",
            status=data.get("status") or data.get("link_status") or "unknown",
            ip_address=data.get("ip_address") or "",
            mac=data.get("mac") or data.get("mac_address") or "",
            speed=data.get("speed") or data.get("bandwidth") or "",
            duplex=data.get("duplex") or "",
            mtu=int(data["mtu"]) if data.get("mtu") else None,
            vlan=str(data.get("vlan") or data.get("access_vlan") or ""),
            mode=data.get("mode") or "",
            port_type=data.get("port_type") or "",
            media_type=data.get("media_type") or "",
            hardware_type=data.get("hardware_type") or "",
            lag=data.get("lag") or "",
            hostname=data.get("hostname") or "",
            device_ip=data.get("device_ip") or "",
        )

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}

    @classmethod
    def ensure_list(cls, data: Union[List[Dict[str, Any]], List["Interface"]]) -> List["Interface"]:
        """Конвертирует List[Dict] в List[Interface] если нужно."""
        if not data:
            return []
        if isinstance(data[0], dict):
            return [cls.from_dict(d) for d in data]
        return data


@dataclass
class MACEntry:
    """
    Запись MAC-адреса.

    Attributes:
        mac: MAC-адрес
        interface: Интерфейс
        vlan: VLAN ID
        mac_type: Тип (dynamic, static, sticky)
        hostname: Hostname устройства
        device_ip: IP устройства
        vendor: Производитель (OUI lookup)
    """
    mac: str
    interface: str
    vlan: str = ""
    mac_type: str = "dynamic"
    hostname: str = ""
    device_ip: str = ""
    vendor: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MACEntry":
        """Создаёт MACEntry из словаря."""
        return cls(
            mac=data.get("mac", data.get("destination_address", "")),
            interface=data.get("interface", data.get("destination_port", "")),
            vlan=str(data.get("vlan", "")),
            mac_type=data.get("type", data.get("mac_type", "dynamic")),
            hostname=data.get("hostname", ""),
            device_ip=data.get("device_ip", ""),
            vendor=data.get("vendor", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return asdict(self)

    @classmethod
    def ensure_list(cls, data: Union[List[Dict[str, Any]], List["MACEntry"]]) -> List["MACEntry"]:
        """Конвертирует List[Dict] в List[MACEntry] если нужно."""
        if not data:
            return []
        if isinstance(data[0], dict):
            return [cls.from_dict(d) for d in data]
        return data


@dataclass
class LLDPNeighbor:
    """
    Сосед LLDP/CDP.

    Attributes:
        local_interface: Локальный интерфейс
        remote_hostname: Имя соседа
        remote_port: Порт соседа
        remote_mac: MAC соседа (chassis_id)
        remote_ip: Management IP соседа
        neighbor_type: Тип идентификации (hostname, mac, ip)
        protocol: Протокол (lldp, cdp)
        hostname: Hostname локального устройства
        device_ip: IP локального устройства
        capabilities: Capabilities соседа (Router, Switch)
        platform: Платформа соседа
    """
    local_interface: str
    remote_hostname: str = ""
    remote_port: str = ""
    remote_mac: str = ""
    remote_ip: str = ""
    neighbor_type: str = "unknown"
    protocol: str = "lldp"
    hostname: str = ""
    device_ip: str = ""
    capabilities: str = ""
    platform: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLDPNeighbor":
        """Создаёт LLDPNeighbor из словаря."""
        return cls(
            local_interface=data.get("local_interface", data.get("local_port", "")),
            remote_hostname=data.get("remote_hostname", data.get("neighbor", "")),
            remote_port=data.get("remote_port", data.get("neighbor_port", "")),
            remote_mac=data.get("remote_mac", data.get("chassis_id", "")),
            remote_ip=data.get("remote_ip", data.get("management_ip", "")),
            neighbor_type=data.get("neighbor_type", "unknown"),
            protocol=data.get("protocol", "lldp"),
            hostname=data.get("hostname", ""),
            device_ip=data.get("device_ip", ""),
            capabilities=data.get("capabilities", data.get("capability", "")),
            platform=data.get("platform", data.get("neighbor_platform", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return asdict(self)

    @classmethod
    def ensure_list(cls, data: Union[List[Dict[str, Any]], List["LLDPNeighbor"]]) -> List["LLDPNeighbor"]:
        """Конвертирует List[Dict] в List[LLDPNeighbor] если нужно."""
        if not data:
            return []
        if isinstance(data[0], dict):
            return [cls.from_dict(d) for d in data]
        return data


@dataclass
class InventoryItem:
    """
    Элемент инвентаризации (модуль, SFP, PSU).

    Attributes:
        name: Имя компонента
        pid: Product ID (модель)
        serial: Серийный номер
        description: Описание
        vid: Version ID
        manufacturer: Производитель
        hostname: Hostname устройства
        device_ip: IP устройства
    """
    name: str
    pid: str = ""
    serial: str = ""
    description: str = ""
    vid: str = ""
    manufacturer: str = ""
    hostname: str = ""
    device_ip: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InventoryItem":
        """Создаёт InventoryItem из словаря."""
        return cls(
            name=data.get("name", ""),
            pid=data.get("pid", data.get("part_id", "")),
            serial=data.get("serial", data.get("sn", "")),
            description=data.get("description", data.get("descr", "")),
            vid=data.get("vid", ""),
            manufacturer=data.get("manufacturer", ""),
            hostname=data.get("hostname", ""),
            device_ip=data.get("device_ip", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return {k: v for k, v in asdict(self).items() if v}

    @classmethod
    def ensure_list(cls, data: Union[List[Dict[str, Any]], List["InventoryItem"]]) -> List["InventoryItem"]:
        """Конвертирует List[Dict] в List[InventoryItem] если нужно."""
        if not data:
            return []
        if isinstance(data[0], dict):
            return [cls.from_dict(d) for d in data]
        return data


@dataclass
class IPAddressEntry:
    """
    IP-адрес на интерфейсе.

    Attributes:
        ip_address: IP-адрес (с маской или без)
        interface: Имя интерфейса
        mask: Маска сети (255.255.255.0 или 24)
        hostname: Hostname устройства
        device_ip: IP устройства
    """
    ip_address: str
    interface: str
    mask: str = ""
    hostname: str = ""
    device_ip: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IPAddressEntry":
        """Создаёт IPAddressEntry из словаря."""
        return cls(
            ip_address=data.get("ip_address", ""),
            interface=data.get("interface", ""),
            mask=data.get("mask", data.get("prefix_length", "")),
            hostname=data.get("hostname", ""),
            device_ip=data.get("device_ip", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return asdict(self)

    @property
    def with_prefix(self) -> str:
        """Возвращает IP с префиксом (10.0.0.1/24)."""
        if "/" in self.ip_address:
            return self.ip_address
        if self.mask:
            return f"{self.ip_address}/{mask_to_prefix(self.mask)}"
        return f"{self.ip_address}/32"

    @classmethod
    def ensure_list(cls, data: Union[List[Dict[str, Any]], List["IPAddressEntry"]]) -> List["IPAddressEntry"]:
        """Конвертирует List[Dict] в List[IPAddressEntry] если нужно."""
        if not data:
            return []
        if isinstance(data[0], dict):
            return [cls.from_dict(d) for d in data]
        return data


@dataclass
class DeviceInfo:
    """
    Информация об устройстве.

    Attributes:
        hostname: Hostname
        ip_address: IP-адрес (management)
        platform: Платформа (cisco_ios, arista_eos)
        model: Модель устройства
        serial: Серийный номер
        version: Версия ПО
        uptime: Время работы
        manufacturer: Производитель
        role: Роль (switch, router)
    """
    hostname: str
    ip_address: str = ""
    platform: str = ""
    model: str = ""
    serial: str = ""
    version: str = ""
    uptime: str = ""
    manufacturer: str = ""
    role: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceInfo":
        """Создаёт DeviceInfo из словаря."""
        return cls(
            hostname=data.get("hostname", data.get("name", "")),
            ip_address=data.get("ip_address", data.get("host", "")),
            platform=data.get("platform", ""),
            model=data.get("model", data.get("hardware", "")),
            serial=data.get("serial", data.get("serial_number", "")),
            version=data.get("version", data.get("software_version", "")),
            uptime=data.get("uptime", ""),
            manufacturer=data.get("manufacturer", data.get("vendor", "")),
            role=data.get("role", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует в словарь."""
        return {k: v for k, v in asdict(self).items() if v}

    @classmethod
    def ensure_list(cls, data: Union[List[Dict[str, Any]], List["DeviceInfo"]]) -> List["DeviceInfo"]:
        """Конвертирует List[Dict] в List[DeviceInfo] если нужно."""
        if not data:
            return []
        if isinstance(data[0], dict):
            return [cls.from_dict(d) for d in data]
        return data


# Type aliases для коллекций
Interfaces = List[Interface]
MACTable = List[MACEntry]
Neighbors = List[LLDPNeighbor]
Inventory = List[InventoryItem]
IPAddresses = List[IPAddressEntry]


def interfaces_from_dicts(data: List[Dict[str, Any]]) -> Interfaces:
    """Конвертирует список словарей в список Interface."""
    return [Interface.from_dict(d) for d in data]


def interfaces_to_dicts(interfaces: Interfaces) -> List[Dict[str, Any]]:
    """Конвертирует список Interface в список словарей."""
    return [i.to_dict() for i in interfaces]


def mac_entries_from_dicts(data: List[Dict[str, Any]]) -> MACTable:
    """Конвертирует список словарей в список MACEntry."""
    return [MACEntry.from_dict(d) for d in data]


def mac_entries_to_dicts(entries: MACTable) -> List[Dict[str, Any]]:
    """Конвертирует список MACEntry в список словарей."""
    return [e.to_dict() for e in entries]


def neighbors_from_dicts(data: List[Dict[str, Any]]) -> Neighbors:
    """Конвертирует список словарей в список LLDPNeighbor."""
    return [LLDPNeighbor.from_dict(d) for d in data]


def neighbors_to_dicts(neighbors: Neighbors) -> List[Dict[str, Any]]:
    """Конвертирует список LLDPNeighbor в список словарей."""
    return [n.to_dict() for n in neighbors]


def inventory_from_dicts(data: List[Dict[str, Any]]) -> Inventory:
    """Конвертирует список словарей в список InventoryItem."""
    return [InventoryItem.from_dict(d) for d in data]


def inventory_to_dicts(items: Inventory) -> List[Dict[str, Any]]:
    """Конвертирует список InventoryItem в список словарей."""
    return [i.to_dict() for i in items]


# Type aliases для IP и Device
IPAddresses = List[IPAddressEntry]
Devices = List[DeviceInfo]


def ip_addresses_from_dicts(data: List[Dict[str, Any]]) -> IPAddresses:
    """Конвертирует список словарей в список IPAddressEntry."""
    return [IPAddressEntry.from_dict(d) for d in data]


def ip_addresses_to_dicts(addresses: IPAddresses) -> List[Dict[str, Any]]:
    """Конвертирует список IPAddressEntry в список словарей."""
    return [a.to_dict() for a in addresses]


def devices_from_dicts(data: List[Dict[str, Any]]) -> Devices:
    """Конвертирует список словарей в список DeviceInfo."""
    return [DeviceInfo.from_dict(d) for d in data]


def devices_to_dicts(devices: Devices) -> List[Dict[str, Any]]:
    """Конвертирует список DeviceInfo в список словарей."""
    return [d.to_dict() for d in devices]
