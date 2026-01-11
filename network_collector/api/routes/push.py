"""Push descriptions routes - push описаний на устройства."""

from fastapi import APIRouter, Request

from ..schemas import PushDescriptionsRequest, PushDescriptionsResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.push_service import PushService

router = APIRouter()


@router.post(
    "/descriptions",
    response_model=PushDescriptionsResponse,
    summary="Push описаний интерфейсов",
)
async def push_descriptions(
    request: Request,
    body: PushDescriptionsRequest,
):
    """
    Отправляет описания интерфейсов на устройства.

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Читает описания из Excel/CSV файла и применяет на устройства.

    dry_run=True (по умолчанию) только показывает изменения.
    """
    credentials = get_credentials_from_headers(request)
    service = PushService(credentials)
    return await service.push(body)
