"""MAC routes - сбор MAC-адресов."""

from fastapi import APIRouter, Request

from ..schemas import MACRequest, MACResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.collector_service import CollectorService

router = APIRouter()


@router.post(
    "/collect",
    response_model=MACResponse,
    summary="Собрать MAC-адреса",
)
async def collect_mac(
    request: Request,
    body: MACRequest,
):
    """
    Собирает MAC-адреса с устройств (show mac address-table).

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Опции:
    - exclude_vlans: Исключить определённые VLAN
    - exclude_interfaces: Исключить интерфейсы по regex
    """
    credentials = get_credentials_from_headers(request)
    service = CollectorService(credentials)
    return await service.collect_mac(body)
