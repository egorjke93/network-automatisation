"""Device Management routes - CRUD для устройств."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from ..services.device_service import (
    get_device_service,
    get_device_types,
    get_device_roles,
    migrate_from_devices_ips,
)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class DeviceCreate(BaseModel):
    """Схема создания устройства."""
    host: str = Field(..., description="IP адрес или hostname")
    device_type: str = Field(default="cisco_ios", description="Платформа (cisco_ios, cisco_nxos, etc.)")
    name: Optional[str] = Field(None, description="Имя устройства")
    site: Optional[str] = Field(None, description="Сайт NetBox")
    role: Optional[str] = Field(None, description="Роль устройства (switch, router, etc.)")
    tenant: Optional[str] = Field(None, description="Tenant NetBox")
    description: Optional[str] = Field(None, description="Описание")
    enabled: bool = Field(default=True, description="Активно")
    tags: Optional[List[str]] = Field(default=[], description="Теги")


class DeviceUpdate(BaseModel):
    """Схема обновления устройства."""
    host: Optional[str] = None
    device_type: Optional[str] = None
    name: Optional[str] = None
    site: Optional[str] = None
    role: Optional[str] = None
    tenant: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None


class DeviceResponse(BaseModel):
    """Ответ с устройством."""
    id: str
    host: str
    device_type: str
    name: Optional[str]
    site: Optional[str]
    role: Optional[str]
    tenant: Optional[str]
    description: Optional[str]
    enabled: bool
    tags: List[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class DevicesListResponse(BaseModel):
    """Список устройств."""
    devices: List[DeviceResponse]
    total: int


class BulkImportRequest(BaseModel):
    """Запрос на массовый импорт."""
    devices: List[DeviceCreate]
    replace: bool = Field(default=False, description="Заменить все существующие")


class BulkImportResponse(BaseModel):
    """Результат импорта."""
    added: int
    skipped: int
    errors: int


class ToggleRequest(BaseModel):
    """Запрос на включение/выключение."""
    enabled: bool


# =============================================================================
# Routes
# =============================================================================

@router.get(
    "/",
    response_model=DevicesListResponse,
    summary="Список устройств",
)
async def list_devices(
    enabled_only: bool = False,
    site: Optional[str] = None,
    device_type: Optional[str] = None,
):
    """
    Возвращает список устройств с фильтрацией.

    - **enabled_only** - только активные устройства
    - **site** - фильтр по сайту
    - **device_type** - фильтр по типу
    """
    service = get_device_service()

    if enabled_only:
        devices = service.get_enabled_devices()
    else:
        devices = service.get_all_devices()

    # Фильтрация
    if site:
        devices = [d for d in devices if d.get("site") == site]
    if device_type:
        devices = [d for d in devices if d.get("device_type") == device_type]

    return DevicesListResponse(devices=devices, total=len(devices))


@router.get(
    "/stats",
    summary="Статистика по устройствам",
)
async def get_stats():
    """Возвращает статистику по устройствам."""
    service = get_device_service()
    return service.get_stats()


@router.get(
    "/types",
    summary="Поддерживаемые типы устройств (платформы)",
)
async def list_device_types():
    """Возвращает список поддерживаемых платформ (для SSH подключения)."""
    return {"types": get_device_types()}


@router.get(
    "/roles",
    summary="Роли устройств для NetBox",
)
async def list_device_roles():
    """Возвращает список ролей устройств для NetBox."""
    return {"roles": get_device_roles()}


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Получить устройство по ID",
)
async def get_device(device_id: str):
    """Возвращает устройство по ID."""
    service = get_device_service()
    device = service.get_device(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.post(
    "/",
    response_model=DeviceResponse,
    summary="Создать устройство",
    status_code=201,
)
async def create_device(data: DeviceCreate):
    """Создаёт новое устройство."""
    service = get_device_service()

    try:
        device = service.create_device(
            host=data.host,
            device_type=data.device_type,
            name=data.name,
            site=data.site,
            role=data.role,
            tenant=data.tenant,
            description=data.description,
            enabled=data.enabled,
            tags=data.tags,
        )
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Обновить устройство",
)
async def update_device(device_id: str, data: DeviceUpdate):
    """Обновляет устройство."""
    service = get_device_service()

    updates = data.model_dump(exclude_unset=True)

    try:
        device = service.update_device(device_id, updates)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{device_id}",
    summary="Удалить устройство",
)
async def delete_device(device_id: str):
    """Удаляет устройство."""
    service = get_device_service()

    if not service.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    return {"success": True, "message": "Device deleted"}


@router.post(
    "/{device_id}/toggle",
    response_model=DeviceResponse,
    summary="Включить/выключить устройство",
)
async def toggle_device(device_id: str, data: ToggleRequest):
    """Включает или выключает устройство."""
    service = get_device_service()

    device = service.toggle_device(device_id, data.enabled)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.post(
    "/bulk",
    response_model=BulkImportResponse,
    summary="Массовый импорт устройств",
)
async def bulk_import(data: BulkImportRequest):
    """
    Массовый импорт устройств.

    - **replace** = true - заменяет все существующие устройства
    - **replace** = false - добавляет только новые (дубликаты пропускаются)
    """
    service = get_device_service()

    devices_data = [d.model_dump() for d in data.devices]
    result = service.bulk_import(devices_data, replace=data.replace)

    return BulkImportResponse(**result)


@router.post(
    "/migrate",
    summary="Миграция из devices_ips.py",
)
async def migrate_devices():
    """
    Мигрирует устройства из devices_ips.py в JSON хранилище.

    Выполняется только если хранилище пустое.
    """
    count = migrate_from_devices_ips()
    return {
        "success": True,
        "migrated": count,
        "message": f"Migrated {count} devices" if count else "No devices to migrate or storage not empty",
    }


@router.get(
    "/hosts/list",
    summary="Список IP-адресов для сбора",
)
async def get_device_hosts():
    """
    Возвращает список IP-адресов активных устройств.

    Используется для запуска сбора данных.
    """
    service = get_device_service()
    hosts = service.get_device_hosts()
    return {"hosts": hosts, "count": len(hosts)}
