"""Interfaces routes - сбор интерфейсов."""

from fastapi import APIRouter, Request

from ..schemas import InterfacesRequest, InterfacesResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.collector_service import CollectorService

router = APIRouter()


@router.post(
    "/collect",
    response_model=InterfacesResponse,
    summary="Собрать интерфейсы",
)
async def collect_interfaces(
    request: Request,
    body: InterfacesRequest,
):
    """
    Собирает информацию об интерфейсах (show interfaces).

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Возвращает: name, status, ip, mac, speed, duplex, vlan, mode.
    """
    credentials = get_credentials_from_headers(request)
    service = CollectorService(credentials)
    return await service.collect_interfaces(body)
