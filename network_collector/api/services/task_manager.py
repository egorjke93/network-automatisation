"""
TaskManager - отслеживание прогресса длительных задач.

Позволяет отслеживать:
- Текущий статус задачи (pending, running, completed, failed)
- Прогресс (current/total)
- Текущий шаг (collect, sync, export)
- Детали по устройствам
"""

import time
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class TaskStatus(str, Enum):
    """Статус задачи."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskStep:
    """Шаг задачи."""
    name: str
    status: TaskStatus = TaskStatus.PENDING
    current: int = 0
    total: int = 0
    message: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "progress_percent": round(self.current / self.total * 100) if self.total > 0 else 0,
        }


@dataclass
class Task:
    """Задача с прогрессом."""
    id: str
    type: str  # collect, sync, pipeline, backup
    status: TaskStatus = TaskStatus.PENDING

    # Общий прогресс
    current_step: int = 0
    total_steps: int = 1

    # Детали текущего шага
    current_item: int = 0
    total_items: int = 0
    current_item_name: str = ""

    # Шаги
    steps: List[TaskStep] = field(default_factory=list)

    # Метаданные
    message: str = ""
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None

    # Время
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        elapsed_ms = 0
        if self.started_at:
            end = self.completed_at or datetime.now()
            elapsed_ms = int((end - self.started_at).total_seconds() * 1000)

        return {
            "id": self.id,
            "type": self.type,
            "status": self.status.value,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "current_item": self.current_item,
            "total_items": self.total_items,
            "current_item_name": self.current_item_name,
            "message": self.message,
            "error": self.error,
            "result": self.result,  # Добавлено - результат задачи
            "steps": [s.to_dict() for s in self.steps],
            "progress_percent": self._calculate_progress(),
            "elapsed_ms": elapsed_ms,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def _calculate_progress(self) -> int:
        """Вычисляет общий прогресс в процентах."""
        if self.total_steps == 0:
            return 0

        # Базовый прогресс по шагам
        step_progress = (self.current_step / self.total_steps) * 100

        # Добавляем прогресс внутри текущего шага
        if self.total_items > 0 and self.current_step < self.total_steps:
            item_progress = (self.current_item / self.total_items) * (100 / self.total_steps)
            step_progress += item_progress

        return min(100, round(step_progress))


class TaskManager:
    """
    Менеджер задач для отслеживания прогресса.

    Singleton, потокобезопасный.

    Usage:
        task = task_manager.create_task("collect", total_steps=2, total_items=10)

        task_manager.update_task(task.id, current_step=1, message="Collecting...")
        task_manager.update_item(task.id, current=1, name="10.0.0.1")
        task_manager.update_item(task.id, current=2, name="10.0.0.2")

        task_manager.complete_task(task.id, result={...})
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: Dict[str, Task] = {}
                    cls._instance._tasks_lock = threading.Lock()
        return cls._instance

    def create_task(
        self,
        task_type: str,
        total_steps: int = 1,
        total_items: int = 0,
        steps: Optional[List[str]] = None,
    ) -> Task:
        """
        Создаёт новую задачу.

        Args:
            task_type: Тип задачи (collect, sync, pipeline, backup)
            total_steps: Количество шагов
            total_items: Количество элементов (устройств)
            steps: Названия шагов

        Returns:
            Task: Созданная задача
        """
        task_id = str(uuid.uuid4())[:8]

        task_steps = []
        if steps:
            for name in steps:
                task_steps.append(TaskStep(name=name))

        task = Task(
            id=task_id,
            type=task_type,
            total_steps=total_steps,
            total_items=total_items,
            steps=task_steps,
        )

        with self._tasks_lock:
            self._tasks[task_id] = task
            # Cleanup старых задач (держим последние 100)
            if len(self._tasks) > 100:
                self._cleanup_old_tasks()

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Возвращает задачу по ID."""
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def start_task(self, task_id: str, message: str = "") -> None:
        """Запускает задачу."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()
                task.message = message

    def update_task(
        self,
        task_id: str,
        current_step: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        """Обновляет прогресс задачи."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task:
                if current_step is not None:
                    task.current_step = current_step
                if message is not None:
                    task.message = message

    def update_item(
        self,
        task_id: str,
        current: int,
        name: str = "",
        total: Optional[int] = None,
    ) -> None:
        """Обновляет прогресс по элементам."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task:
                task.current_item = current
                task.current_item_name = name
                if total is not None:
                    task.total_items = total
                # Автоматически обновляем сообщение
                if name and task.total_items > 0:
                    task.message = f"Обработка {name} ({current}/{task.total_items})"

    def start_step(self, task_id: str, step_index: int, total_items: int = 0) -> None:
        """Начинает шаг."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task and step_index < len(task.steps):
                task.current_step = step_index
                task.current_item = 0
                task.total_items = total_items
                step = task.steps[step_index]
                step.status = TaskStatus.RUNNING
                step.started_at = datetime.now()
                step.total = total_items

    def complete_step(self, task_id: str, step_index: int) -> None:
        """Завершает шаг."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task and step_index < len(task.steps):
                step = task.steps[step_index]
                step.status = TaskStatus.COMPLETED
                step.completed_at = datetime.now()
                step.current = step.total

    def complete_task(
        self,
        task_id: str,
        result: Optional[Dict[str, Any]] = None,
        message: str = "Completed",
    ) -> None:
        """Завершает задачу успешно."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                task.result = result
                task.message = message
                task.current_step = task.total_steps

    def fail_task(self, task_id: str, error: str) -> None:
        """Завершает задачу с ошибкой."""
        with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = error
                task.message = f"Failed: {error}"

    def get_all_tasks(self, limit: int = 20) -> List[Task]:
        """Возвращает последние задачи."""
        with self._tasks_lock:
            tasks = list(self._tasks.values())
            tasks.sort(key=lambda t: t.created_at, reverse=True)
            return tasks[:limit]

    def _cleanup_old_tasks(self) -> None:
        """Удаляет старые завершённые задачи."""
        completed = [
            (tid, t) for tid, t in self._tasks.items()
            if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
        ]
        completed.sort(key=lambda x: x[1].created_at)

        # Удаляем старые, оставляем 50
        to_remove = len(completed) - 50
        for i in range(max(0, to_remove)):
            del self._tasks[completed[i][0]]


# Глобальный экземпляр
task_manager = TaskManager()
