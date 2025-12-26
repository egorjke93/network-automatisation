"""
Core модули Network Collector.

Содержит базовые классы для работы с устройствами:
- Device: Представление сетевого устройства
- ConnectionManager: Управление SSH подключениями через Scrapli
- CredentialsManager: Безопасное управление учётными данными
- RunContext: Контекст выполнения для отслеживания запусков
- Structured Logging: JSON/Human-readable логирование
- constants: Константы и маппинги
"""

from .device import Device, DeviceStatus
from .connection import ConnectionManager
from .credentials import CredentialsManager, Credentials
from .context import (
    RunContext,
    get_current_context,
    set_current_context,
    RunContextFilter,
    setup_logging_with_context,
)
from .logging import (
    get_logger,
    setup_json_logging,
    setup_human_logging,
    setup_logging,
    setup_file_logging,
    setup_logging_from_config,
    StructuredLogger,
    JSONFormatter,
    HumanFormatter,
    LogContext,
    OperationLog,
    LogLevel,
    LogConfig,
    RotationType,
)
from .exceptions import (
    NetworkCollectorError,
    CollectorError,
    ConnectionError,
    AuthenticationError,
    CommandError,
    ParseError,
    TimeoutError,
    NetBoxError,
    NetBoxConnectionError,
    NetBoxAPIError,
    NetBoxValidationError,
    ConfigError,
    format_error_for_log,
    is_retryable,
)
from .models import (
    Interface,
    MACEntry,
    LLDPNeighbor,
    InventoryItem,
    IPAddressEntry,
    DeviceInfo,
    InterfaceStatus,
    SwitchportMode,
    NeighborType,
    Interfaces,
    MACTable,
    Neighbors,
    Inventory,
    IPAddresses,
    interfaces_from_dicts,
    interfaces_to_dicts,
    mac_entries_from_dicts,
    mac_entries_to_dicts,
    neighbors_from_dicts,
    neighbors_to_dicts,
    inventory_from_dicts,
    inventory_to_dicts,
)

__all__ = [
    # Device & Connection
    "Device",
    "DeviceStatus",
    "ConnectionManager",
    "CredentialsManager",
    "Credentials",
    # Context
    "RunContext",
    "get_current_context",
    "set_current_context",
    "RunContextFilter",
    "setup_logging_with_context",
    # Structured Logging
    "get_logger",
    "setup_json_logging",
    "setup_human_logging",
    "setup_logging",
    "setup_file_logging",
    "setup_logging_from_config",
    "StructuredLogger",
    "JSONFormatter",
    "HumanFormatter",
    "LogContext",
    "OperationLog",
    "LogLevel",
    "LogConfig",
    "RotationType",
    # Exceptions
    "NetworkCollectorError",
    "CollectorError",
    "ConnectionError",
    "AuthenticationError",
    "CommandError",
    "ParseError",
    "TimeoutError",
    "NetBoxError",
    "NetBoxConnectionError",
    "NetBoxAPIError",
    "NetBoxValidationError",
    "ConfigError",
    "format_error_for_log",
    "is_retryable",
    # Data Models
    "Interface",
    "MACEntry",
    "LLDPNeighbor",
    "InventoryItem",
    "IPAddressEntry",
    "DeviceInfo",
    "InterfaceStatus",
    "SwitchportMode",
    "NeighborType",
    "Interfaces",
    "MACTable",
    "Neighbors",
    "Inventory",
    "IPAddresses",
    "interfaces_from_dicts",
    "interfaces_to_dicts",
    "mac_entries_from_dicts",
    "mac_entries_to_dicts",
    "neighbors_from_dicts",
    "neighbors_to_dicts",
    "inventory_from_dicts",
    "inventory_to_dicts",
]

