"""
Тесты для Tasks API и TaskManager.
"""

import pytest
from fastapi.testclient import TestClient

from network_collector.api.main import app
from network_collector.api.services.task_manager import (
    TaskManager,
    TaskStatus,
    Task,
    task_manager,
)


class TestTaskManager:
    """Тесты TaskManager."""

    def test_create_task(self):
        """Тест создания задачи."""
        task = task_manager.create_task(
            task_type="test",
            total_steps=3,
            total_items=10,
        )

        assert task.id is not None
        assert task.type == "test"
        assert task.status == TaskStatus.PENDING
        assert task.total_steps == 3
        assert task.total_items == 10

    def test_start_task(self):
        """Тест запуска задачи."""
        task = task_manager.create_task(task_type="test")
        task_manager.start_task(task.id, "Starting...")

        updated = task_manager.get_task(task.id)
        assert updated.status == TaskStatus.RUNNING
        assert updated.message == "Starting..."
        assert updated.started_at is not None

    def test_update_task_progress(self):
        """Тест обновления прогресса."""
        task = task_manager.create_task(task_type="test", total_steps=3)
        task_manager.start_task(task.id)
        task_manager.update_task(task.id, current_step=1, message="Step 1")

        updated = task_manager.get_task(task.id)
        assert updated.current_step == 1
        assert updated.message == "Step 1"

    def test_update_item_progress(self):
        """Тест обновления прогресса по элементам."""
        task = task_manager.create_task(task_type="test", total_items=10)
        task_manager.start_task(task.id)
        task_manager.update_item(task.id, current=5, name="Device-5")

        updated = task_manager.get_task(task.id)
        assert updated.current_item == 5
        assert updated.current_item_name == "Device-5"

    def test_complete_task(self):
        """Тест завершения задачи."""
        task = task_manager.create_task(task_type="test")
        task_manager.start_task(task.id)
        task_manager.complete_task(task.id, result={"count": 10}, message="Done")

        updated = task_manager.get_task(task.id)
        assert updated.status == TaskStatus.COMPLETED
        assert updated.result == {"count": 10}
        assert updated.message == "Done"
        assert updated.completed_at is not None

    def test_fail_task(self):
        """Тест завершения задачи с ошибкой."""
        task = task_manager.create_task(task_type="test")
        task_manager.start_task(task.id)
        task_manager.fail_task(task.id, "Connection failed")

        updated = task_manager.get_task(task.id)
        assert updated.status == TaskStatus.FAILED
        assert updated.error == "Connection failed"
        assert "Failed" in updated.message

    def test_get_all_tasks(self):
        """Тест получения всех задач."""
        # Создаём несколько задач
        for i in range(5):
            task_manager.create_task(task_type=f"test_{i}")

        tasks = task_manager.get_all_tasks(limit=5)
        assert len(tasks) <= 5

    def test_task_progress_calculation(self):
        """Тест вычисления прогресса."""
        task = task_manager.create_task(
            task_type="test",
            total_steps=2,
            total_items=10,
        )
        task_manager.start_task(task.id)

        # 0 step, 0 items = 0%
        assert task._calculate_progress() == 0

        # Complete step 1 of 2 = 50%
        task.current_step = 1
        assert task._calculate_progress() == 50

        # Complete step 2 of 2 = 100%
        task.current_step = 2
        assert task._calculate_progress() == 100

    def test_task_with_steps(self):
        """Тест задачи с именованными шагами."""
        task = task_manager.create_task(
            task_type="sync",
            total_steps=3,
            steps=["Devices", "Interfaces", "Cables"],
        )

        assert len(task.steps) == 3
        assert task.steps[0].name == "Devices"
        assert task.steps[1].name == "Interfaces"
        assert task.steps[2].name == "Cables"

    def test_start_and_complete_step(self):
        """Тест начала и завершения шага."""
        task = task_manager.create_task(
            task_type="sync",
            total_steps=2,
            steps=["Step1", "Step2"],
        )
        task_manager.start_task(task.id)

        # Start step 0
        task_manager.start_step(task.id, step_index=0, total_items=5)
        updated = task_manager.get_task(task.id)
        assert updated.steps[0].status == TaskStatus.RUNNING
        assert updated.steps[0].total == 5

        # Complete step 0
        task_manager.complete_step(task.id, step_index=0)
        updated = task_manager.get_task(task.id)
        assert updated.steps[0].status == TaskStatus.COMPLETED

    def test_task_to_dict(self):
        """Тест сериализации задачи."""
        task = task_manager.create_task(task_type="test", total_steps=1)
        task_manager.start_task(task.id, "Test message")

        data = task.to_dict()

        assert "id" in data
        assert data["type"] == "test"
        assert data["status"] == "running"
        assert data["message"] == "Test message"
        assert "progress_percent" in data
        assert "elapsed_ms" in data
        assert "created_at" in data
        assert "started_at" in data


class TestTasksAPI:
    """Тесты API endpoints для tasks."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_tasks_list(self, client):
        """Тест получения списка задач."""
        # Создаём задачу
        task = task_manager.create_task(task_type="test_api")

        response = client.get("/api/tasks")
        assert response.status_code == 200

        data = response.json()
        assert "tasks" in data
        assert "total" in data
        assert isinstance(data["tasks"], list)

    def test_get_task_by_id(self, client):
        """Тест получения задачи по ID."""
        task = task_manager.create_task(task_type="test_get")
        task_manager.start_task(task.id, "Testing...")

        response = client.get(f"/api/tasks/{task.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == task.id
        assert data["type"] == "test_get"
        assert data["status"] == "running"
        assert data["message"] == "Testing..."

    def test_get_task_not_found(self, client):
        """Тест получения несуществующей задачи."""
        response = client.get("/api/tasks/nonexistent")
        assert response.status_code == 404

    def test_cancel_running_task(self, client):
        """Тест отмены запущенной задачи."""
        task = task_manager.create_task(task_type="test_cancel")
        task_manager.start_task(task.id)

        response = client.delete(f"/api/tasks/{task.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "cancelled"

        # Проверяем, что задача помечена как failed
        updated = task_manager.get_task(task.id)
        assert updated.status == TaskStatus.FAILED

    def test_cancel_completed_task(self, client):
        """Тест отмены уже завершённой задачи."""
        task = task_manager.create_task(task_type="test_cancel_done")
        task_manager.start_task(task.id)
        task_manager.complete_task(task.id)

        response = client.delete(f"/api/tasks/{task.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "already_finished"

    def test_cancel_task_not_found(self, client):
        """Тест отмены несуществующей задачи."""
        response = client.delete("/api/tasks/nonexistent")
        assert response.status_code == 404

    def test_tasks_list_limit(self, client):
        """Тест лимита списка задач."""
        # Создаём несколько задач
        for i in range(5):
            task_manager.create_task(task_type=f"test_limit_{i}")

        response = client.get("/api/tasks?limit=3")
        assert response.status_code == 200

        data = response.json()
        assert len(data["tasks"]) <= 3

    def test_task_response_schema(self, client):
        """Тест схемы ответа задачи."""
        task = task_manager.create_task(
            task_type="test_schema",
            total_steps=2,
            total_items=5,
            steps=["Step1", "Step2"],
        )
        task_manager.start_task(task.id)

        response = client.get(f"/api/tasks/{task.id}")
        assert response.status_code == 200

        data = response.json()

        # Проверяем обязательные поля
        required_fields = [
            "id", "type", "status", "current_step", "total_steps",
            "current_item", "total_items", "current_item_name",
            "message", "steps", "progress_percent", "elapsed_ms",
            "created_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"

        # Проверяем steps
        assert len(data["steps"]) == 2
        step = data["steps"][0]
        assert "name" in step
        assert "status" in step
        assert "progress_percent" in step


class TestTaskManagerSingleton:
    """Тесты синглтона TaskManager."""

    def test_singleton_pattern(self):
        """Тест паттерна синглтон."""
        tm1 = TaskManager()
        tm2 = TaskManager()
        assert tm1 is tm2

    def test_global_instance(self):
        """Тест глобального экземпляра."""
        from network_collector.api.services.task_manager import task_manager
        assert task_manager is not None
        assert isinstance(task_manager, TaskManager)
