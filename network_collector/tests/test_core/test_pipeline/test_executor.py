"""
Тесты для PipelineExecutor.

Проверяет:
- Выполнение pipeline
- Обработка зависимостей
- Обработка ошибок
- Callbacks
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from network_collector.core.pipeline.models import (
    Pipeline,
    PipelineStep,
    StepType,
    StepStatus,
)
from network_collector.core.pipeline.executor import (
    PipelineExecutor,
    PipelineResult,
    StepResult,
)


@pytest.mark.unit
class TestPipelineExecutor:
    """Тесты для PipelineExecutor."""

    @pytest.fixture
    def simple_pipeline(self):
        """Простой pipeline для тестов."""
        return Pipeline(
            id="test",
            name="Test Pipeline",
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

    @pytest.fixture
    def mock_devices(self):
        """Мок устройств."""
        return [
            Mock(host="10.0.0.1", platform="cisco_ios"),
            Mock(host="10.0.0.2", platform="cisco_ios"),
        ]

    def test_executor_init(self, simple_pipeline):
        """Инициализация executor."""
        executor = PipelineExecutor(simple_pipeline)
        assert executor.pipeline == simple_pipeline
        assert executor.dry_run is False

    def test_executor_dry_run_mode(self, simple_pipeline):
        """Executor в dry-run режиме."""
        executor = PipelineExecutor(simple_pipeline, dry_run=True)
        assert executor.dry_run is True

    def test_run_validates_pipeline(self):
        """Run валидирует pipeline перед выполнением."""
        invalid_pipeline = Pipeline(
            id="",  # Invalid: empty id
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
            ],
        )
        executor = PipelineExecutor(invalid_pipeline)
        result = executor.run(devices=[])

        assert result.status == StepStatus.FAILED
        assert len(result.steps) == 1
        assert "validation" in result.steps[0].step_id
        assert result.steps[0].error is not None

    def test_run_empty_devices(self, simple_pipeline):
        """Выполнение с пустым списком устройств."""
        executor = PipelineExecutor(simple_pipeline)
        result = executor.run(devices=[])

        assert result.pipeline_id == "test"
        # Должен завершиться (пусть и с пустыми результатами)
        assert result.status in (StepStatus.COMPLETED, StepStatus.FAILED)

    def test_run_executes_steps_in_order(self, simple_pipeline, mock_devices):
        """Шаги выполняются в правильном порядке."""
        executed_steps = []

        def on_step_start(step):
            executed_steps.append(step.id)

        executor = PipelineExecutor(
            simple_pipeline,
            on_step_start=on_step_start,
        )
        executor.run(devices=mock_devices)

        assert executed_steps == ["collect_devices", "sync_devices"]

    def test_run_skips_disabled_steps(self, mock_devices):
        """Отключённые шаги пропускаются."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices", enabled=True),
                PipelineStep(id="s2", type=StepType.COLLECT, target="interfaces", enabled=False),
                PipelineStep(id="s3", type=StepType.COLLECT, target="mac", enabled=True),
            ],
        )

        executed_steps = []

        def on_step_start(step):
            executed_steps.append(step.id)

        executor = PipelineExecutor(pipeline, on_step_start=on_step_start)
        executor.run(devices=mock_devices)

        assert executed_steps == ["s1", "s3"]

    def test_run_respects_dependencies(self, mock_devices):
        """Шаги с невыполненными зависимостями пропускаются."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                # Collect шаги нужны для sync
                PipelineStep(
                    id="collect_devices",
                    type=StepType.COLLECT,
                    target="devices",
                    enabled=True,
                ),
                PipelineStep(
                    id="collect_interfaces",
                    type=StepType.COLLECT,
                    target="interfaces",
                    enabled=True,
                ),
                # Первый sync — disabled, поэтому не выполнится
                PipelineStep(
                    id="sync_devices",
                    type=StepType.SYNC,
                    target="devices",
                    enabled=False,  # Отключён
                ),
                PipelineStep(
                    id="sync_interfaces",
                    type=StepType.SYNC,
                    target="interfaces",
                    depends_on=["sync_devices"],  # Зависит от отключённого шага
                ),
            ],
        )

        executor = PipelineExecutor(pipeline)
        result = executor.run(devices=mock_devices)

        # sync_interfaces должен быть SKIPPED (зависимость не выполнена)
        sync_interfaces_result = next(
            (s for s in result.steps if s.step_id == "sync_interfaces"), None
        )
        assert sync_interfaces_result is not None
        assert sync_interfaces_result.status == StepStatus.SKIPPED
        assert "Dependencies not met" in sync_interfaces_result.error

    def test_callbacks_called(self, simple_pipeline, mock_devices):
        """Callbacks вызываются."""
        on_start = Mock()
        on_complete = Mock()

        executor = PipelineExecutor(
            simple_pipeline,
            on_step_start=on_start,
            on_step_complete=on_complete,
        )
        executor.run(devices=mock_devices)

        assert on_start.call_count == 2  # 2 шага
        assert on_complete.call_count == 2

    def test_result_contains_duration(self, simple_pipeline, mock_devices):
        """Результат содержит время выполнения."""
        executor = PipelineExecutor(simple_pipeline)
        result = executor.run(devices=mock_devices)

        assert result.total_duration_ms >= 0
        for step_result in result.steps:
            assert step_result.duration_ms >= 0

    def test_result_to_dict(self, simple_pipeline, mock_devices):
        """Результат сериализуется в словарь."""
        executor = PipelineExecutor(simple_pipeline)
        result = executor.run(devices=mock_devices)

        result_dict = result.to_dict()
        assert "pipeline_id" in result_dict
        assert "status" in result_dict
        assert "steps" in result_dict
        assert "total_duration_ms" in result_dict


@pytest.mark.unit
class TestPipelineExecutorSteps:
    """Тесты выполнения конкретных типов шагов."""

    @pytest.fixture
    def mock_devices(self):
        """Мок устройств."""
        return [Mock(host="10.0.0.1", platform="cisco_ios")]

    def test_collect_step_stores_data_in_context(self, mock_devices):
        """Collect шаг сохраняет данные в контекст."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="collect", type=StepType.COLLECT, target="devices"),
            ],
        )

        executor = PipelineExecutor(pipeline)

        # Мокаем _execute_collect с side_effect, который также сохраняет в контекст
        collected_data = {"target": "devices", "data": [{"hostname": "switch1"}], "count": 1}

        def mock_execute_collect(step):
            # Сохраняем в контекст как настоящий метод
            executor._context["collected_data"][step.target] = collected_data
            return collected_data

        with patch.object(executor, '_execute_collect', side_effect=mock_execute_collect):
            executor.run(
                devices=mock_devices,
                credentials={"username": "admin", "password": "secret"},
            )

        # Данные должны быть в контексте
        assert "devices" in executor._context["collected_data"]

    def test_sync_step_uses_dry_run(self, mock_devices):
        """Sync шаг использует dry_run из контекста."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="collect", type=StepType.COLLECT, target="devices"),
                PipelineStep(id="sync", type=StepType.SYNC, target="devices"),
            ],
        )

        executor = PipelineExecutor(pipeline, dry_run=True)
        result = executor.run(devices=mock_devices)

        # Проверяем что dry_run передан в контекст
        assert executor._context.get("dry_run") is True


@pytest.mark.unit
class TestPipelineExecutorErrorHandling:
    """Тесты обработки ошибок."""

    @pytest.fixture
    def mock_devices(self):
        """Мок устройств."""
        return [Mock(host="10.0.0.1", platform="cisco_ios")]

    def test_step_failure_stops_pipeline(self, mock_devices):
        """При ошибке шага pipeline останавливается."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
                PipelineStep(id="s2", type=StepType.COLLECT, target="interfaces"),
            ],
        )

        executor = PipelineExecutor(pipeline)

        # Мокаем _execute_step чтобы первый шаг фейлился
        original_execute = executor._execute_step

        def failing_execute(step):
            if step.id == "s1":
                return StepResult(
                    step_id=step.id,
                    status=StepStatus.FAILED,
                    error="Test error",
                )
            return original_execute(step)

        executor._execute_step = failing_execute

        result = executor.run(devices=mock_devices)

        assert result.status == StepStatus.FAILED
        # Второй шаг не должен выполняться
        assert len([s for s in result.steps if s.status == StepStatus.FAILED]) == 1

    def test_exception_in_step_is_caught(self, mock_devices):
        """Исключение в шаге перехватывается."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
            ],
        )

        executor = PipelineExecutor(pipeline)

        # Мокаем _execute_collect чтобы бросало исключение
        def raising_collect(step):
            raise RuntimeError("Test exception")

        executor._execute_collect = raising_collect

        result = executor.run(devices=mock_devices)

        assert result.status == StepStatus.FAILED
        assert result.steps[0].status == StepStatus.FAILED
        assert "Test exception" in result.steps[0].error


@pytest.mark.unit
class TestStepResult:
    """Тесты для StepResult."""

    def test_create_step_result(self):
        """Создание StepResult."""
        result = StepResult(
            step_id="test",
            status=StepStatus.COMPLETED,
            data={"key": "value"},
            duration_ms=100,
        )
        assert result.step_id == "test"
        assert result.status == StepStatus.COMPLETED
        assert result.data == {"key": "value"}
        assert result.duration_ms == 100

    def test_step_result_with_error(self):
        """StepResult с ошибкой."""
        result = StepResult(
            step_id="test",
            status=StepStatus.FAILED,
            error="Something went wrong",
        )
        assert result.status == StepStatus.FAILED
        assert result.error == "Something went wrong"


@pytest.mark.unit
class TestPipelineResult:
    """Тесты для PipelineResult."""

    def test_create_pipeline_result(self):
        """Создание PipelineResult."""
        result = PipelineResult(
            pipeline_id="test",
            status=StepStatus.COMPLETED,
            steps=[
                StepResult(step_id="s1", status=StepStatus.COMPLETED),
                StepResult(step_id="s2", status=StepStatus.COMPLETED),
            ],
            total_duration_ms=500,
        )
        assert result.pipeline_id == "test"
        assert len(result.steps) == 2
        assert result.total_duration_ms == 500

    def test_pipeline_result_to_dict(self):
        """Сериализация PipelineResult."""
        result = PipelineResult(
            pipeline_id="test",
            status=StepStatus.COMPLETED,
            steps=[
                StepResult(step_id="s1", status=StepStatus.COMPLETED, duration_ms=100),
            ],
            total_duration_ms=100,
        )
        result_dict = result.to_dict()

        assert result_dict["pipeline_id"] == "test"
        assert result_dict["status"] == "completed"
        assert len(result_dict["steps"]) == 1
        assert result_dict["steps"][0]["step_id"] == "s1"
