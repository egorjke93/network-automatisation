"""
Модуль представления сетевого устройства.

Класс Device инкапсулирует всю информацию об устройстве:
- Параметры подключения (IP, platform, порт)
- Метаданные (hostname, vendor, model)
- Состояние (online/offline, ошибки)

Пример использования:
    # Новый формат (рекомендуется):
    device = Device(
        host="192.168.1.1",
        platform="cisco_iosxe",
        device_type="C9200L-24P-4X",  # модель для NetBox
    )

    # Старый формат (backward compatible):
    device = Device(
        host="192.168.1.1",
        device_type="cisco_ios",  # будет использован как platform
    )
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

from .constants import get_vendor_by_platform

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
        platform: Платформа для подключения (cisco_ios, cisco_iosxe, arista_eos)
                  Используется для Scrapli, Netmiko, NTC Templates
        device_type: Модель устройства для NetBox (C9200L-24P-4X, WS-C2960X)
                     Опционально, может быть определена из show version
        port: SSH порт (по умолчанию 22)
        hostname: Имя устройства (определяется после подключения)
        vendor: Вендор (определяется по platform)
        model: Модель устройства (алиас для device_type, для совместимости)
        serial: Серийный номер
        status: Текущий статус устройства
        last_error: Последняя ошибка

    Example:
        # Новый формат с моделью:
        device = Device(
            host="10.0.0.1",
            platform="cisco_iosxe",
            device_type="C9200L-48P-4X"
        )

        # Старый формат (backward compatible):
        device = Device(host="10.0.0.1", device_type="cisco_ios")
        # platform будет установлен в "cisco_ios"
    """

    # Обязательный параметр
    host: str

    # Платформа для подключения (Scrapli/Netmiko/NTC)
    # Значения: cisco_ios, cisco_iosxe, cisco_nxos, arista_eos, juniper_junos, etc.
    platform: Optional[str] = None

    # Модель устройства для NetBox (C9200L-24P-4X, WS-C2960X-48FPS-L)
    # Если не указана, может быть определена из show version
    device_type: Optional[str] = None

    # Роль устройства для NetBox (Switch, Router, Firewall)
    role: Optional[str] = None

    # Сайт устройства для NetBox (если не указан — берётся из конфига)
    site: Optional[str] = None

    # Опциональные параметры подключения
    port: int = 22
    timeout: int = 10

    # Метаданные (заполняются после подключения)
    hostname: Optional[str] = None
    vendor: Optional[str] = None
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
        """
        Инициализация после создания.

        Обеспечивает backward compatibility:
        - Если platform не указан, но указан device_type в старом формате
          (cisco_ios, cisco_iosxe), используем его как platform
        """
        # Обрезаем пробелы из строковых полей
        if self.host:
            self.host = self.host.strip()
        if self.platform:
            self.platform = self.platform.strip()
        if self.device_type:
            self.device_type = self.device_type.strip()
        if self.role:
            self.role = self.role.strip()

        # Backward compatibility: старый формат где device_type = platform
        if not self.platform and self.device_type:
            # Проверяем, похоже ли device_type на platform (cisco_ios, etc.)
            # а не на модель (C9200L-24P-4X)
            platform_indicators = [
                "cisco_", "arista_", "juniper_", "qtech", "huawei_", "hp_"
            ]
            if any(self.device_type.lower().startswith(ind) for ind in platform_indicators):
                self.platform = self.device_type
                self.device_type = None  # Модель будет определена позже

        # Определяем vendor по platform
        if not self.vendor and self.platform:
            self.vendor = self._detect_vendor()

    def _detect_vendor(self) -> str:
        """
        Определяет вендора по платформе.

        Returns:
            str: Название вендора
        """
        return get_vendor_by_platform(self.platform)

    @property
    def model(self) -> Optional[str]:
        """Алиас для device_type (для совместимости)."""
        return self.device_type

    @model.setter
    def model(self, value: str):
        """Устанавливает device_type через алиас model."""
        self.device_type = value

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

        Поддерживает оба формата:
        - Новый: {"host": "...", "platform": "cisco_iosxe", "device_type": "C9200L"}
        - Старый: {"host": "...", "device_type": "cisco_ios"}

        Args:
            data: Словарь с параметрами устройства

        Returns:
            Device: Экземпляр устройства
        """
        return cls(
            host=data.get("host", data.get("ip", "")),
            platform=data.get("platform"),
            device_type=data.get("device_type"),
            role=data.get("role"),
            site=data.get("site"),
            port=data.get("port", 22),
            hostname=data.get("hostname"),
            tags=data.get("tags", []),
        )
