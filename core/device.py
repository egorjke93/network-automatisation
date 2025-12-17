"""
Модуль представления сетевого устройства.

Класс Device инкапсулирует всю информацию об устройстве:
- Параметры подключения (IP, тип, порт)
- Метаданные (hostname, vendor, model)
- Состояние (online/offline, ошибки)

Пример использования:
    device = Device(
        host="192.168.1.1",
        device_type="cisco_ios",
    )
    device.hostname = "SW-CORE-01"
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

from .constants import get_vendor_by_device_type

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    """Статус устройства."""
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass
class Device:
    """
    Представление сетевого устройства.
    
    Attributes:
        host: IP-адрес или hostname устройства
        device_type: Тип устройства для Netmiko (cisco_ios, arista_eos, etc.)
        port: SSH порт (по умолчанию 22)
        hostname: Имя устройства (определяется после подключения)
        vendor: Вендор (определяется по device_type)
        model: Модель устройства
        serial: Серийный номер
        status: Текущий статус устройства
        last_error: Последняя ошибка
        
    Example:
        device = Device(host="10.0.0.1", device_type="cisco_ios")
        print(device.vendor)  # "cisco"
    """
    
    # Обязательные параметры
    host: str
    device_type: str
    
    # Опциональные параметры подключения
    port: int = 22
    timeout: int = 10
    
    # Метаданные (заполняются после подключения)
    hostname: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    version: Optional[str] = None
    
    # Состояние
    status: DeviceStatus = DeviceStatus.UNKNOWN
    last_error: Optional[str] = None
    
    # Дополнительные данные
    tags: List[str] = field(default_factory=list)
    custom_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Автоматически определяет vendor по device_type."""
        if not self.vendor:
            self.vendor = self._detect_vendor()
    
    def _detect_vendor(self) -> str:
        """
        Определяет вендора по типу устройства.

        Returns:
            str: Название вендора
        """
        return get_vendor_by_device_type(self.device_type)
    
    def to_netmiko_params(self, credentials: dict) -> dict:
        """
        Формирует параметры для Netmiko.
        
        Args:
            credentials: Словарь с username, password, secret
            
        Returns:
            dict: Параметры для ConnectHandler
        """
        params = {
            "device_type": self.device_type,
            "host": self.host,
            "port": self.port,
            "timeout": self.timeout,
            **credentials,
        }
        return params
    
    @property
    def display_name(self) -> str:
        """Возвращает отображаемое имя устройства."""
        return self.hostname or self.host
    
    def __str__(self) -> str:
        """Строковое представление."""
        status_icon = {
            DeviceStatus.ONLINE: "🟢",
            DeviceStatus.OFFLINE: "🔴",
            DeviceStatus.ERROR: "⚠️",
            DeviceStatus.UNKNOWN: "⚪",
        }
        icon = status_icon.get(self.status, "⚪")
        return f"{icon} {self.display_name} ({self.host})"
    
    @classmethod
    def from_dict(cls, data: dict) -> "Device":
        """
        Создаёт Device из словаря.
        
        Args:
            data: Словарь с параметрами устройства
            
        Returns:
            Device: Экземпляр устройства
        """
        return cls(
            host=data.get("host", data.get("ip", "")),
            device_type=data.get("device_type", "cisco_ios"),
            port=data.get("port", 22),
            hostname=data.get("hostname"),
            tags=data.get("tags", []),
        )

