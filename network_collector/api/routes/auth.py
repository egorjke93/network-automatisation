"""Auth routes - управление credentials.

Credentials передаются через HTTP headers в каждом запросе.
Сервер НЕ хранит пароли — они остаются только в браузере (sessionStorage).

Headers:
    X-SSH-Username: admin
    X-SSH-Password: secret
    X-NetBox-URL: http://netbox:8000
    X-NetBox-Token: 0123456789abcdef
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Optional

from ..schemas import Credentials, NetBoxConfig, FullConfig

router = APIRouter()


# =============================================================================
# API Endpoints (для проверки статуса - не хранят данные)
# =============================================================================

@router.get("/credentials/status", summary="Проверить наличие credentials в headers")
async def credentials_status(request: Request):
    """Проверяет есть ли credentials в headers запроса."""
    username = request.headers.get("X-SSH-Username")
    return {
        "credentials_set": username is not None,
        "username": username,
        "message": "Credentials передаются в headers каждого запроса (не хранятся на сервере)",
    }


@router.get("/netbox/status", summary="Проверить наличие NetBox config в headers")
async def netbox_status(request: Request):
    """Проверяет есть ли NetBox config в headers запроса."""
    url = request.headers.get("X-NetBox-URL")
    return {
        "netbox_configured": url is not None,
        "url": url,
        "message": "NetBox config передаётся в headers каждого запроса (не хранится на сервере)",
    }


# =============================================================================
# Dependency functions - извлечение из headers
# =============================================================================

def get_credentials_from_headers(request: Request) -> Credentials:
    """
    Извлекает SSH credentials из HTTP headers.

    Headers:
        X-SSH-Username: admin
        X-SSH-Password: secret

    Raises:
        HTTPException 401 если headers отсутствуют
    """
    username = request.headers.get("X-SSH-Username")
    password = request.headers.get("X-SSH-Password")

    if not username or not password:
        raise HTTPException(
            status_code=401,
            detail="SSH credentials required. Set X-SSH-Username and X-SSH-Password headers.",
        )

    return Credentials(username=username, password=password)


def get_netbox_config_from_headers(request: Request) -> NetBoxConfig:
    """
    Извлекает NetBox config из HTTP headers.

    Headers:
        X-NetBox-URL: http://netbox:8000
        X-NetBox-Token: 0123456789abcdef

    Raises:
        HTTPException 401 если headers отсутствуют
    """
    url = request.headers.get("X-NetBox-URL")
    token = request.headers.get("X-NetBox-Token")

    if not url or not token:
        raise HTTPException(
            status_code=401,
            detail="NetBox config required. Set X-NetBox-URL and X-NetBox-Token headers.",
        )

    return NetBoxConfig(url=url, token=token)


def get_optional_netbox_config(request: Request) -> Optional[NetBoxConfig]:
    """Извлекает NetBox config из headers (опционально)."""
    url = request.headers.get("X-NetBox-URL")
    token = request.headers.get("X-NetBox-Token")

    if url and token:
        return NetBoxConfig(url=url, token=token)
    return None


# =============================================================================
# Aliases для обратной совместимости
# =============================================================================

# Новые функции (используют headers)
get_credentials = get_credentials_from_headers
get_netbox_config = get_netbox_config_from_headers
