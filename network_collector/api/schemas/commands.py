"""Schemas для всех команд Network Collector."""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class ExportFormat(str, Enum):
    """Формат экспорта."""
    EXCEL = "excel"
    CSV = "csv"
    JSON = "json"


class Protocol(str, Enum):
    """Протокол для LLDP/CDP."""
    LLDP = "lldp"
    CDP = "cdp"
    BOTH = "both"


# =============================================================================
# Devices (show version)
# =============================================================================

class DevicesRequest(BaseModel):
    """Запрос на сбор информации об устройствах."""

    devices: Optional[List[str]] = Field(
        None, description="Список IP/hostname устройств. Если пусто - из devices_ips.py"
    )
    format: ExportFormat = Field(ExportFormat.JSON, description="Формат вывода")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "devices": ["10.0.0.1", "10.0.0.2"],
                "format": "json",
            }
        }
    )


class DeviceInfo(BaseModel):
    """Информация об устройстве."""

    hostname: str
    ip_address: str
    platform: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    version: Optional[str] = None
    uptime: Optional[str] = None


class DevicesResponse(BaseModel):
    """Ответ со списком устройств."""

    success: bool
    devices: List[DeviceInfo]
    errors: List[str] = []


# =============================================================================
# MAC Address Table
# =============================================================================

class MACRequest(BaseModel):
    """Запрос на сбор MAC-адресов."""

    devices: Optional[List[str]] = None
    format: ExportFormat = Field(ExportFormat.JSON)
    exclude_vlans: Optional[List[int]] = Field(None, description="Исключить VLAN")
    exclude_interfaces: Optional[List[str]] = Field(None, description="Исключить интерфейсы (regex)")


class MACEntry(BaseModel):
    """Запись MAC-адреса."""

    mac: str
    interface: str
    vlan: str
    hostname: str
    device_ip: str
    type: Optional[str] = None


class MACResponse(BaseModel):
    """Ответ со списком MAC-адресов."""

    success: bool
    entries: List[MACEntry]
    total: int
    errors: List[str] = []


# =============================================================================
# LLDP/CDP Neighbors
# =============================================================================

class LLDPRequest(BaseModel):
    """Запрос на сбор LLDP/CDP соседей."""

    devices: Optional[List[str]] = None
    protocol: Protocol = Field(Protocol.BOTH, description="lldp, cdp или both")
    format: ExportFormat = Field(ExportFormat.JSON)


class LLDPNeighborInfo(BaseModel):
    """Информация о соседе."""

    hostname: str
    device_ip: str
    local_interface: str
    remote_hostname: str
    remote_port: Optional[str] = None
    remote_ip: Optional[str] = None
    remote_mac: Optional[str] = None
    remote_platform: Optional[str] = None
    protocol: str


class LLDPResponse(BaseModel):
    """Ответ со списком соседей."""

    success: bool
    neighbors: List[LLDPNeighborInfo]
    total: int
    errors: List[str] = []


# =============================================================================
# Interfaces
# =============================================================================

class InterfacesRequest(BaseModel):
    """Запрос на сбор интерфейсов."""

    devices: Optional[List[str]] = None
    format: ExportFormat = Field(ExportFormat.JSON)


class InterfaceInfo(BaseModel):
    """Информация об интерфейсе."""

    name: str
    description: Optional[str] = None
    status: str
    ip_address: Optional[str] = None
    mac: Optional[str] = None
    speed: Optional[str] = None
    duplex: Optional[str] = None
    vlan: Optional[str] = None
    mode: Optional[str] = None
    hostname: str
    device_ip: str


class InterfacesResponse(BaseModel):
    """Ответ со списком интерфейсов."""

    success: bool
    interfaces: List[InterfaceInfo]
    total: int
    errors: List[str] = []


# =============================================================================
# Inventory
# =============================================================================

class InventoryRequest(BaseModel):
    """Запрос на сбор inventory."""

    devices: Optional[List[str]] = None
    format: ExportFormat = Field(ExportFormat.JSON)


class InventoryItem(BaseModel):
    """Элемент inventory."""

    name: str
    description: Optional[str] = None
    pid: Optional[str] = None
    serial: Optional[str] = None
    hostname: str
    device_ip: str


class InventoryResponse(BaseModel):
    """Ответ с inventory."""

    success: bool
    items: List[InventoryItem]
    total: int
    errors: List[str] = []


# =============================================================================
# Config Backup
# =============================================================================

class BackupRequest(BaseModel):
    """Запрос на backup конфигураций."""

    devices: Optional[List[str]] = None
    output_dir: Optional[str] = Field(None, description="Директория для сохранения")


class BackupResult(BaseModel):
    """Результат backup одного устройства."""

    hostname: str
    device_ip: str
    success: bool
    file_path: Optional[str] = None
    error: Optional[str] = None


class BackupResponse(BaseModel):
    """Ответ с результатами backup."""

    success: bool
    results: List[BackupResult]
    total_success: int
    total_failed: int


# =============================================================================
# Sync NetBox
# =============================================================================

class SyncRequest(BaseModel):
    """Запрос на синхронизацию с NetBox."""

    devices: Optional[List[str]] = None
    site: Optional[str] = Field(None, description="Site в NetBox")
    role: Optional[str] = Field(None, description="Device Role")

    # CREATE/UPDATE
    sync_all: bool = Field(False, description="Синхронизировать всё")
    create_devices: bool = Field(False, description="Создавать устройства")
    update_devices: bool = Field(False, description="Обновлять устройства")
    interfaces: bool = Field(False, description="Синхронизировать интерфейсы")
    ip_addresses: bool = Field(False, description="Синхронизировать IP")
    update_ips: bool = Field(False, description="Обновлять существующие IP")
    vlans: bool = Field(False, description="Синхронизировать VLANs")
    inventory: bool = Field(False, description="Синхронизировать inventory")
    cables: bool = Field(False, description="Создавать кабели из LLDP/CDP")
    protocol: Protocol = Field(Protocol.BOTH, description="Протокол для кабелей: lldp, cdp, both")

    # DELETE (cleanup)
    cleanup_interfaces: bool = Field(False, description="Удалить интерфейсы, которых нет на устройстве")
    cleanup_ips: bool = Field(False, description="Удалить IP, которых нет на устройстве")
    cleanup_cables: bool = Field(False, description="Удалить кабели, которых нет в LLDP/CDP")

    # Опции
    dry_run: bool = Field(True, description="Только показать изменения")
    show_diff: bool = Field(True, description="Показать diff")


class DiffEntry(BaseModel):
    """Одно изменение в diff."""

    entity_type: str  # device, interface, ip, cable
    entity_name: str
    action: str  # create, update, delete, skip
    field: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    device: Optional[str] = None


class SyncStats(BaseModel):
    """Статистика синхронизации."""

    created: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0


class SyncResponse(BaseModel):
    """Ответ синхронизации."""

    success: bool
    dry_run: bool

    # Статистика по типам
    devices: SyncStats = Field(default_factory=SyncStats)
    interfaces: SyncStats = Field(default_factory=SyncStats)
    ip_addresses: SyncStats = Field(default_factory=SyncStats)
    vlans: SyncStats = Field(default_factory=SyncStats)
    cables: SyncStats = Field(default_factory=SyncStats)
    inventory: SyncStats = Field(default_factory=SyncStats)

    # Diff для отображения
    diff: List[DiffEntry] = []

    errors: List[str] = []


# =============================================================================
# Match (MAC → Host)
# =============================================================================

class MatchRequest(BaseModel):
    """Запрос на сопоставление MAC с хостами."""

    mac_file: str = Field(..., description="Путь к файлу с MAC-адресами")
    source: Literal["glpi", "netbox", "csv"] = Field("glpi", description="Источник данных о хостах")
    glpi_url: Optional[str] = None
    glpi_token: Optional[str] = None


class MatchEntry(BaseModel):
    """Результат сопоставления."""

    mac: str
    interface: str
    vlan: str
    hostname: str
    device_ip: str
    matched_host: Optional[str] = None
    matched_ip: Optional[str] = None


class MatchResponse(BaseModel):
    """Ответ с результатами сопоставления."""

    success: bool
    entries: List[MatchEntry]
    matched: int
    unmatched: int


# =============================================================================
# Push Descriptions
# =============================================================================

class PushDescriptionsRequest(BaseModel):
    """Запрос на push описаний интерфейсов."""

    source_file: str = Field(..., description="Файл с описаниями (Excel/CSV)")
    dry_run: bool = Field(True, description="Только показать изменения")
    show_diff: bool = Field(True, description="Показать diff")


class PushResult(BaseModel):
    """Результат push для одного интерфейса."""

    device: str
    interface: str
    old_description: Optional[str] = None
    new_description: str
    success: bool
    error: Optional[str] = None


class PushDescriptionsResponse(BaseModel):
    """Ответ push описаний."""

    success: bool
    dry_run: bool
    results: List[PushResult]
    total_success: int
    total_failed: int
    total_skipped: int
