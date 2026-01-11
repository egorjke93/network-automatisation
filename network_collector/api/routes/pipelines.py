"""
Pipeline API routes - управление конвейерами синхронизации.

Endpoints:
- GET /pipelines - список всех pipelines
- GET /pipelines/{id} - получить pipeline
- POST /pipelines - создать pipeline
- PUT /pipelines/{id} - обновить pipeline
- DELETE /pipelines/{id} - удалить pipeline
- POST /pipelines/{id}/run - запустить pipeline
- POST /pipelines/{id}/validate - валидировать pipeline
"""

from pathlib import Path
from typing import List
import uuid

from fastapi import APIRouter, Request, HTTPException

from ..schemas.pipeline import (
    PipelineConfig,
    PipelineCreate,
    PipelineUpdate,
    PipelineRunRequest,
    PipelineRunResponse,
    PipelineListResponse,
    PipelineValidateResponse,
    StepConfig,
    StepResultSchema,
)
from ..schemas import Credentials, NetBoxConfig
from .auth import get_credentials_from_headers, get_netbox_config_from_headers, get_optional_netbox_config
from ...core.pipeline import Pipeline, PipelineStep, StepType, PipelineExecutor
from ...core.device import Device

router = APIRouter()

# Директория для хранения pipelines
PIPELINES_DIR = Path(__file__).parent.parent.parent / "pipelines"


def _load_pipelines() -> List[Pipeline]:
    """Загружает все pipelines из директории."""
    pipelines = []
    if PIPELINES_DIR.exists():
        for yaml_file in PIPELINES_DIR.glob("*.yaml"):
            try:
                pipeline = Pipeline.from_yaml(str(yaml_file))
                pipelines.append(pipeline)
            except Exception:
                pass  # Пропускаем невалидные файлы
    return pipelines


def _get_pipeline(pipeline_id: str) -> Pipeline:
    """Получает pipeline по ID."""
    yaml_path = PIPELINES_DIR / f"{pipeline_id}.yaml"
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")
    return Pipeline.from_yaml(str(yaml_path))


def _pipeline_to_config(pipeline: Pipeline) -> PipelineConfig:
    """Конвертирует Pipeline в PipelineConfig."""
    return PipelineConfig(
        id=pipeline.id,
        name=pipeline.name,
        description=pipeline.description,
        enabled=pipeline.enabled,
        steps=[
            StepConfig(
                id=s.id,
                type=s.type.value,
                target=s.target,
                enabled=s.enabled,
                options=s.options,
                depends_on=s.depends_on,
            )
            for s in pipeline.steps
        ],
    )


def _config_to_pipeline(config: PipelineCreate, pipeline_id: str = None) -> Pipeline:
    """Конвертирует PipelineCreate в Pipeline."""
    return Pipeline(
        id=pipeline_id or str(uuid.uuid4())[:8],
        name=config.name,
        description=config.description,
        steps=[
            PipelineStep(
                id=s.id,
                type=StepType(s.type),
                target=s.target,
                enabled=s.enabled,
                options=s.options,
                depends_on=s.depends_on,
            )
            for s in config.steps
        ],
    )


@router.get(
    "",
    response_model=PipelineListResponse,
    summary="Список pipelines",
)
async def list_pipelines():
    """
    Возвращает список всех доступных pipelines.
    """
    pipelines = _load_pipelines()
    return PipelineListResponse(
        pipelines=[_pipeline_to_config(p) for p in pipelines],
        total=len(pipelines),
    )


@router.get(
    "/{pipeline_id}",
    response_model=PipelineConfig,
    summary="Получить pipeline",
)
async def get_pipeline(pipeline_id: str):
    """
    Возвращает pipeline по ID.
    """
    pipeline = _get_pipeline(pipeline_id)
    return _pipeline_to_config(pipeline)


@router.post(
    "",
    response_model=PipelineConfig,
    summary="Создать pipeline",
    status_code=201,
)
async def create_pipeline(config: PipelineCreate):
    """
    Создаёт новый pipeline.
    """
    # Генерируем ID из имени
    pipeline_id = config.name.lower().replace(" ", "_")[:20]

    # Проверяем что не существует
    yaml_path = PIPELINES_DIR / f"{pipeline_id}.yaml"
    if yaml_path.exists():
        raise HTTPException(status_code=409, detail=f"Pipeline '{pipeline_id}' already exists")

    pipeline = _config_to_pipeline(config, pipeline_id)

    # Валидируем
    errors = pipeline.validate()
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Сохраняем
    PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
    pipeline.to_yaml(str(yaml_path))

    return _pipeline_to_config(pipeline)


@router.put(
    "/{pipeline_id}",
    response_model=PipelineConfig,
    summary="Обновить pipeline",
)
async def update_pipeline(pipeline_id: str, update: PipelineUpdate):
    """
    Обновляет существующий pipeline.
    """
    pipeline = _get_pipeline(pipeline_id)

    if update.name is not None:
        pipeline.name = update.name
    if update.description is not None:
        pipeline.description = update.description
    if update.enabled is not None:
        pipeline.enabled = update.enabled
    if update.steps is not None:
        pipeline.steps = [
            PipelineStep(
                id=s.id,
                type=StepType(s.type),
                target=s.target,
                enabled=s.enabled,
                options=s.options,
                depends_on=s.depends_on,
            )
            for s in update.steps
        ]

    # Валидируем
    errors = pipeline.validate()
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # Сохраняем
    yaml_path = PIPELINES_DIR / f"{pipeline_id}.yaml"
    pipeline.to_yaml(str(yaml_path))

    return _pipeline_to_config(pipeline)


@router.delete(
    "/{pipeline_id}",
    status_code=204,
    summary="Удалить pipeline",
)
async def delete_pipeline(pipeline_id: str):
    """
    Удаляет pipeline.
    """
    yaml_path = PIPELINES_DIR / f"{pipeline_id}.yaml"
    if not yaml_path.exists():
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found")

    yaml_path.unlink()


@router.post(
    "/{pipeline_id}/validate",
    response_model=PipelineValidateResponse,
    summary="Валидировать pipeline",
)
async def validate_pipeline(pipeline_id: str):
    """
    Валидирует pipeline и возвращает ошибки.
    """
    pipeline = _get_pipeline(pipeline_id)
    errors = pipeline.validate()
    return PipelineValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
    )


@router.post(
    "/{pipeline_id}/run",
    response_model=PipelineRunResponse,
    summary="Запустить pipeline",
)
async def run_pipeline(
    pipeline_id: str,
    request: Request,
    body: PipelineRunRequest,
):
    """
    Запускает pipeline.

    Credentials передаются в headers:
    - X-SSH-Username, X-SSH-Password (SSH)
    - X-NetBox-URL, X-NetBox-Token (NetBox, опционально)

    Параметры:
    - devices: Список устройств для обработки
    - dry_run: Режим dry-run (по умолчанию True)
    """
    credentials = get_credentials_from_headers(request)
    netbox = get_optional_netbox_config(request)

    pipeline = _get_pipeline(pipeline_id)

    # Конвертируем devices из dict в Device
    devices = [
        Device(
            host=d.get("host", d.get("ip", "")),
            platform=d.get("platform", "cisco_ios"),
        )
        for d in body.devices
    ]

    # Создаём executor
    executor = PipelineExecutor(
        pipeline,
        dry_run=body.dry_run,
    )

    # Выполняем
    netbox_config = None
    if netbox:
        netbox_config = {
            "url": netbox.url,
            "token": netbox.token,
        }

    result = executor.run(
        devices=devices,
        credentials={
            "username": credentials.username,
            "password": credentials.password,
        },
        netbox_config=netbox_config,
    )

    return PipelineRunResponse(
        pipeline_id=result.pipeline_id,
        status=result.status.value,
        steps=[
            StepResultSchema(
                step_id=s.step_id,
                status=s.status.value,
                error=s.error,
                duration_ms=s.duration_ms,
            )
            for s in result.steps
        ],
        total_duration_ms=result.total_duration_ms,
    )
