"""Match routes - сопоставление MAC с хостами."""

from fastapi import APIRouter, Request

from ..schemas import MatchRequest, MatchResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.match_service import MatchService

router = APIRouter()


@router.post(
    "/run",
    response_model=MatchResponse,
    summary="Сопоставить MAC с хостами",
)
async def match_mac(
    request: Request,
    body: MatchRequest,
):
    """
    Сопоставляет MAC-адреса с хостами из внешнего источника.

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Источники:
    - glpi: GLPI API
    - netbox: NetBox API
    - csv: CSV файл
    """
    credentials = get_credentials_from_headers(request)
    service = MatchService(credentials)
    return await service.match(body)
