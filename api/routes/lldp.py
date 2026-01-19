"""LLDP/CDP routes - сбор соседей."""

from fastapi import APIRouter, Request

from ..schemas import LLDPRequest, LLDPResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.collector_service import CollectorService

router = APIRouter()


@router.post(
    "/collect",
    response_model=LLDPResponse,
    summary="Собрать LLDP/CDP соседей",
)
async def collect_lldp(
    request: Request,
    body: LLDPRequest,
):
    """
    Собирает LLDP/CDP соседей с устройств.

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Протоколы:
    - lldp: Только LLDP
    - cdp: Только CDP (Cisco)
    - both: Оба протокола с merge (CDP приоритет)
    """
    credentials = get_credentials_from_headers(request)
    service = CollectorService(credentials)
    return await service.collect_lldp(body)
