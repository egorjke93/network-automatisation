"""
Pydantic схемы для Pipeline API.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class StepConfig(BaseModel):
    """Конфигурация шага pipeline."""
    id: str = Field(..., description="Уникальный ID шага")
    type: str = Field(..., description="Тип: collect, sync, export")
    target: str = Field(..., description="Цель: devices, interfaces, etc.")
    enabled: bool = Field(True, description="Включён ли шаг")
    options: Dict[str, Any] = Field(default_factory=dict, description="Опции шага")
    depends_on: List[str] = Field(default_factory=list, description="Зависимости")


class PipelineConfig(BaseModel):
    """Конфигурация pipeline."""
    id: str = Field(..., description="Уникальный ID pipeline")
    name: str = Field(..., description="Название")
    description: str = Field("", description="Описание")
    enabled: bool = Field(True, description="Включён ли pipeline")
    steps: List[StepConfig] = Field(..., description="Шаги pipeline")


class PipelineCreate(BaseModel):
    """Создание нового pipeline."""
    name: str = Field(..., description="Название", min_length=1)
    description: str = Field("", description="Описание")
    steps: List[StepConfig] = Field(..., description="Шаги pipeline", min_length=1)


class PipelineUpdate(BaseModel):
    """Обновление pipeline."""
    name: Optional[str] = Field(None, description="Название")
    description: Optional[str] = Field(None, description="Описание")
    enabled: Optional[bool] = Field(None, description="Включён ли")
    steps: Optional[List[StepConfig]] = Field(None, description="Шаги")


class StepResultSchema(BaseModel):
    """Результат выполнения шага."""
    step_id: str
    status: str
    error: Optional[str] = None
    duration_ms: int = 0
    data: Optional[Dict[str, Any]] = Field(None, description="Данные результата (created, updated, skipped, etc.)")


class PipelineRunRequest(BaseModel):
    """Запрос на выполнение pipeline."""
    devices: List[Dict[str, Any]] = Field(default_factory=list, description="Список устройств (пустой = из device management)")
    dry_run: bool = Field(True, description="Режим dry-run")
    async_mode: bool = Field(True, description="Асинхронный режим (возвращает task_id)")


class PipelineRunResponse(BaseModel):
    """Ответ на выполнение pipeline."""
    pipeline_id: str
    status: str
    steps: List[StepResultSchema] = Field(default_factory=list)
    total_duration_ms: int = 0
    task_id: Optional[str] = Field(None, description="ID задачи (для async mode)")


class PipelineListResponse(BaseModel):
    """Список pipelines."""
    pipelines: List[PipelineConfig]
    total: int


class PipelineValidateResponse(BaseModel):
    """Результат валидации pipeline."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
