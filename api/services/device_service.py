"""
Device Service - управление списком устройств.

Использует Repository pattern для абстракции хранилища.
Легко переключается между JSON файлом и базой данных.
"""

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any, Protocol
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
import uuid


# =============================================================================
# Domain Models
# =============================================================================

@dataclass
class DeviceConfig:
    """Модель устройства."""
    id: str
    host: str
    device_type: str  # Платформа для SSH (cisco_ios, cisco_nxos, etc.)
    name: Optional[str] = None
    site: Optional[str] = None  # NetBox site
    role: Optional[str] = None  # NetBox role (switch, router, firewall, etc.)
    tenant: Optional[str] = None  # NetBox tenant
    description: Optional[str] = None
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "host": self.host,
            "device_type": self.device_type,
            "name": self.name,
            "site": self.site,
            "role": self.role,
            "tenant": self.tenant,
            "description": self.description,
            "enabled": self.enabled,
            "tags": self.tags or [],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceConfig":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            host=data["host"],
            device_type=data.get("device_type", "cisco_ios"),
            name=data.get("name"),
            site=data.get("site"),
            role=data.get("role"),
            tenant=data.get("tenant"),
            description=data.get("description"),
            enabled=data.get("enabled", True),
            tags=data.get("tags", []),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# =============================================================================
# Repository Interface
# =============================================================================

class DeviceRepository(ABC):
    """Абстрактный репозиторий устройств."""

    @abstractmethod
    def get_all(self) -> List[DeviceConfig]:
        """Возвращает все устройства."""
        pass

    @abstractmethod
    def get_by_id(self, device_id: str) -> Optional[DeviceConfig]:
        """Находит устройство по ID."""
        pass

    @abstractmethod
    def get_by_host(self, host: str) -> Optional[DeviceConfig]:
        """Находит устройство по host."""
        pass

    @abstractmethod
    def create(self, device: DeviceConfig) -> DeviceConfig:
        """Создаёт устройство."""
        pass

    @abstractmethod
    def update(self, device: DeviceConfig) -> Optional[DeviceConfig]:
        """Обновляет устройство."""
        pass

    @abstractmethod
    def delete(self, device_id: str) -> bool:
        """Удаляет устройство."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Возвращает количество устройств."""
        pass


# =============================================================================
# JSON File Repository Implementation
# =============================================================================

class JsonDeviceRepository(DeviceRepository):
    """Репозиторий устройств на базе JSON файла."""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or self._default_path()
        self._ensure_dir()

    def _default_path(self) -> Path:
        return Path(__file__).parent.parent.parent / "data" / "devices.json"

    def _ensure_dir(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save(self, data: List[Dict[str, Any]]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_all(self) -> List[DeviceConfig]:
        return [DeviceConfig.from_dict(d) for d in self._load()]

    def get_by_id(self, device_id: str) -> Optional[DeviceConfig]:
        for d in self._load():
            if d.get("id") == device_id:
                return DeviceConfig.from_dict(d)
        return None

    def get_by_host(self, host: str) -> Optional[DeviceConfig]:
        for d in self._load():
            if d.get("host") == host:
                return DeviceConfig.from_dict(d)
        return None

    def create(self, device: DeviceConfig) -> DeviceConfig:
        data = self._load()

        # Проверка дубликата
        for d in data:
            if d.get("host") == device.host:
                raise ValueError(f"Device with host {device.host} already exists")

        device.created_at = datetime.now(timezone.utc).isoformat()
        device.updated_at = device.created_at
        data.append(device.to_dict())
        self._save(data)
        return device

    def update(self, device: DeviceConfig) -> Optional[DeviceConfig]:
        data = self._load()

        for i, d in enumerate(data):
            if d.get("id") == device.id:
                # Проверка дубликата host
                if device.host != d.get("host"):
                    for other in data:
                        if other.get("host") == device.host and other.get("id") != device.id:
                            raise ValueError(f"Device with host {device.host} already exists")

                device.updated_at = datetime.now(timezone.utc).isoformat()
                device.created_at = d.get("created_at")
                data[i] = device.to_dict()
                self._save(data)
                return device

        return None

    def delete(self, device_id: str) -> bool:
        data = self._load()
        original_count = len(data)
        data = [d for d in data if d.get("id") != device_id]

        if len(data) < original_count:
            self._save(data)
            return True
        return False

    def count(self) -> int:
        return len(self._load())


# =============================================================================
# Database Repository (placeholder for future)
# =============================================================================

# class SqlAlchemyDeviceRepository(DeviceRepository):
#     """Репозиторий на базе SQLAlchemy."""
#
#     def __init__(self, session):
#         self.session = session
#
#     def get_all(self) -> List[DeviceConfig]:
#         return self.session.query(DeviceModel).all()
#
#     # ... остальные методы


# =============================================================================
# Device Service (использует Repository)
# =============================================================================

class DeviceService:
    """Сервис управления устройствами."""

    def __init__(self, repository: Optional[DeviceRepository] = None):
        self.repo = repository or JsonDeviceRepository()

    def get_all_devices(self) -> List[Dict[str, Any]]:
        """Возвращает все устройства."""
        return [d.to_dict() for d in self.repo.get_all()]

    def get_enabled_devices(self) -> List[Dict[str, Any]]:
        """Возвращает только включённые устройства."""
        return [d.to_dict() for d in self.repo.get_all() if d.enabled]

    def get_device_hosts(self) -> List[str]:
        """Возвращает IP-адреса включённых устройств."""
        return [d.host for d in self.repo.get_all() if d.enabled]

    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Находит устройство по ID."""
        device = self.repo.get_by_id(device_id)
        return device.to_dict() if device else None

    def get_device_by_host(self, host: str) -> Optional[Dict[str, Any]]:
        """Находит устройство по host."""
        device = self.repo.get_by_host(host)
        return device.to_dict() if device else None

    def create_device(
        self,
        host: str,
        device_type: str = "cisco_ios",
        name: Optional[str] = None,
        site: Optional[str] = None,
        role: Optional[str] = None,
        tenant: Optional[str] = None,
        description: Optional[str] = None,
        enabled: bool = True,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Создаёт новое устройство."""
        device = DeviceConfig(
            id=str(uuid.uuid4()),
            host=host,
            device_type=device_type,
            name=name,
            site=site,
            role=role,
            tenant=tenant,
            description=description,
            enabled=enabled,
            tags=tags or [],
        )
        created = self.repo.create(device)
        return created.to_dict()

    def update_device(self, device_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обновляет устройство."""
        existing = self.repo.get_by_id(device_id)
        if not existing:
            return None

        # Применяем обновления
        for key, value in updates.items():
            if key != "id" and hasattr(existing, key):
                setattr(existing, key, value)

        updated = self.repo.update(existing)
        return updated.to_dict() if updated else None

    def delete_device(self, device_id: str) -> bool:
        """Удаляет устройство."""
        return self.repo.delete(device_id)

    def toggle_device(self, device_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        """Включает/выключает устройство."""
        return self.update_device(device_id, {"enabled": enabled})

    def bulk_import(
        self,
        devices_data: List[Dict[str, Any]],
        replace: bool = False
    ) -> Dict[str, int]:
        """Массовый импорт устройств."""
        if replace:
            # Удаляем все существующие
            for device in self.repo.get_all():
                self.repo.delete(device.id)

        added = 0
        skipped = 0
        errors = 0

        for item in devices_data:
            host = item.get("host")
            if not host:
                errors += 1
                continue

            try:
                self.create_device(
                    host=host,
                    device_type=item.get("device_type", "cisco_ios"),
                    name=item.get("name"),
                    site=item.get("site"),
                    role=item.get("role"),
                    tenant=item.get("tenant"),
                    description=item.get("description"),
                    enabled=item.get("enabled", True),
                    tags=item.get("tags"),
                )
                added += 1
            except ValueError:
                # Дубликат
                skipped += 1
            except Exception:
                errors += 1

        return {"added": added, "skipped": skipped, "errors": errors}

    def get_stats(self) -> Dict[str, Any]:
        """Статистика по устройствам."""
        devices = self.repo.get_all()

        by_type: Dict[str, int] = {}
        by_site: Dict[str, int] = {}
        enabled = 0
        disabled = 0

        for d in devices:
            # По типу
            by_type[d.device_type] = by_type.get(d.device_type, 0) + 1

            # По сайту
            site = d.site or "No site"
            by_site[site] = by_site.get(site, 0) + 1

            if d.enabled:
                enabled += 1
            else:
                disabled += 1

        return {
            "total": len(devices),
            "enabled": enabled,
            "disabled": disabled,
            "by_type": by_type,
            "by_site": by_site,
        }


# =============================================================================
# Global instance (можно заменить на DI)
# =============================================================================

_service: Optional[DeviceService] = None


def get_device_service() -> DeviceService:
    """Возвращает глобальный экземпляр сервиса."""
    global _service
    if _service is None:
        _service = DeviceService()
    return _service


# =============================================================================
# Helper: миграция из devices_ips.py
# =============================================================================

def migrate_from_devices_ips() -> int:
    """Мигрирует устройства из devices_ips.py."""
    service = get_device_service()

    if service.repo.count() > 0:
        return 0  # Уже есть данные

    devices = []
    try:
        try:
            from network_collector.devices_ips import DEVICES
            source = DEVICES
        except ImportError:
            from network_collector.devices_ips import devices_list
            source = devices_list

        for item in source:
            if isinstance(item, str):
                devices.append({"host": item})
            elif isinstance(item, dict):
                devices.append(item)

    except ImportError:
        return 0

    result = service.bulk_import(devices)
    return result["added"]


# =============================================================================
# Supported device types
# =============================================================================

DEVICE_TYPES = [
    {"value": "cisco_ios", "label": "Cisco IOS"},
    {"value": "cisco_iosxe", "label": "Cisco IOS-XE"},
    {"value": "cisco_nxos", "label": "Cisco Nexus NX-OS"},
    {"value": "arista_eos", "label": "Arista EOS"},
    {"value": "juniper_junos", "label": "Juniper Junos"},
    {"value": "eltex", "label": "Eltex"},
    {"value": "qtech", "label": "QTech"},
    {"value": "huawei_vrp", "label": "Huawei VRP"},
]

DEVICE_ROLES = [
    {"value": "switch", "label": "Switch"},
    {"value": "router", "label": "Router"},
    {"value": "firewall", "label": "Firewall"},
    {"value": "access-switch", "label": "Access Switch"},
    {"value": "distribution-switch", "label": "Distribution Switch"},
    {"value": "core-switch", "label": "Core Switch"},
    {"value": "leaf", "label": "Leaf"},
    {"value": "spine", "label": "Spine"},
    {"value": "border", "label": "Border"},
    {"value": "wan-router", "label": "WAN Router"},
    {"value": "load-balancer", "label": "Load Balancer"},
    {"value": "wireless-controller", "label": "Wireless Controller"},
    {"value": "access-point", "label": "Access Point"},
]


def get_device_types() -> List[Dict[str, str]]:
    """Возвращает список поддерживаемых типов устройств (платформ)."""
    return DEVICE_TYPES


def get_device_roles() -> List[Dict[str, str]]:
    """Возвращает список ролей устройств для NetBox."""
    return DEVICE_ROLES
