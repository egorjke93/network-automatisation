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
from typing import List, Dict, Any
import uuid
import threading
import time
import logging

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
from ..services.task_manager import task_manager
from ..services import history_service

logger = logging.getLogger(__name__)

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


def _run_pipeline_background(
    task_id: str,
    pipeline: Pipeline,
    devices: List[Device],
    credentials: Dict[str, str],
    netbox_config: Dict[str, str],
    dry_run: bool,
):
    """Выполняет pipeline в фоновом режиме с обновлением прогресса."""
    start_time = time.time()
    enabled_steps = [s for s in pipeline.steps if s.enabled]
    total_steps = len(enabled_steps)

    # Callbacks для обновления прогресса
    def on_step_start(step: PipelineStep):
        step_index = next((i for i, s in enumerate(enabled_steps) if s.id == step.id), 0)
        task_manager.update_task(
            task_id,
            current_step=step_index,
            message=f"Выполняется: {step.type.value} {step.target}",
        )

    def on_step_complete(step: PipelineStep, step_result):
        step_index = next((i for i, s in enumerate(enabled_steps) if s.id == step.id), 0)
        # Формируем сообщение о результате
        data = step_result.data or {}
        created = data.get("created", 0)
        updated = data.get("updated", 0)
        msg = f"{step.type.value} {step.target}: "
        if step_result.status.value == "completed":
            msg += f"+{created} created, ~{updated} updated"
        else:
            msg += step_result.error or "failed"

        task_manager.update_task(
            task_id,
            current_step=step_index + 1,
            message=msg,
        )

    try:
        executor = PipelineExecutor(
            pipeline,
            dry_run=dry_run,
            on_step_start=on_step_start,
            on_step_complete=on_step_complete,
        )

        result = executor.run(
            devices=devices,
            credentials=credentials,
            netbox_config=netbox_config,
        )

        # Формируем результат для task
        task_result = {
            "pipeline_id": result.pipeline_id,
            "status": result.status.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "status": s.status.value,
                    "error": s.error,
                    "duration_ms": s.duration_ms,
                    "data": s.data,
                }
                for s in result.steps
            ],
            "total_duration_ms": result.total_duration_ms,
        }

        task_manager.complete_task(
            task_id,
            result=task_result,
            message=f"Pipeline завершён: {result.status.value}",
        )

        # Записываем в историю (не для dry_run)
        if not dry_run:
            # Собираем статистику по шагам
            stats = {}
            for s in result.steps:
                if s.data:
                    stats[s.step_id] = {
                        "created": s.data.get("created", 0),
                        "updated": s.data.get("updated", 0),
                        "deleted": s.data.get("deleted", 0),
                        "skipped": s.data.get("skipped", 0),
                        "details": s.data.get("details"),
                    }

            history_service.add_entry(
                operation=f"pipeline:{pipeline.id}",
                status="success" if result.status.value == "completed" else "partial",
                devices=[d.host for d in devices],
                stats=stats,
                duration_ms=result.total_duration_ms,
            )

    except Exception as e:
        logger.error(f"Pipeline execution error: {e}")
        task_manager.fail_task(task_id, str(e))
        # Записываем ошибку в историю
        history_service.add_entry(
            operation=f"pipeline:{pipeline.id}",
            status="error",
            devices=[d.host for d in devices],
            duration_ms=int((time.time() - start_time) * 1000),
            error=str(e),
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
    - devices: Список устройств (опционально - если пусто, берёт из device management)
    - dry_run: Режим dry-run (по умолчанию True)
    - async_mode: Асинхронный режим (возвращает task_id)
    """
    credentials = get_credentials_from_headers(request)
    netbox = get_optional_netbox_config(request)

    pipeline = _get_pipeline(pipeline_id)

    # Если devices не указаны - берём из device management
    if body.devices:
        devices = [
            Device(
                host=d.get("host", d.get("ip", "")),
                platform=d.get("platform", d.get("device_type", "cisco_ios")),
                hostname=d.get("name"),  # Передаём hostname из данных
                device_type=d.get("model"),  # Передаём модель если есть
            )
            for d in body.devices
        ]
    else:
        # Берём устройства из device_service - включая name и другие поля
        from ..services.device_service import get_device_service
        device_service = get_device_service()
        all_devices = device_service.get_all_devices()
        devices = [
            Device(
                host=d["host"],
                platform=d.get("device_type", "cisco_ios"),
                hostname=d.get("name"),  # name из Device Management = hostname
                device_type=d.get("model"),  # model из Device Management
                role=d.get("role"),  # role из Device Management
            )
            for d in all_devices
            if d.get("enabled", True)
        ]

    if not devices:
        raise HTTPException(status_code=400, detail="No devices to process")

    # Подготавливаем конфигурации
    creds = {
        "username": credentials.username,
        "password": credentials.password,
    }
    netbox_config = None
    if netbox:
        netbox_config = {
            "url": netbox.url,
            "token": netbox.token,
        }

    # Async mode - запускаем в фоне и возвращаем task_id
    if body.async_mode:
        enabled_steps = [s for s in pipeline.steps if s.enabled]
        task = task_manager.create_task(
            task_type=f"pipeline_{pipeline_id}",
            total_steps=len(enabled_steps),
            total_items=len(devices),
        )
        task_manager.start_task(task.id, f"Запуск pipeline: {pipeline.name}")

        # Запускаем в фоновом потоке
        thread = threading.Thread(
            target=_run_pipeline_background,
            args=(task.id, pipeline, devices, creds, netbox_config, body.dry_run),
            daemon=True,
        )
        thread.start()

        return PipelineRunResponse(
            pipeline_id=pipeline_id,
            status="running",
            steps=[],
            total_duration_ms=0,
            task_id=task.id,
        )

    # Sync mode - выполняем и возвращаем результат
    executor = PipelineExecutor(
        pipeline,
        dry_run=body.dry_run,
    )

    result = executor.run(
        devices=devices,
        credentials=creds,
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
                data=s.data,
            )
            for s in result.steps
        ],
        total_duration_ms=result.total_duration_ms,
    )
