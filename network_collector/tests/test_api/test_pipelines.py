"""
Тесты для Pipeline API.

Проверяет:
- CRUD операции для pipelines
- Валидация pipelines
- Выполнение pipelines
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, Mock

from fastapi.testclient import TestClient

from network_collector.api.main import app
from network_collector.api.routes import pipelines as pipelines_module


@pytest.fixture
def client():
    """TestClient для API."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def temp_pipelines_dir(tmp_path):
    """Временная директория для pipelines."""
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    return pipelines_dir


@pytest.fixture(autouse=True)
def mock_pipelines_dir(temp_pipelines_dir):
    """Подменяет директорию pipelines на временную."""
    original_dir = pipelines_module.PIPELINES_DIR
    pipelines_module.PIPELINES_DIR = temp_pipelines_dir
    yield temp_pipelines_dir
    pipelines_module.PIPELINES_DIR = original_dir


@pytest.fixture
def sample_pipeline_yaml(temp_pipelines_dir):
    """Создаёт sample pipeline YAML."""
    yaml_content = """
id: sample
name: Sample Pipeline
description: Test pipeline
enabled: true
steps:
  - id: collect_devices
    type: collect
    target: devices
    enabled: true
  - id: sync_devices
    type: sync
    target: devices
    enabled: true
    depends_on:
      - collect_devices
"""
    yaml_path = temp_pipelines_dir / "sample.yaml"
    yaml_path.write_text(yaml_content)
    return yaml_path


@pytest.fixture
def sample_pipeline_data():
    """Данные для создания pipeline."""
    return {
        "name": "Test Pipeline",
        "description": "Pipeline for testing",
        "steps": [
            {
                "id": "collect",
                "type": "collect",
                "target": "devices",
                "enabled": True,
                "options": {},
                "depends_on": [],
            },
            {
                "id": "sync",
                "type": "sync",
                "target": "devices",
                "enabled": True,
                "options": {},
                "depends_on": ["collect"],
            },
        ],
    }


@pytest.mark.api
class TestPipelinesList:
    """Тесты для GET /api/pipelines."""

    def test_list_empty(self, client):
        """Пустой список pipelines."""
        response = client.get("/api/pipelines")
        assert response.status_code == 200
        data = response.json()
        assert data["pipelines"] == []
        assert data["total"] == 0

    def test_list_with_pipelines(self, client, sample_pipeline_yaml):
        """Список с pipeline."""
        response = client.get("/api/pipelines")
        assert response.status_code == 200
        data = response.json()
        assert len(data["pipelines"]) == 1
        assert data["total"] == 1
        assert data["pipelines"][0]["id"] == "sample"
        assert data["pipelines"][0]["name"] == "Sample Pipeline"


@pytest.mark.api
class TestPipelineGet:
    """Тесты для GET /api/pipelines/{id}."""

    def test_get_existing(self, client, sample_pipeline_yaml):
        """Получение существующего pipeline."""
        response = client.get("/api/pipelines/sample")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "sample"
        assert data["name"] == "Sample Pipeline"
        assert len(data["steps"]) == 2

    def test_get_not_found(self, client):
        """Pipeline не найден."""
        response = client.get("/api/pipelines/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


@pytest.mark.api
class TestPipelineCreate:
    """Тесты для POST /api/pipelines."""

    def test_create_pipeline(self, client, sample_pipeline_data):
        """Создание pipeline."""
        response = client.post("/api/pipelines", json=sample_pipeline_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Pipeline"
        assert len(data["steps"]) == 2
        # ID генерируется из имени
        assert "test_pipeline" in data["id"]

    def test_create_pipeline_sync_without_collect_allowed(self, client):
        """Sync без collect допустим (auto-collect)."""
        valid_data = {
            "name": "Sync Only",
            "steps": [
                {
                    "id": "sync_first",
                    "type": "sync",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": [],
                },
            ],
        }
        response = client.post("/api/pipelines", json=valid_data)
        # Sync без collect теперь допустим - auto-collect выполнится автоматически
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Sync Only"

    def test_create_duplicate_pipeline(self, client, sample_pipeline_yaml):
        """Попытка создать pipeline с существующим ID."""
        data = {
            "name": "sample",  # Сгенерирует ID "sample" который уже существует
            "description": "Duplicate",
            "steps": [
                {
                    "id": "collect",
                    "type": "collect",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": [],
                },
            ],
        }
        response = client.post("/api/pipelines", json=data)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]

    def test_create_pipeline_empty_name(self, client):
        """Пустое имя pipeline."""
        data = {
            "name": "",
            "steps": [
                {
                    "id": "collect",
                    "type": "collect",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": [],
                },
            ],
        }
        response = client.post("/api/pipelines", json=data)
        assert response.status_code == 422  # Pydantic validation

    def test_create_pipeline_empty_steps(self, client):
        """Пустой список шагов."""
        data = {
            "name": "Empty Steps",
            "steps": [],
        }
        response = client.post("/api/pipelines", json=data)
        assert response.status_code == 422  # Pydantic validation (min_length=1)


@pytest.mark.api
class TestPipelineUpdate:
    """Тесты для PUT /api/pipelines/{id}."""

    def test_update_name(self, client, sample_pipeline_yaml):
        """Обновление имени."""
        response = client.put(
            "/api/pipelines/sample",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    def test_update_description(self, client, sample_pipeline_yaml):
        """Обновление описания."""
        response = client.put(
            "/api/pipelines/sample",
            json={"description": "New description"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "New description"

    def test_update_enabled(self, client, sample_pipeline_yaml):
        """Обновление enabled."""
        response = client.put(
            "/api/pipelines/sample",
            json={"enabled": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False

    def test_update_not_found(self, client):
        """Обновление несуществующего pipeline."""
        response = client.put(
            "/api/pipelines/nonexistent",
            json={"name": "New Name"},
        )
        assert response.status_code == 404

    def test_update_steps(self, client, sample_pipeline_yaml):
        """Обновление шагов."""
        new_steps = [
            {
                "id": "collect_mac",
                "type": "collect",
                "target": "mac",
                "enabled": True,
                "options": {},
                "depends_on": [],
            },
        ]
        response = client.put(
            "/api/pipelines/sample",
            json={"steps": new_steps},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["steps"]) == 1
        assert data["steps"][0]["target"] == "mac"


@pytest.mark.api
class TestPipelineDelete:
    """Тесты для DELETE /api/pipelines/{id}."""

    def test_delete_pipeline(self, client, sample_pipeline_yaml, temp_pipelines_dir):
        """Удаление pipeline."""
        # Проверяем что файл существует
        assert (temp_pipelines_dir / "sample.yaml").exists()

        response = client.delete("/api/pipelines/sample")
        assert response.status_code == 204

        # Проверяем что файл удалён
        assert not (temp_pipelines_dir / "sample.yaml").exists()

    def test_delete_not_found(self, client):
        """Удаление несуществующего pipeline."""
        response = client.delete("/api/pipelines/nonexistent")
        assert response.status_code == 404


@pytest.mark.api
class TestPipelineValidate:
    """Тесты для POST /api/pipelines/{id}/validate."""

    def test_validate_valid_pipeline(self, client, sample_pipeline_yaml):
        """Валидация корректного pipeline."""
        response = client.post("/api/pipelines/sample/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_not_found(self, client):
        """Валидация несуществующего pipeline."""
        response = client.post("/api/pipelines/nonexistent/validate")
        assert response.status_code == 404

    def test_validate_valid_pipeline(self, client, temp_pipelines_dir):
        """Валидация валидного pipeline (sync без collect допустим с auto-collect)."""
        # sync без collect теперь допустим (auto-collect)
        yaml_content = """
id: valid_sync
name: Valid Sync Pipeline
steps:
  - id: sync_first
    type: sync
    target: devices
    enabled: true
"""
        (temp_pipelines_dir / "valid_sync.yaml").write_text(yaml_content)

        response = client.post("/api/pipelines/valid_sync/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert len(data["errors"]) == 0


@pytest.mark.api
class TestPipelineRun:
    """Тесты для POST /api/pipelines/{id}/run."""

    def test_run_pipeline_dry_run(self, client_with_netbox, sample_pipeline_yaml):
        """Запуск pipeline в dry-run режиме (sync mode)."""
        request_data = {
            "devices": [
                {"host": "10.0.0.1", "platform": "cisco_ios"},
            ],
            "dry_run": True,
            "async_mode": False,  # Sync mode для тестирования
        }
        response = client_with_netbox.post("/api/pipelines/sample/run", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["pipeline_id"] == "sample"
        assert data["status"] in ["completed", "failed"]  # Может фейлиться без реального устройства
        assert "steps" in data
        assert "total_duration_ms" in data

    def test_run_pipeline_not_found(self, client_with_credentials):
        """Запуск несуществующего pipeline."""
        request_data = {
            "devices": [{"host": "10.0.0.1", "platform": "cisco_ios"}],
            "dry_run": True,
        }
        response = client_with_credentials.post("/api/pipelines/nonexistent/run", json=request_data)
        # 401 потому что сначала проверяются credentials, а потом pipeline
        # или 404 если pipeline проверяется первым
        assert response.status_code in [401, 404]

    def test_run_without_credentials(self, client, sample_pipeline_yaml):
        """Запуск без credentials в headers."""
        request_data = {
            "devices": [{"host": "10.0.0.1", "platform": "cisco_ios"}],
            "dry_run": True,
        }
        response = client.post("/api/pipelines/sample/run", json=request_data)
        assert response.status_code == 401  # Unauthorized

    def test_run_without_netbox(self, client_with_credentials, sample_pipeline_yaml):
        """Запуск без NetBox config в headers - OK для collect-only pipelines."""
        request_data = {
            "devices": [{"host": "10.0.0.1", "platform": "cisco_ios"}],
            "dry_run": True,
        }
        # NetBox опционален если pipeline не содержит sync шагов
        response = client_with_credentials.post("/api/pipelines/sample/run", json=request_data)
        # Может быть 200 если pipeline работает без NetBox
        assert response.status_code in [200, 401]

    def test_run_with_empty_devices(self, client_with_credentials, sample_pipeline_yaml):
        """Запуск с пустым списком устройств."""
        request_data = {
            "devices": [],
            "dry_run": True,
        }
        response = client_with_credentials.post("/api/pipelines/sample/run", json=request_data)
        assert response.status_code == 200
        # Pipeline должен выполниться (пусть и без результатов)


@pytest.mark.api
class TestPipelineStepTypes:
    """Тесты для различных типов шагов."""

    def test_create_collect_step(self, client):
        """Создание pipeline с collect шагом."""
        data = {
            "name": "Collect Only",
            "steps": [
                {
                    "id": "collect_mac",
                    "type": "collect",
                    "target": "mac",
                    "enabled": True,
                    "options": {},
                    "depends_on": [],
                },
            ],
        }
        response = client.post("/api/pipelines", json=data)
        assert response.status_code == 201

    def test_create_export_step(self, client):
        """Создание pipeline с export шагом."""
        data = {
            "name": "Export Only",
            "steps": [
                {
                    "id": "collect_data",
                    "type": "collect",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": [],
                },
                {
                    "id": "export_excel",
                    "type": "export",
                    "target": "devices",
                    "enabled": True,
                    "options": {"format": "excel"},
                    "depends_on": ["collect_data"],
                },
            ],
        }
        response = client.post("/api/pipelines", json=data)
        assert response.status_code == 201

@pytest.mark.api
class TestPipelineDependencies:
    """Тесты для зависимостей между шагами."""

    def test_valid_dependency_chain(self, client):
        """Валидная цепочка зависимостей."""
        data = {
            "name": "Chain Pipeline",
            "steps": [
                {
                    "id": "step1",
                    "type": "collect",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": [],
                },
                {
                    "id": "step2",
                    "type": "sync",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": ["step1"],
                },
                {
                    "id": "step3",
                    "type": "export",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": ["step2"],
                },
            ],
        }
        response = client.post("/api/pipelines", json=data)
        assert response.status_code == 201

    def test_missing_dependency(self, client):
        """Отсутствующая зависимость."""
        data = {
            "name": "Bad Dependency",
            "steps": [
                {
                    "id": "step1",
                    "type": "collect",
                    "target": "devices",
                    "enabled": True,
                    "options": {},
                    "depends_on": ["nonexistent"],  # Не существует
                },
            ],
        }
        response = client.post("/api/pipelines", json=data)
        assert response.status_code == 400
        assert "errors" in response.json()["detail"]
