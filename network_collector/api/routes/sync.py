"""Sync NetBox routes - синхронизация с NetBox."""

from fastapi import APIRouter, Request, HTTPException

from ..schemas import (
    SyncRequest,
    SyncResponse,
    SyncStats,
    DiffEntry,
    Credentials,
    NetBoxConfig,
)
from .auth import get_credentials_from_headers, get_netbox_config_from_headers
from ..services.sync_service import SyncService

router = APIRouter()


@router.post(
    "/netbox",
    response_model=SyncResponse,
    summary="Синхронизация с NetBox",
)
async def sync_netbox(
    request: Request,
    body: SyncRequest,
):
    """
    Синхронизирует данные с NetBox.

    Credentials передаются в headers:
    - X-SSH-Username, X-SSH-Password (SSH)
    - X-NetBox-URL, X-NetBox-Token (NetBox)

    Опции:
    - sync_all: Синхронизировать всё
    - create_devices: Создавать новые устройства
    - update_devices: Обновлять существующие
    - interfaces: Синхронизировать интерфейсы
    - ip_addresses: Синхронизировать IP
    - cables: Создавать кабели из LLDP/CDP
    - inventory: Синхронизировать модули

    dry_run=True (по умолчанию) только показывает изменения.
    """
    credentials = get_credentials_from_headers(request)
    netbox = get_netbox_config_from_headers(request)
    service = SyncService(credentials, netbox)
    return await service.sync(body)


@router.post(
    "/netbox/diff",
    response_model=SyncResponse,
    summary="Показать diff без применения",
)
async def sync_netbox_diff(
    request: Request,
    body: SyncRequest,
):
    """
    Показывает diff изменений без применения.

    Credentials передаются в headers.

    Эквивалент sync с dry_run=True.
    """
    credentials = get_credentials_from_headers(request)
    netbox = get_netbox_config_from_headers(request)
    body.dry_run = True
    body.show_diff = True
    service = SyncService(credentials, netbox)
    return await service.sync(body)
