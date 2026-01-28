"""Devices routes - сбор информации об устройствах."""

from fastapi import APIRouter, Request
from typing import List, Optional

from ..schemas import (
    DevicesRequest,
    DevicesResponse,
    DeviceInfo,
    Credentials,
)
from .auth import get_credentials_from_headers
from ..services.collector_service import CollectorService

router = APIRouter()


@router.get(
    "",
    summary="Получить список устройств",
)
async def get_devices():
    """
    Возвращает список устройств для выбора в UI.

    Используется DeviceSelector компонентом.
    """
    from ..services.device_service import get_device_service

    service = get_device_service()
    devices = service.get_enabled_devices()

    return {"devices": devices or []}


@router.post(
    "/collect",
    response_model=DevicesResponse,
    summary="Собрать информацию об устройствах",
)
async def collect_devices(
    request: Request,
    body: DevicesRequest,
):
    """
    Собирает информацию об устройствах (show version).

    Credentials передаются в headers:
    - X-SSH-Username
    - X-SSH-Password

    Возвращает: hostname, model, serial, version, uptime.
    """
    credentials = get_credentials_from_headers(request)
    service = CollectorService(credentials)
    return await service.collect_devices(body)


@router.get(
    "/list",
    summary="Получить список устройств из конфига",
)
async def list_devices():
    """
    Возвращает список устройств для сбора данных.

    Использует device_service (JSON хранилище) с fallback на devices_ips.py.
    """
    from ..services.device_service import get_device_service

    service = get_device_service()
    devices = service.get_enabled_devices()

    if devices:
        return {"devices": devices}

    # Fallback для обратной совместимости
    try:
        from network_collector.devices_ips import devices_list
        return {"devices": devices_list}
    except ImportError:
        return {"devices": [], "error": "No devices configured"}
