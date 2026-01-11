"""Backup routes - резервное копирование конфигураций."""

from fastapi import APIRouter, Request

from ..schemas import BackupRequest, BackupResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.collector_service import CollectorService

router = APIRouter()


@router.post(
    "/run",
    response_model=BackupResponse,
    summary="Выполнить backup конфигураций",
)
async def run_backup(
    request: Request,
    body: BackupRequest,
):
    """
    Выполняет резервное копирование конфигураций.

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Сохраняет running-config в файлы.
    """
    credentials = get_credentials_from_headers(request)
    service = CollectorService(credentials)
    return await service.run_backup(body)
