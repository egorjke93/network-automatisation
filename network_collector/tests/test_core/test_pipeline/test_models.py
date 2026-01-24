"""
Тесты для Pipeline моделей.

Проверяет:
- Создание Pipeline и PipelineStep
- Валидация
- Сериализация/десериализация
- Загрузка из YAML
"""

import pytest
import tempfile
from pathlib import Path

from network_collector.core.pipeline.models import (
    Pipeline,
    PipelineStep,
    StepType,
    StepStatus,
    AVAILABLE_COLLECTORS,
    AVAILABLE_SYNC_TARGETS,
)


@pytest.mark.unit
class TestPipelineStep:
    """Тесты для PipelineStep."""

    def test_create_collect_step(self):
        """Создание шага collect."""
        step = PipelineStep(
            id="collect_devices",
            type=StepType.COLLECT,
            target="devices",
        )
        assert step.id == "collect_devices"
        assert step.type == StepType.COLLECT
        assert step.target == "devices"
        assert step.enabled is True
        assert step.status == StepStatus.PENDING

    def test_create_sync_step(self):
        """Создание шага sync."""
        step = PipelineStep(
            id="sync_interfaces",
            type=StepType.SYNC,
            target="interfaces",
            options={"sync_mac": True},
            depends_on=["sync_devices"],
        )
        assert step.type == StepType.SYNC
        assert step.options == {"sync_mac": True}
        assert step.depends_on == ["sync_devices"]

    def test_step_from_dict(self):
        """Создание шага из словаря."""
        data = {
            "id": "test_step",
            "type": "collect",
            "target": "interfaces",
            "enabled": True,
            "options": {"key": "value"},
        }
        step = PipelineStep.from_dict(data)
        assert step.id == "test_step"
        assert step.type == StepType.COLLECT
        assert step.target == "interfaces"
        assert step.options == {"key": "value"}

    def test_step_to_dict(self):
        """Сериализация шага в словарь."""
        step = PipelineStep(
            id="test",
            type=StepType.SYNC,
            target="devices",
            options={"create": True},
        )
        result = step.to_dict()
        assert result["id"] == "test"
        assert result["type"] == "sync"
        assert result["target"] == "devices"
        assert result["options"] == {"create": True}
        assert result["status"] == "pending"

    def test_validate_valid_collect_step(self):
        """Валидация валидного collect шага."""
        step = PipelineStep(
            id="collect_mac",
            type=StepType.COLLECT,
            target="mac",
        )
        errors = step.validate()
        assert errors == []

    def test_validate_invalid_collector(self):
        """Валидация с неизвестным collector."""
        step = PipelineStep(
            id="collect_unknown",
            type=StepType.COLLECT,
            target="unknown_collector",
        )
        errors = step.validate()
        assert len(errors) == 1
        assert "Unknown collector" in errors[0]

    def test_validate_invalid_sync_target(self):
        """Валидация с неизвестным sync target."""
        step = PipelineStep(
            id="sync_unknown",
            type=StepType.SYNC,
            target="unknown_target",
        )
        errors = step.validate()
        assert len(errors) == 1
        assert "Unknown sync target" in errors[0]

    def test_validate_empty_id(self):
        """Валидация без id."""
        step = PipelineStep(
            id="",
            type=StepType.COLLECT,
            target="devices",
        )
        errors = step.validate()
        assert "Step id is required" in errors

    @pytest.mark.parametrize("collector", list(AVAILABLE_COLLECTORS))
    def test_all_collectors_valid(self, collector):
        """Все доступные collectors проходят валидацию."""
        step = PipelineStep(
            id=f"collect_{collector}",
            type=StepType.COLLECT,
            target=collector,
        )
        errors = step.validate()
        assert errors == [], f"Collector '{collector}' should be valid"

    @pytest.mark.parametrize("target", list(AVAILABLE_SYNC_TARGETS))
    def test_all_sync_targets_valid(self, target):
        """Все доступные sync targets проходят валидацию."""
        step = PipelineStep(
            id=f"sync_{target}",
            type=StepType.SYNC,
            target=target,
        )
        errors = step.validate()
        assert errors == [], f"Sync target '{target}' should be valid"


@pytest.mark.unit
class TestPipeline:
    """Тесты для Pipeline."""

    @pytest.fixture
    def simple_pipeline(self):
        """Простой pipeline для тестов."""
        return Pipeline(
            id="test",
            name="Test Pipeline",
            description="Test description",
            steps=[
                PipelineStep(
                    id="collect_devices",
                    type=StepType.COLLECT,
                    target="devices",
                ),
                PipelineStep(
                    id="sync_devices",
                    type=StepType.SYNC,
                    target="devices",
                    depends_on=["collect_devices"],
                ),
            ],
        )

    def test_create_pipeline(self, simple_pipeline):
        """Создание pipeline."""
        assert simple_pipeline.id == "test"
        assert simple_pipeline.name == "Test Pipeline"
        assert len(simple_pipeline.steps) == 2
        assert simple_pipeline.status == StepStatus.PENDING

    def test_pipeline_from_dict(self):
        """Создание pipeline из словаря."""
        data = {
            "id": "from_dict",
            "name": "From Dict Pipeline",
            "description": "Created from dict",
            "steps": [
                {"id": "step1", "type": "collect", "target": "devices"},
            ],
        }
        pipeline = Pipeline.from_dict(data)
        assert pipeline.id == "from_dict"
        assert len(pipeline.steps) == 1
        assert pipeline.steps[0].id == "step1"

    def test_pipeline_to_dict(self, simple_pipeline):
        """Сериализация pipeline в словарь."""
        result = simple_pipeline.to_dict()
        assert result["id"] == "test"
        assert result["name"] == "Test Pipeline"
        assert len(result["steps"]) == 2
        assert result["status"] == "pending"

    def test_validate_valid_pipeline(self, simple_pipeline):
        """Валидация валидного pipeline."""
        errors = simple_pipeline.validate()
        assert errors == []

    def test_validate_empty_id(self):
        """Валидация pipeline без id."""
        pipeline = Pipeline(
            id="",
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
            ],
        )
        errors = pipeline.validate()
        assert "Pipeline id is required" in errors

    def test_validate_empty_name(self):
        """Валидация pipeline без name."""
        pipeline = Pipeline(
            id="test",
            name="",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
            ],
        )
        errors = pipeline.validate()
        assert "Pipeline name is required" in errors

    def test_validate_no_steps(self):
        """Валидация pipeline без шагов."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[],
        )
        errors = pipeline.validate()
        assert "Pipeline must have at least one step" in errors

    def test_validate_duplicate_step_ids(self):
        """Валидация pipeline с дубликатами step id."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="same_id", type=StepType.COLLECT, target="devices"),
                PipelineStep(id="same_id", type=StepType.SYNC, target="devices"),
            ],
        )
        errors = pipeline.validate()
        assert any("Duplicate step id" in e for e in errors)

    def test_validate_unknown_dependency(self):
        """Валидация pipeline с неизвестной зависимостью."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(
                    id="step1",
                    type=StepType.COLLECT,
                    target="devices",
                    depends_on=["unknown_step"],
                ),
            ],
        )
        errors = pipeline.validate()
        assert any("depends on unknown step" in e for e in errors)

    def test_validate_sync_dependencies(self):
        """Валидация что sync interfaces требует sync devices."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.SYNC, target="interfaces"),
            ],
        )
        errors = pipeline.validate()
        assert any("requires sync 'devices'" in e for e in errors)

    def test_validate_sync_cables_requires_interfaces(self):
        """Валидация что sync cables требует sync interfaces."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.SYNC, target="devices"),
                PipelineStep(id="s2", type=StepType.SYNC, target="cables"),
            ],
        )
        errors = pipeline.validate()
        assert any("requires sync 'interfaces'" in e for e in errors)

    def test_get_enabled_steps(self):
        """Получение только включённых шагов."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices", enabled=True),
                PipelineStep(id="s2", type=StepType.COLLECT, target="interfaces", enabled=False),
                PipelineStep(id="s3", type=StepType.COLLECT, target="mac", enabled=True),
            ],
        )
        enabled = pipeline.get_enabled_steps()
        assert len(enabled) == 2
        assert enabled[0].id == "s1"
        assert enabled[1].id == "s3"

    def test_get_step_by_id(self, simple_pipeline):
        """Поиск шага по id."""
        step = simple_pipeline.get_step_by_id("collect_devices")
        assert step is not None
        assert step.id == "collect_devices"

        unknown = simple_pipeline.get_step_by_id("unknown")
        assert unknown is None

    def test_reset_status(self, simple_pipeline):
        """Сброс статусов шагов."""
        # Имитируем выполнение
        simple_pipeline.status = StepStatus.COMPLETED
        simple_pipeline.steps[0].status = StepStatus.COMPLETED
        simple_pipeline.steps[1].status = StepStatus.FAILED
        simple_pipeline.steps[1].error = "Some error"

        simple_pipeline.reset_status()

        assert simple_pipeline.status == StepStatus.PENDING
        assert simple_pipeline.steps[0].status == StepStatus.PENDING
        assert simple_pipeline.steps[1].status == StepStatus.PENDING
        assert simple_pipeline.steps[1].error is None


@pytest.mark.unit
class TestPipelineYAML:
    """Тесты загрузки/сохранения YAML."""

    def test_from_yaml(self):
        """Загрузка pipeline из YAML."""
        yaml_content = """
id: yaml_test
name: "YAML Test Pipeline"
description: "Loaded from YAML"
steps:
  - id: step1
    type: collect
    target: devices
  - id: step2
    type: sync
    target: devices
    depends_on:
      - step1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            pipeline = Pipeline.from_yaml(f.name)

        assert pipeline.id == "yaml_test"
        assert pipeline.name == "YAML Test Pipeline"
        assert len(pipeline.steps) == 2
        assert pipeline.steps[1].depends_on == ["step1"]

    def test_to_yaml(self):
        """Сохранение pipeline в YAML."""
        pipeline = Pipeline(
            id="save_test",
            name="Save Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
            ],
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            pipeline.to_yaml(f.name)

            # Загружаем обратно и проверяем
            loaded = Pipeline.from_yaml(f.name)

        assert loaded.id == "save_test"
        assert loaded.name == "Save Test"
        assert len(loaded.steps) == 1

    def test_load_default_pipeline(self):
        """Загрузка дефолтного pipeline."""
        default_path = Path(__file__).parent.parent.parent.parent.parent / "pipelines" / "default.yaml"
        if default_path.exists():
            pipeline = Pipeline.from_yaml(str(default_path))
            errors = pipeline.validate()
            assert errors == [], f"Default pipeline has errors: {errors}"
            assert pipeline.id == "default"
            assert len(pipeline.steps) >= 1
