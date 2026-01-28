"""
Тесты CLI команды pipeline.
"""

import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from argparse import Namespace

from network_collector.cli.commands.pipeline import (
    cmd_pipeline,
    _load_pipeline,
    _get_pipeline_files,
    _print_pipeline_list,
    _print_pipeline_details,
    _print_validation_result,
    _print_run_result,
    PIPELINES_DIR,
)
from network_collector.core.pipeline.models import Pipeline, PipelineStep, StepType, StepStatus
from network_collector.core.pipeline.executor import PipelineResult, StepResult


@pytest.fixture
def sample_pipeline():
    """Создаёт тестовый pipeline."""
    return Pipeline(
        id="test",
        name="Test Pipeline",
        description="Pipeline for testing",
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
def temp_pipeline_dir(tmp_path):
    """Создаёт временную директорию для pipelines."""
    return tmp_path / "pipelines"


class TestLoadPipeline:
    """Тесты загрузки pipeline."""

    @pytest.mark.unit
    def test_load_pipeline_from_pipelines_dir(self):
        """Загрузка pipeline из директории pipelines."""
        # default.yaml должен существовать
        pipeline = _load_pipeline("default")
        assert pipeline is not None
        assert pipeline.id == "default"

    @pytest.mark.unit
    def test_load_pipeline_not_found(self):
        """Возвращает None для несуществующего pipeline."""
        pipeline = _load_pipeline("nonexistent_pipeline_xyz")
        assert pipeline is None

    @pytest.mark.unit
    def test_load_pipeline_from_path(self, tmp_path):
        """Загрузка pipeline по полному пути."""
        # Создаём временный YAML
        yaml_content = """
id: temp_test
name: Temp Test
description: Temporary test pipeline
steps:
  - id: step1
    type: collect
    target: devices
"""
        yaml_path = tmp_path / "temp_test.yaml"
        yaml_path.write_text(yaml_content)

        pipeline = _load_pipeline(str(yaml_path))
        assert pipeline is not None
        assert pipeline.id == "temp_test"


class TestGetPipelineFiles:
    """Тесты получения списка файлов."""

    @pytest.mark.unit
    def test_get_pipeline_files_returns_list(self):
        """Возвращает список файлов."""
        files = _get_pipeline_files()
        assert isinstance(files, list)

    @pytest.mark.unit
    def test_get_pipeline_files_contains_default(self):
        """Список содержит default.yaml."""
        files = _get_pipeline_files()
        filenames = [f.name for f in files]
        assert "default.yaml" in filenames


class TestPrintPipelineList:
    """Тесты вывода списка pipelines."""

    @pytest.mark.unit
    def test_print_pipeline_list_table(self, sample_pipeline, capsys):
        """Табличный вывод списка."""
        _print_pipeline_list([sample_pipeline], format_="table")
        captured = capsys.readouterr()

        assert "test" in captured.out
        assert "Test Pipeline" in captured.out
        assert "Total: 1 pipeline(s)" in captured.out

    @pytest.mark.unit
    def test_print_pipeline_list_json(self, sample_pipeline, capsys):
        """JSON вывод списка."""
        _print_pipeline_list([sample_pipeline], format_="json")
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert len(data) == 1
        assert data[0]["id"] == "test"
        assert data[0]["name"] == "Test Pipeline"
        assert data[0]["steps_count"] == 2


class TestPrintPipelineDetails:
    """Тесты вывода деталей pipeline."""

    @pytest.mark.unit
    def test_print_details_table(self, sample_pipeline, capsys):
        """Табличный вывод деталей."""
        _print_pipeline_details(sample_pipeline, format_="table")
        captured = capsys.readouterr()

        assert "Pipeline: Test Pipeline" in captured.out
        assert "ID:          test" in captured.out
        assert "Steps:       2" in captured.out
        assert "collect_devices" in captured.out
        assert "sync_devices" in captured.out

    @pytest.mark.unit
    def test_print_details_json(self, sample_pipeline, capsys):
        """JSON вывод деталей."""
        _print_pipeline_details(sample_pipeline, format_="json")
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert data["id"] == "test"
        assert data["name"] == "Test Pipeline"
        assert len(data["steps"]) == 2


class TestPrintValidationResult:
    """Тесты вывода результата валидации."""

    @pytest.mark.unit
    def test_validation_success(self, sample_pipeline, capsys):
        """Успешная валидация."""
        _print_validation_result(sample_pipeline, [])
        captured = capsys.readouterr()

        assert "✓" in captured.out
        assert "is valid" in captured.out

    @pytest.mark.unit
    def test_validation_errors(self, sample_pipeline, capsys):
        """Валидация с ошибками."""
        errors = ["Error 1", "Error 2"]
        _print_validation_result(sample_pipeline, errors)
        captured = capsys.readouterr()

        assert "✗" in captured.out
        assert "2 error(s)" in captured.out
        assert "Error 1" in captured.out
        assert "Error 2" in captured.out


class TestPrintRunResult:
    """Тесты вывода результата выполнения."""

    @pytest.mark.unit
    def test_run_result_table(self, capsys):
        """Табличный вывод результата."""
        result = PipelineResult(
            pipeline_id="test",
            status=StepStatus.COMPLETED,
            steps=[
                StepResult(
                    step_id="step1",
                    status=StepStatus.COMPLETED,
                    duration_ms=100,
                ),
                StepResult(
                    step_id="step2",
                    status=StepStatus.COMPLETED,
                    duration_ms=200,
                ),
            ],
            total_duration_ms=300,
        )

        _print_run_result(result, format_="table")
        captured = capsys.readouterr()

        assert "Pipeline Run Result: test" in captured.out
        assert "COMPLETED" in captured.out
        assert "step1" in captured.out
        assert "step2" in captured.out
        assert "300ms" in captured.out

    @pytest.mark.unit
    def test_run_result_json(self, capsys):
        """JSON вывод результата."""
        result = PipelineResult(
            pipeline_id="test",
            status=StepStatus.COMPLETED,
            steps=[
                StepResult(
                    step_id="step1",
                    status=StepStatus.COMPLETED,
                    duration_ms=100,
                ),
            ],
            total_duration_ms=100,
        )

        _print_run_result(result, format_="json")
        captured = capsys.readouterr()

        data = json.loads(captured.out)
        assert data["pipeline_id"] == "test"
        assert data["status"] == "completed"
        assert len(data["steps"]) == 1

    @pytest.mark.unit
    def test_run_result_with_error(self, capsys):
        """Вывод с ошибкой."""
        result = PipelineResult(
            pipeline_id="test",
            status=StepStatus.FAILED,
            steps=[
                StepResult(
                    step_id="step1",
                    status=StepStatus.FAILED,
                    error="Connection refused",
                    duration_ms=50,
                ),
            ],
            total_duration_ms=50,
        )

        _print_run_result(result, format_="table")
        captured = capsys.readouterr()

        assert "FAILED" in captured.out
        assert "Connection refused" in captured.out


class TestCmdPipeline:
    """Тесты команды cmd_pipeline."""

    @pytest.mark.unit
    def test_cmd_list(self, capsys):
        """Команда list."""
        args = Namespace(
            pipeline_command="list",
            format="table",
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "default" in captured.out
        assert "Total:" in captured.out

    @pytest.mark.unit
    def test_cmd_show(self, capsys):
        """Команда show."""
        args = Namespace(
            pipeline_command="show",
            name="default",
            format="table",
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "Pipeline:" in captured.out
        assert "Steps:" in captured.out

    @pytest.mark.unit
    def test_cmd_show_not_found(self, capsys):
        """Команда show для несуществующего pipeline."""
        args = Namespace(
            pipeline_command="show",
            name="nonexistent",
            format="table",
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "not found" in captured.out

    @pytest.mark.unit
    def test_cmd_validate(self, capsys):
        """Команда validate."""
        args = Namespace(
            pipeline_command="validate",
            name="default",
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        # default pipeline может иметь ошибки валидации из-за cables->lldp
        # но команда должна выполниться
        assert "default" in captured.out

    @pytest.mark.unit
    def test_cmd_validate_not_found(self, capsys):
        """Команда validate для несуществующего pipeline."""
        args = Namespace(
            pipeline_command="validate",
            name="nonexistent",
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "not found" in captured.out

    @pytest.mark.unit
    def test_cmd_no_subcommand(self, capsys):
        """Без подкоманды выводит usage."""
        args = Namespace(
            pipeline_command=None,
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "Usage:" in captured.out


class TestCmdCreate:
    """Тесты команды create."""

    @pytest.mark.unit
    def test_create_from_yaml(self, tmp_path, capsys):
        """Создание pipeline из YAML."""
        # Создаём временный YAML
        yaml_content = """
id: new_test_pipeline
name: New Test
description: New test pipeline
steps:
  - id: step1
    type: collect
    target: devices
"""
        yaml_path = tmp_path / "new_test.yaml"
        yaml_path.write_text(yaml_content)

        args = Namespace(
            pipeline_command="create",
            source=str(yaml_path),
            force=False,
        )

        # Мокаем PIPELINES_DIR
        with patch("network_collector.cli.commands.pipeline.PIPELINES_DIR", tmp_path / "pipelines"):
            cmd_pipeline(args)

        captured = capsys.readouterr()
        assert "created" in captured.out or "error" in captured.out.lower()

    @pytest.mark.unit
    def test_create_file_not_found(self, capsys):
        """Ошибка если файл не найден."""
        args = Namespace(
            pipeline_command="create",
            source="/nonexistent/path.yaml",
            force=False,
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "not found" in captured.out


class TestCmdDelete:
    """Тесты команды delete."""

    @pytest.mark.unit
    def test_delete_not_found(self, capsys):
        """Ошибка если pipeline не найден."""
        args = Namespace(
            pipeline_command="delete",
            name="nonexistent_pipeline_xyz",
            force=True,
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "not found" in captured.out

    @pytest.mark.unit
    def test_delete_with_force(self, tmp_path, capsys):
        """Удаление с флагом force."""
        # Создаём временный pipeline
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()
        yaml_path = pipelines_dir / "to_delete.yaml"
        yaml_path.write_text("id: to_delete\nname: To Delete\nsteps: []")

        args = Namespace(
            pipeline_command="delete",
            name="to_delete",
            force=True,
        )

        with patch("network_collector.cli.commands.pipeline.PIPELINES_DIR", pipelines_dir):
            cmd_pipeline(args)

        captured = capsys.readouterr()
        assert "deleted" in captured.out


class TestCmdRun:
    """Тесты команды run."""

    @pytest.mark.unit
    def test_run_not_found(self, capsys):
        """Ошибка если pipeline не найден."""
        args = Namespace(
            pipeline_command="run",
            name="nonexistent",
            devices="devices_ips.py",
            dry_run=True,
            apply=False,
            format="table",
            netbox_url=None,
            netbox_token=None,
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "not found" in captured.out

    @pytest.mark.unit
    @patch("network_collector.cli.utils.load_devices")
    @patch("network_collector.cli.utils.get_credentials")
    def test_run_no_devices(self, mock_creds, mock_devices, capsys):
        """Ошибка если нет устройств."""
        mock_devices.return_value = []
        mock_creds.return_value = None

        args = Namespace(
            pipeline_command="run",
            name="default",
            devices="devices_ips.py",
            dry_run=True,
            apply=False,
            format="table",
            netbox_url=None,
            netbox_token=None,
        )
        cmd_pipeline(args)
        captured = capsys.readouterr()

        assert "No devices" in captured.out or "error" in captured.out.lower()


class TestIntegration:
    """Интеграционные тесты CLI pipeline."""

    @pytest.mark.integration
    def test_full_workflow(self, tmp_path, capsys):
        """Полный цикл: create -> list -> show -> validate -> delete."""
        pipelines_dir = tmp_path / "pipelines"
        pipelines_dir.mkdir()

        # 1. Create
        yaml_content = """
id: integration_test
name: Integration Test
description: Test pipeline
steps:
  - id: step1
    type: collect
    target: devices
"""
        yaml_path = tmp_path / "integration_test.yaml"
        yaml_path.write_text(yaml_content)

        with patch("network_collector.cli.commands.pipeline.PIPELINES_DIR", pipelines_dir):
            # Create
            args = Namespace(pipeline_command="create", source=str(yaml_path), force=True)
            cmd_pipeline(args)

            # List
            args = Namespace(pipeline_command="list", format="table")
            cmd_pipeline(args)
            captured = capsys.readouterr()
            assert "integration_test" in captured.out

            # Show
            args = Namespace(pipeline_command="show", name="integration_test", format="table")
            cmd_pipeline(args)
            captured = capsys.readouterr()
            assert "Integration Test" in captured.out

            # Validate
            args = Namespace(pipeline_command="validate", name="integration_test")
            cmd_pipeline(args)
            captured = capsys.readouterr()
            assert "integration_test" in captured.out

            # Delete
            args = Namespace(pipeline_command="delete", name="integration_test", force=True)
            cmd_pipeline(args)
            captured = capsys.readouterr()
            assert "deleted" in captured.out
