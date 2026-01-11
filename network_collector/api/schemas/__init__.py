"""Pydantic schemas для API."""

from .credentials import Credentials, NetBoxConfig, FullConfig
from .commands import (
    ExportFormat,
    Protocol,
    # Devices
    DevicesRequest,
    DeviceInfo,
    DevicesResponse,
    # MAC
    MACRequest,
    MACEntry,
    MACResponse,
    # LLDP
    LLDPRequest,
    LLDPNeighborInfo,
    LLDPResponse,
    # Interfaces
    InterfacesRequest,
    InterfaceInfo,
    InterfacesResponse,
    # Inventory
    InventoryRequest,
    InventoryItem,
    InventoryResponse,
    # Backup
    BackupRequest,
    BackupResult,
    BackupResponse,
    # Sync
    SyncRequest,
    SyncStats,
    SyncResponse,
    DiffEntry,
    # Match
    MatchRequest,
    MatchEntry,
    MatchResponse,
    # Push
    PushDescriptionsRequest,
    PushResult,
    PushDescriptionsResponse,
)
from .common import (
    TaskStatus,
    DeviceResult,
    TaskResult,
    HealthResponse,
    ErrorResponse,
)

__all__ = [
    # Credentials
    "Credentials",
    "NetBoxConfig",
    "FullConfig",
    # Enums
    "ExportFormat",
    "Protocol",
    # Devices
    "DevicesRequest",
    "DeviceInfo",
    "DevicesResponse",
    # MAC
    "MACRequest",
    "MACEntry",
    "MACResponse",
    # LLDP
    "LLDPRequest",
    "LLDPNeighborInfo",
    "LLDPResponse",
    # Interfaces
    "InterfacesRequest",
    "InterfaceInfo",
    "InterfacesResponse",
    # Inventory
    "InventoryRequest",
    "InventoryItem",
    "InventoryResponse",
    # Backup
    "BackupRequest",
    "BackupResult",
    "BackupResponse",
    # Sync
    "SyncRequest",
    "SyncStats",
    "SyncResponse",
    "DiffEntry",
    # Match
    "MatchRequest",
    "MatchEntry",
    "MatchResponse",
    # Push
    "PushDescriptionsRequest",
    "PushResult",
    "PushDescriptionsResponse",
    # Common
    "TaskStatus",
    "DeviceResult",
    "TaskResult",
    "HealthResponse",
    "ErrorResponse",
]
