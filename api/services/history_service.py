"""
История операций.

Хранит логи операций в JSON файле.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import threading

logger = logging.getLogger(__name__)

# Путь к файлу истории
HISTORY_FILE = Path(__file__).parent.parent.parent / "data" / "history.json"
MAX_ENTRIES = 1000  # Максимум записей

_lock = threading.Lock()


def _ensure_dir():
    """Создаёт директорию для данных."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_history() -> List[Dict[str, Any]]:
    """Загружает историю из файла."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_history(entries: List[Dict[str, Any]]):
    """Сохраняет историю в файл."""
    _ensure_dir()
    # Ограничиваем количество записей
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2, default=str)


def add_entry(
    operation: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
    devices: Optional[List[str]] = None,
    stats: Optional[Dict[str, Any]] = None,
    duration_ms: Optional[int] = None,
    error: Optional[str] = None,
):
    """
    Добавляет запись в историю.

    Args:
        operation: Тип операции (devices, mac, lldp, interfaces, inventory, sync, backup)
        status: Статус (success, error, partial)
        details: Детали операции
        devices: Список устройств
        stats: Статистика (created, updated, etc.)
        duration_ms: Длительность в миллисекундах
        error: Сообщение об ошибке
    """
    entry = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "status": status,
        "devices": devices or [],
        "device_count": len(devices) if devices else 0,
        "stats": stats,
        "duration_ms": duration_ms,
        "error": error,
        "details": details,
    }

    with _lock:
        history = _load_history()
        history.append(entry)
        _save_history(history)

    return entry


def get_history(
    limit: int = 50,
    offset: int = 0,
    operation: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Возвращает историю операций.

    Args:
        limit: Максимум записей
        offset: Смещение
        operation: Фильтр по типу операции
        status: Фильтр по статусу

    Returns:
        Dict с entries и total
    """
    with _lock:
        history = _load_history()

    # Фильтрация
    if operation:
        history = [e for e in history if e.get("operation") == operation]
    if status:
        history = [e for e in history if e.get("status") == status]

    # Сортировка по времени (новые первые)
    history = sorted(history, key=lambda e: e.get("timestamp", ""), reverse=True)

    total = len(history)
    entries = history[offset : offset + limit]

    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_stats() -> Dict[str, Any]:
    """
    Возвращает статистику по операциям.

    Returns:
        Dict со статистикой
    """
    with _lock:
        history = _load_history()

    if not history:
        return {
            "total_operations": 0,
            "by_operation": {},
            "by_status": {},
            "last_24h": 0,
        }

    # Подсчёт по операциям
    by_operation = {}
    by_status = {}
    last_24h = 0
    now = datetime.now()

    for entry in history:
        op = entry.get("operation", "unknown")
        status = entry.get("status", "unknown")

        by_operation[op] = by_operation.get(op, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

        # Последние 24 часа
        try:
            ts = datetime.fromisoformat(entry.get("timestamp", ""))
            if (now - ts).total_seconds() < 86400:
                last_24h += 1
        except (ValueError, TypeError) as e:
            logger.debug(f"Ошибка парсинга timestamp в истории: {e}")

    return {
        "total_operations": len(history),
        "by_operation": by_operation,
        "by_status": by_status,
        "last_24h": last_24h,
    }


def clear_history():
    """Очищает историю."""
    with _lock:
        _save_history([])
