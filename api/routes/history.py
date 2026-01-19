"""History routes - история операций."""

from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from ..services import history_service

router = APIRouter()


class HistoryEntry(BaseModel):
    """Запись истории."""

    id: str
    timestamp: str
    operation: str
    status: str
    devices: List[str] = []
    device_count: int = 0
    stats: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    details: Optional[Any] = None  # Dict или List в зависимости от операции


class HistoryResponse(BaseModel):
    """Ответ со списком записей."""

    entries: List[HistoryEntry]
    total: int
    limit: int
    offset: int


class HistoryStats(BaseModel):
    """Статистика операций."""

    total_operations: int
    by_operation: Dict[str, int]
    by_status: Dict[str, int]
    last_24h: int


@router.get(
    "/",
    response_model=HistoryResponse,
    summary="Получить историю операций",
)
async def get_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    operation: Optional[str] = Query(None, description="Фильтр по типу операции"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
):
    """
    Возвращает историю операций.

    Поддерживает пагинацию и фильтрацию по типу операции и статусу.
    """
    return history_service.get_history(
        limit=limit,
        offset=offset,
        operation=operation,
        status=status,
    )


@router.get(
    "/stats",
    response_model=HistoryStats,
    summary="Статистика операций",
)
async def get_stats():
    """
    Возвращает статистику по операциям.

    - Общее количество операций
    - Разбивка по типам
    - Разбивка по статусам
    - Количество за последние 24 часа
    """
    return history_service.get_stats()


@router.delete(
    "/",
    summary="Очистить историю",
)
async def clear_history():
    """Очищает всю историю операций."""
    history_service.clear_history()
    return {"status": "cleared"}
