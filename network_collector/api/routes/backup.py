"""Backup routes - резервное копирование конфигураций."""

import io
import zipfile
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from ..schemas import BackupRequest, BackupResponse, Credentials
from .auth import get_credentials_from_headers
from ..services.collector_service import CollectorService
from ..services.task_manager import task_manager

router = APIRouter()


@router.post(
    "/run",
    response_model=BackupResponse,
    summary="Выполнить backup конфигураций",
)
async def run_backup(
    request: Request,
    body: BackupRequest,
):
    """
    Выполняет резервное копирование конфигураций.

    Credentials передаются в headers: X-SSH-Username, X-SSH-Password

    Сохраняет running-config в файлы.
    """
    credentials = get_credentials_from_headers(request)
    service = CollectorService(credentials)
    return await service.run_backup(body)


@router.get(
    "/download/{task_id}",
    summary="Скачать backup как ZIP",
)
async def download_backup(task_id: str):
    """
    Скачивает все конфиги из backup как ZIP-архив.

    Args:
        task_id: ID задачи backup
    """
    # Получаем задачу
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if task.status != "completed":
        raise HTTPException(status_code=400, detail=f"Задача не завершена: {task.status}")

    # Получаем папку с бэкапами из результата
    output_folder = task.result.get("output_folder") if task.result else None
    if not output_folder:
        raise HTTPException(status_code=400, detail="Папка backup не найдена в результате задачи")

    folder_path = Path(output_folder)
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail=f"Папка не существует: {output_folder}")

    # Собираем все .cfg файлы
    config_files = list(folder_path.glob("*.cfg"))
    if not config_files:
        raise HTTPException(status_code=404, detail="Конфигурационные файлы не найдены")

    # Создаём ZIP в памяти
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for cfg_file in config_files:
            zip_file.write(cfg_file, cfg_file.name)

    zip_buffer.seek(0)

    # Имя файла: backup_2026-01-18.zip (только дата)
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"backup_{date_str}.zip"

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
