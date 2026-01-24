"""Inventory routes - сбор модулей/SFP."""

from fastapi import APIRouter, Request

from ..schemas import InventoryRequest, InventoryResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.collector_service import CollectorService

router = APIRouter()


@router.post(
    "/collect",
    response_model=InventoryResponse,
    summary="Собрать inventory",
)
async def collect_inventory(
    request: Request,
    body: InventoryRequest,
):
    """
    Собирает inventory (show inventory).

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Возвращает: модули, SFP, PSU с PID и serial.
    """
    credentials = get_credentials_from_headers(request)
    service = CollectorService(credentials)
    return await service.collect_inventory(body)
