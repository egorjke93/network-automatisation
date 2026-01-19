"""
Интеграционные тесты для PipelineExecutor.

Тестирует реальную интеграцию с collectors, sync и export
с использованием моков для внешних зависимостей.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import json

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


@pytest.mark.integration
class TestPipelineExecutorCollectIntegration:
    """Тесты интеграции с collectors."""

    @pytest.fixture
    def mock_devices(self):
        """Мок устройств."""
        return [
            Mock(host="10.0.0.1", platform="cisco_ios"),
            Mock(host="10.0.0.2", platform="cisco_ios"),
        ]

    @pytest.fixture
    def collect_pipeline(self):
        """Pipeline только с collect шагом."""
        return Pipeline(
            id="test_collect",
            name="Test Collect",
            steps=[
                PipelineStep(
                    id="collect_devices",
                    type=StepType.COLLECT,
                    target="devices",
                ),
            ],
        )

    def test_collect_calls_collector(self, collect_pipeline, mock_devices):
        """Collect шаг вызывает collector."""
        # Патчим весь модуль collectors
        with patch("network_collector.collectors.DeviceCollector") as MockCollector:
            mock_instance = MockCollector.return_value
            # Используем collect_dicts вместо collect
            mock_instance.collect_dicts.return_value = [
                {"hostname": "router1", "device_ip": "10.0.0.1", "platform": "cisco_ios"},
                {"hostname": "router2", "device_ip": "10.0.0.2", "platform": "cisco_ios"},
            ]

            executor = PipelineExecutor(collect_pipeline)
            result = executor.run(
                devices=mock_devices,
                credentials={"username": "admin", "password": "admin"},
            )

            # Collector должен быть вызван
            assert MockCollector.called
            assert mock_instance.collect_dicts.called

            # Проверяем результат
            assert result.status == StepStatus.COMPLETED
            assert len(result.steps) == 1
            assert result.steps[0].status == StepStatus.COMPLETED

    def test_collect_empty_devices_returns_empty_data(self, collect_pipeline):
        """Collect с пустым списком устройств возвращает пустые данные."""
        executor = PipelineExecutor(collect_pipeline)
        result = executor.run(devices=[], credentials={})

        assert result.status == StepStatus.COMPLETED
        # Контекст должен содержать пустые данные
        assert "devices" in executor._context["collected_data"]
        assert executor._context["collected_data"]["devices"]["count"] == 0

    def test_collect_stores_data_in_context(self, mock_devices):
        """Collect сохраняет данные в контекст."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="collect_mac", type=StepType.COLLECT, target="mac"),
            ],
        )

        with patch("network_collector.collectors.MACCollector") as MockCollector:
            mock_instance = MockCollector.return_value
            # Используем collect_dicts вместо collect
            mock_instance.collect_dicts.return_value = [
                {"mac": "aa:bb:cc:dd:ee:ff", "interface": "Gi0/1"},
            ]

            executor = PipelineExecutor(pipeline)
            executor.run(devices=mock_devices, credentials={})

            # Данные должны быть в контексте
            assert "mac" in executor._context["collected_data"]
            assert executor._context["collected_data"]["mac"]["count"] == 1
            assert len(executor._context["collected_data"]["mac"]["data"]) == 1


@pytest.mark.integration
class TestPipelineExecutorSyncIntegration:
    """Тесты интеграции с NetBox sync."""

    @pytest.fixture
    def sync_pipeline(self):
        """Pipeline с collect + sync."""
        return Pipeline(
            id="test_sync",
            name="Test Sync",
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
                    options={"site": "Office"},
                    depends_on=["collect_devices"],
                ),
            ],
        )

    def test_sync_requires_netbox_config(self, sync_pipeline):
        """Sync без NetBox config возвращает ошибку."""
        executor = PipelineExecutor(sync_pipeline)

        # Мокаем collect чтобы он возвращал данные
        original_collect = executor._execute_collect
        executor._execute_collect = Mock(return_value={
            "target": "devices",
            "data": [{"hostname": "test"}],
            "count": 1,
        })

        result = executor.run(
            devices=[Mock(host="10.0.0.1")],
            credentials={},
            netbox_config={},  # Пустой config
        )

        # Sync должен упасть
        assert result.status == StepStatus.FAILED
        sync_step = next(s for s in result.steps if s.step_id == "sync_devices")
        assert "NetBox URL and token are required" in sync_step.error

    def test_sync_calls_netbox_sync(self, sync_pipeline):
        """Sync вызывает NetBox sync."""
        executor = PipelineExecutor(sync_pipeline)

        # Мокаем collect чтобы заполнить контекст
        def mock_collect(step):
            data = [{"hostname": "router1", "device_ip": "10.0.0.1"}]
            executor._context["collected_data"]["devices"] = {
                "target": "devices",
                "data": data,
                "count": 1,
            }
            return {"target": "devices", "data": data, "count": 1}

        executor._execute_collect = mock_collect

        # Патчим NetBox
        with patch("network_collector.netbox.client.NetBoxClient"):
            with patch("network_collector.netbox.sync.NetBoxSync") as MockSync:
                mock_sync = MockSync.return_value
                mock_sync.sync_devices_from_inventory.return_value = {
                    "created": 1,
                    "updated": 0,
                    "skipped": 0,
                }

                result = executor.run(
                    devices=[Mock(host="10.0.0.1")],
                    credentials={},
                    netbox_config={"url": "http://netbox:8000", "token": "test-token"},
                )

                # Проверяем что sync был вызван
                assert mock_sync.sync_devices_from_inventory.called

                # Оба шага должны завершиться успешно
                assert result.status == StepStatus.COMPLETED

    def test_sync_no_data_returns_skipped(self):
        """Sync без данных возвращает skipped."""
        pipeline = Pipeline(
            id="test",
            name="Test",
            steps=[
                PipelineStep(id="collect", type=StepType.COLLECT, target="devices"),
                PipelineStep(id="sync", type=StepType.SYNC, target="devices", depends_on=["collect"]),
            ],
        )

        executor = PipelineExecutor(pipeline)

        # Мокаем collect с пустыми данными
        executor._execute_collect = Mock(return_value={
            "target": "devices",
            "data": [],
            "count": 0,
        })

        result = executor.run(
            devices=[Mock()],
            credentials={},
            netbox_config={"url": "http://netbox", "token": "tok"},
        )

        # Sync должен вернуть skipped
        sync_step = next(s for s in result.steps if s.step_id == "sync")
        assert sync_step.status == StepStatus.COMPLETED
        assert sync_step.data.get("skipped") is True


@pytest.mark.integration
class TestPipelineExecutorExportIntegration:
    """Тесты интеграции с exporters."""

    @pytest.fixture
    def export_pipeline(self):
        """Pipeline с collect + export."""
        return Pipeline(
            id="test_export",
            name="Test Export",
            steps=[
                PipelineStep(
                    id="collect_devices",
                    type=StepType.COLLECT,
                    target="devices",
                ),
                PipelineStep(
                    id="export_devices",
                    type=StepType.EXPORT,
                    target="devices",
                    options={"format": "json"},
                    depends_on=["collect_devices"],
                ),
            ],
        )

    def test_export_creates_json_file(self):
        """Export создаёт JSON файл."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pipeline = Pipeline(
                id="test",
                name="Test",
                steps=[
                    PipelineStep(id="collect", type=StepType.COLLECT, target="devices"),
                    PipelineStep(
                        id="export",
                        type=StepType.EXPORT,
                        target="devices",
                        options={"format": "json", "output_dir": tmpdir},
                        depends_on=["collect"],
                    ),
                ],
            )

            executor = PipelineExecutor(pipeline)

            # Мокаем collect чтобы вернуть данные и сохранить в контекст
            def mock_collect(step):
                data = [{"hostname": "router1", "ip": "10.0.0.1"}]
                executor._context["collected_data"]["devices"] = {
                    "target": "devices",
                    "data": data,
                    "count": 1,
                }
                return {"target": "devices", "data": data, "count": 1}

            executor._execute_collect = mock_collect

            result = executor.run(devices=[Mock(host="10.0.0.1")], credentials={})

            # Export должен завершиться успешно
            export_result = next(s for s in result.steps if s.step_id == "export")
            assert export_result.status == StepStatus.COMPLETED

            # Файл должен быть создан
            expected_file = os.path.join(tmpdir, "devices.json")
            assert os.path.exists(expected_file)

            # Проверяем содержимое
            with open(expected_file) as f:
                content = json.load(f)
            assert len(content) == 1
            assert content[0]["hostname"] == "router1"

    def test_export_no_data_skips(self, export_pipeline):
        """Export без данных пропускается."""
        executor = PipelineExecutor(export_pipeline)

        # Мокаем collect с пустыми данными
        def mock_collect(step):
            executor._context["collected_data"]["devices"] = {
                "target": "devices",
                "data": [],
                "count": 0,
            }
            return {"target": "devices", "data": [], "count": 0}

        executor._execute_collect = mock_collect

        result = executor.run(devices=[Mock(host="10.0.0.1")], credentials={})

        # Export должен вернуть skipped
        export_result = next(s for s in result.steps if s.step_id == "export_devices")
        assert export_result.status == StepStatus.COMPLETED
        assert export_result.data.get("skipped") is True


@pytest.mark.integration
class TestPipelineExecutorFullFlow:
    """Тесты полного потока pipeline."""

    def test_full_pipeline_collect_sync(self):
        """Полный pipeline: collect → sync."""
        pipeline = Pipeline(
            id="full_test",
            name="Full Test",
            steps=[
                PipelineStep(id="collect_devices", type=StepType.COLLECT, target="devices"),
                PipelineStep(id="collect_interfaces", type=StepType.COLLECT, target="interfaces"),
                PipelineStep(
                    id="sync_devices",
                    type=StepType.SYNC,
                    target="devices",
                    depends_on=["collect_devices"],
                ),
                PipelineStep(
                    id="sync_interfaces",
                    type=StepType.SYNC,
                    target="interfaces",
                    depends_on=["sync_devices", "collect_interfaces"],
                ),
            ],
        )

        executor = PipelineExecutor(pipeline, dry_run=True)

        # Мокаем все collectors
        call_count = [0]

        def mock_collect(step):
            call_count[0] += 1
            target = step.target
            if target == "devices":
                data = [{"hostname": "r1"}]
            else:
                data = [{"name": "Gi0/1", "hostname": "r1"}]

            executor._context["collected_data"][target] = {
                "target": target,
                "data": data,
                "count": 1,
            }
            return {"target": target, "data": data, "count": 1}

        executor._execute_collect = mock_collect

        # Патчим NetBox
        with patch("network_collector.netbox.client.NetBoxClient"):
            with patch("network_collector.netbox.sync.NetBoxSync") as MockSync:
                mock_sync = MockSync.return_value
                mock_sync.sync_devices_from_inventory.return_value = {"created": 1}
                mock_sync.sync_interfaces.return_value = {"created": 1}

                result = executor.run(
                    devices=[Mock(host="10.0.0.1")],
                    credentials={},
                    netbox_config={"url": "http://netbox", "token": "tok"},
                )

        assert result.status == StepStatus.COMPLETED
        assert len(result.steps) == 4
        assert all(s.status == StepStatus.COMPLETED for s in result.steps)
        assert call_count[0] == 2  # Два collect вызова

    def test_pipeline_stops_on_failed_dependency(self):
        """Pipeline останавливается если зависимость упала."""
        pipeline = Pipeline(
            id="dep_test",
            name="Dependency Test",
            steps=[
                PipelineStep(id="collect", type=StepType.COLLECT, target="devices"),
                PipelineStep(id="sync", type=StepType.SYNC, target="devices", depends_on=["collect"]),
            ],
        )

        executor = PipelineExecutor(pipeline)

        # Первый шаг падает
        def failing_execute(step):
            if step.id == "collect":
                return StepResult(step_id="collect", status=StepStatus.FAILED, error="Connection error")
            return StepResult(step_id=step.id, status=StepStatus.COMPLETED)

        executor._execute_step = failing_execute

        result = executor.run(devices=[Mock()], credentials={})

        assert result.status == StepStatus.FAILED
        # Второй шаг не должен выполняться
        assert len(result.steps) == 1
        assert result.steps[0].step_id == "collect"

    def test_dry_run_propagates_to_context(self):
        """dry_run передаётся в контекст."""
        pipeline = Pipeline(
            id="dry_test",
            name="Dry Run Test",
            steps=[
                PipelineStep(id="collect", type=StepType.COLLECT, target="devices"),
            ],
        )

        executor = PipelineExecutor(pipeline, dry_run=True)
        executor._execute_collect = Mock(return_value={"target": "devices", "data": [], "count": 0})

        executor.run(devices=[], credentials={})

        assert executor._context["dry_run"] is True


@pytest.mark.integration
class TestPipelineExecutorCallbacks:
    """Тесты callbacks."""

    def test_callbacks_receive_correct_data(self):
        """Callbacks получают правильные данные."""
        pipeline = Pipeline(
            id="cb_test",
            name="Callback Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
                PipelineStep(id="s2", type=StepType.COLLECT, target="interfaces"),
            ],
        )

        started_steps = []
        completed_steps = []

        def on_start(step):
            started_steps.append({"id": step.id, "type": step.type})

        def on_complete(step, result):
            completed_steps.append({
                "id": step.id,
                "status": result.status,
            })

        executor = PipelineExecutor(
            pipeline,
            on_step_start=on_start,
            on_step_complete=on_complete,
        )

        def mock_collect(step):
            executor._context["collected_data"][step.target] = {"data": [], "count": 0}
            return {"target": step.target, "data": [], "count": 0}

        executor._execute_collect = mock_collect

        executor.run(devices=[], credentials={})

        assert len(started_steps) == 2
        assert len(completed_steps) == 2
        assert started_steps[0]["id"] == "s1"
        assert started_steps[1]["id"] == "s2"
        assert completed_steps[0]["status"] == StepStatus.COMPLETED

    def test_callbacks_on_failure(self):
        """Callbacks вызываются при ошибке."""
        pipeline = Pipeline(
            id="fail_test",
            name="Fail Test",
            steps=[
                PipelineStep(id="s1", type=StepType.COLLECT, target="devices"),
            ],
        )

        completed_steps = []

        def on_complete(step, result):
            completed_steps.append({
                "id": step.id,
                "status": result.status,
                "error": result.error,
            })

        executor = PipelineExecutor(pipeline, on_step_complete=on_complete)

        # Collector падает
        def failing_collect(step):
            raise RuntimeError("Test error")

        executor._execute_collect = failing_collect

        result = executor.run(devices=[Mock()], credentials={})

        assert result.status == StepStatus.FAILED
        assert len(completed_steps) == 1
        assert completed_steps[0]["status"] == StepStatus.FAILED
        assert "Test error" in completed_steps[0]["error"]
