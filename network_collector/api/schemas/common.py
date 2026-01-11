"""Общие schemas для API."""

from typing import Optional, List, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    """Статус задачи."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DeviceResult(BaseModel):
    """Результат выполнения для одного устройства."""

    hostname: str
    device_ip: str
    success: bool
    error: Optional[str] = None
    data: Optional[Any] = None


class TaskResult(BaseModel):
    """Результат выполнения задачи."""

    task_id: str
    status: TaskStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    progress: int = Field(0, ge=0, le=100)
    current_device: Optional[str] = None
    results: List[DeviceResult] = []
    errors: List[str] = []


class HealthResponse(BaseModel):
    """Ответ health check."""

    status: str = "ok"
    version: str
    uptime: float


class ErrorResponse(BaseModel):
    """Ответ с ошибкой."""

    success: bool = False
    error: str
    detail: Optional[str] = None
