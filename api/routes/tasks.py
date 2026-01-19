"""
Tasks API - получение статуса и прогресса задач.

Endpoints:
- GET /api/tasks - список всех задач
- GET /api/tasks/{task_id} - статус конкретной задачи
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.task_manager import task_manager, TaskStatus

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskStepResponse(BaseModel):
    """Шаг задачи."""
    name: str
    status: str
    current: int
    total: int
    message: str
    progress_percent: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskResponse(BaseModel):
    """Ответ с информацией о задаче."""
    id: str
    type: str
    status: str
    current_step: int
    total_steps: int
    current_item: int
    total_items: int
    current_item_name: str
    message: str
    error: Optional[str] = None
    result: Optional[dict] = None  # Результат выполнения задачи
    steps: List[TaskStepResponse] = []
    progress_percent: int
    elapsed_ms: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskListResponse(BaseModel):
    """Список задач."""
    tasks: List[TaskResponse]
    total: int


@router.get("", response_model=TaskListResponse)
async def get_tasks(limit: int = 20):
    """
    Получить список последних задач.

    Args:
        limit: Максимальное количество задач (default: 20)

    Returns:
        TaskListResponse: Список задач
    """
    tasks = task_manager.get_all_tasks(limit=limit)
    return TaskListResponse(
        tasks=[TaskResponse(**t.to_dict()) for t in tasks],
        total=len(tasks),
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """
    Получить статус задачи по ID.

    Args:
        task_id: ID задачи

    Returns:
        TaskResponse: Информация о задаче

    Raises:
        404: Задача не найдена
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return TaskResponse(**task.to_dict())


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """
    Отменить задачу (если она ещё выполняется).

    Args:
        task_id: ID задачи

    Returns:
        dict: Результат операции
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if task.status == TaskStatus.RUNNING:
        task_manager.fail_task(task_id, "Cancelled by user")
        return {"status": "cancelled", "task_id": task_id}

    return {"status": "already_finished", "task_id": task_id}
