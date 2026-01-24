"""
Network Collector Web API.

FastAPI backend для веб-интерфейса.

Запуск:
    cd /home/sa/project
    source network_collector/myenv/bin/activate
    uvicorn network_collector.api.main:app --reload --host 0.0.0.0 --port 8080

Документация:
    http://localhost:8080/docs (Swagger UI)
    http://localhost:8080/redoc (ReDoc)
"""

import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .schemas import HealthResponse, ErrorResponse
from .routes import (
    auth_router,
    devices_router,
    mac_router,
    lldp_router,
    interfaces_router,
    inventory_router,
    backup_router,
    sync_router,
    match_router,
    push_router,
    pipelines_router,
    history_router,
    device_management_router,
    fields_router,
    tasks_router,
)

# Время запуска для uptime
START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events."""
    # Startup
    print(f"Network Collector API v{__version__} starting...")
    yield
    # Shutdown
    print("Network Collector API shutting down...")


app = FastAPI(
    title="Network Collector API",
    description="""
## Network Collector Web API

REST API для сбора данных с сетевого оборудования и синхронизации с NetBox.

### Возможности

- **Devices** - Инвентаризация устройств (show version)
- **MAC** - Сбор MAC-адресов
- **LLDP/CDP** - Сбор соседей
- **Interfaces** - Сбор интерфейсов
- **Inventory** - Сбор модулей/SFP
- **Backup** - Резервное копирование конфигураций
- **Sync NetBox** - Синхронизация с NetBox
- **Match** - Сопоставление MAC с хостами
- **Push Descriptions** - Push описаний на устройства

### Аутентификация

Credentials (SSH логин/пароль) передаются в теле запроса.
NetBox токен передаётся отдельно для sync операций.
    """,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Exception handlers
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Глобальный обработчик ошибок."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            detail=str(exc),
        ).model_dump(),
    )


# =============================================================================
# Health check
# =============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check",
)
async def health_check():
    """Проверка состояния API."""
    return HealthResponse(
        status="ok",
        version=__version__,
        uptime=time.time() - START_TIME,
    )


@app.get("/", tags=["Health"])
async def root():
    """Корневой endpoint."""
    return {
        "name": "Network Collector API",
        "version": __version__,
        "docs": "/docs",
    }


# =============================================================================
# Routes
# =============================================================================

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(devices_router, prefix="/api/devices", tags=["Devices"])
app.include_router(mac_router, prefix="/api/mac", tags=["MAC"])
app.include_router(lldp_router, prefix="/api/lldp", tags=["LLDP/CDP"])
app.include_router(interfaces_router, prefix="/api/interfaces", tags=["Interfaces"])
app.include_router(inventory_router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(backup_router, prefix="/api/backup", tags=["Backup"])
app.include_router(sync_router, prefix="/api/sync", tags=["Sync NetBox"])
app.include_router(match_router, prefix="/api/match", tags=["Match"])
app.include_router(push_router, prefix="/api/push", tags=["Push Descriptions"])
app.include_router(pipelines_router, prefix="/api/pipelines", tags=["Pipelines"])
app.include_router(history_router, prefix="/api/history", tags=["History"])
app.include_router(device_management_router, prefix="/api/device-management", tags=["Device Management"])
app.include_router(tasks_router, tags=["Tasks"])
app.include_router(fields_router, tags=["Fields"])
