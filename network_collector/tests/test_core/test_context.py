"""
Тесты для RunContext.

Проверяет:
- Создание контекста
- run_id генерация
- Папки отчётов
- Сериализация
"""

import pytest
import json
from pathlib import Path
from datetime import datetime

from network_collector.core.context import (
    RunContext,
    get_current_context,
    set_current_context,
)


class TestRunContextCreation:
    """Тесты создания RunContext."""

    def test_create_with_defaults(self):
        """Тест создания с дефолтными параметрами."""
        ctx = RunContext.create()

        assert ctx.run_id is not None
        assert ctx.started_at is not None
        assert ctx.dry_run is False
        assert ctx.triggered_by == "cli"
        assert ctx.command == ""

    def test_create_with_dry_run(self):
        """Тест создания с dry_run=True."""
        ctx = RunContext.create(dry_run=True)

        assert ctx.dry_run is True
        assert "[DRY-RUN]" in str(ctx)

    def test_create_with_command(self):
        """Тест создания с командой."""
        ctx = RunContext.create(command="sync-netbox")

        assert ctx.command == "sync-netbox"
        assert "sync-netbox" in ctx.log_prefix()

    def test_create_with_triggered_by(self):
        """Тест создания с разными источниками."""
        for source in ["cli", "cron", "api", "test"]:
            ctx = RunContext.create(triggered_by=source)
            assert ctx.triggered_by == source

    def test_run_id_is_timestamp(self):
        """Тест что run_id по умолчанию - timestamp."""
        ctx = RunContext.create(use_timestamp_id=True)

        # Формат: 2025-03-14T12-30-22
        assert len(ctx.run_id) == 19
        assert ctx.run_id.count("-") == 4
        assert "T" in ctx.run_id

    def test_run_id_is_uuid(self):
        """Тест что run_id может быть UUID."""
        ctx = RunContext.create(use_timestamp_id=False)

        # Короткий UUID (8 символов)
        assert len(ctx.run_id) == 8


class TestRunContextOutputDir:
    """Тесты для output_dir."""

    def test_output_dir_default(self):
        """Тест дефолтной папки."""
        ctx = RunContext.create()

        assert ctx.output_dir is not None
        assert "reports" in str(ctx.output_dir)
        assert ctx.run_id in str(ctx.output_dir)

    def test_output_dir_custom_base(self, tmp_path):
        """Тест кастомной базовой папки."""
        ctx = RunContext.create(base_output_dir=tmp_path)

        assert str(tmp_path) in str(ctx.output_dir)
        assert ctx.run_id in str(ctx.output_dir)

    def test_ensure_output_dir_creates(self, tmp_path):
        """Тест что ensure_output_dir создаёт папку."""
        ctx = RunContext.create(base_output_dir=tmp_path)

        assert not ctx.output_dir.exists()
        result = ctx.ensure_output_dir()
        assert ctx.output_dir.exists()
        assert result == ctx.output_dir

    def test_get_output_path(self, tmp_path):
        """Тест получения пути для файла."""
        ctx = RunContext.create(base_output_dir=tmp_path)

        path = ctx.get_output_path("interfaces.xlsx")

        assert path.name == "interfaces.xlsx"
        assert ctx.run_id in str(path)
        assert ctx.output_dir.exists()  # Папка должна быть создана


class TestRunContextElapsed:
    """Тесты для elapsed time."""

    def test_elapsed_seconds(self):
        """Тест вычисления elapsed."""
        ctx = RunContext.create()

        # Сразу после создания должно быть близко к 0
        assert ctx.elapsed_seconds >= 0
        assert ctx.elapsed_seconds < 1

    def test_elapsed_human_seconds(self):
        """Тест форматирования секунд."""
        ctx = RunContext.create()

        # < 60 секунд → "X.Xs"
        human = ctx.elapsed_human
        assert "s" in human


class TestRunContextSerialization:
    """Тесты сериализации."""

    def test_to_dict(self):
        """Тест конвертации в словарь."""
        ctx = RunContext.create(
            dry_run=True,
            command="interfaces",
            triggered_by="api",
        )

        data = ctx.to_dict()

        assert data["run_id"] == ctx.run_id
        assert data["dry_run"] is True
        assert data["command"] == "interfaces"
        assert data["triggered_by"] == "api"
        assert "started_at" in data
        assert "elapsed_seconds" in data

    def test_save_summary(self, tmp_path):
        """Тест сохранения summary.json."""
        ctx = RunContext.create(base_output_dir=tmp_path, command="test")

        stats = {"devices": 5, "interfaces": 100}
        summary_path = ctx.save_summary(stats)

        assert summary_path.exists()
        assert summary_path.name == "summary.json"

        # Читаем и проверяем содержимое
        with open(summary_path) as f:
            data = json.load(f)

        assert data["run_id"] == ctx.run_id
        assert data["command"] == "test"
        assert data["stats"]["devices"] == 5
        assert "completed_at" in data


class TestRunContextGlobal:
    """Тесты глобального контекста."""

    def test_get_set_current_context(self):
        """Тест установки и получения глобального контекста."""
        # Изначально None
        set_current_context(None)
        assert get_current_context() is None

        # Устанавливаем
        ctx = RunContext.create()
        set_current_context(ctx)

        # Получаем
        current = get_current_context()
        assert current is ctx
        assert current.run_id == ctx.run_id

        # Очищаем после теста
        set_current_context(None)

    def test_context_isolation(self):
        """Тест что контексты независимы."""
        # Используем UUID чтобы гарантировать уникальность
        ctx1 = RunContext.create(command="cmd1", use_timestamp_id=False)
        ctx2 = RunContext.create(command="cmd2", use_timestamp_id=False)

        assert ctx1.run_id != ctx2.run_id
        assert ctx1.command != ctx2.command


class TestRunContextLogPrefix:
    """Тесты для log_prefix."""

    def test_log_prefix_with_command(self):
        """Тест префикса с командой."""
        ctx = RunContext.create(command="sync-netbox")

        prefix = ctx.log_prefix()

        assert ctx.run_id in prefix
        assert "sync-netbox" in prefix
        assert prefix.startswith("[")

    def test_log_prefix_without_command(self):
        """Тест префикса без команды."""
        ctx = RunContext.create()

        prefix = ctx.log_prefix()

        assert ctx.run_id in prefix
        assert prefix.count("[") == 1  # Только run_id


class TestRunContextRepr:
    """Тесты строковых представлений."""

    def test_str(self):
        """Тест __str__."""
        ctx = RunContext.create(dry_run=False)
        assert "RunContext" in str(ctx)
        assert ctx.run_id in str(ctx)

    def test_str_dry_run(self):
        """Тест __str__ с dry_run."""
        ctx = RunContext.create(dry_run=True)
        assert "[DRY-RUN]" in str(ctx)

    def test_repr(self):
        """Тест __repr__."""
        ctx = RunContext.create(command="test", triggered_by="api")
        r = repr(ctx)

        assert "RunContext" in r
        assert "run_id=" in r
        assert "command='test'" in r
        assert "triggered_by='api'" in r
