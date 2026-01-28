"""
Tests for api/services/history_service.py.

Тестирует функции работы с историей операций.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

from network_collector.api.services import history_service
from network_collector.api.services.history_service import (
    add_entry,
    get_history,
    get_stats,
    clear_history,
    _load_history,
    _save_history,
    _ensure_dir,
    MAX_ENTRIES,
)


class TestEnsureDir:
    """Тесты _ensure_dir."""

    def test_creates_directory(self, tmp_path):
        """Создаёт директорию если не существует."""
        test_file = tmp_path / "subdir" / "history.json"

        with patch.object(history_service, "HISTORY_FILE", test_file):
            _ensure_dir()

        assert test_file.parent.exists()


class TestLoadHistory:
    """Тесты _load_history."""

    def test_returns_empty_list_if_not_exists(self, tmp_path):
        """Возвращает пустой список если файл не существует."""
        test_file = tmp_path / "nonexistent.json"

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = _load_history()

        assert result == []

    def test_loads_existing_file(self, tmp_path):
        """Загружает существующий файл."""
        test_file = tmp_path / "history.json"
        test_data = [{"id": "1", "operation": "test"}]
        test_file.write_text(json.dumps(test_data))

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = _load_history()

        assert result == test_data

    def test_returns_empty_on_json_error(self, tmp_path):
        """Возвращает пустой список при ошибке JSON."""
        test_file = tmp_path / "history.json"
        test_file.write_text("invalid json {{{")

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = _load_history()

        assert result == []


class TestSaveHistory:
    """Тесты _save_history."""

    def test_saves_entries(self, tmp_path):
        """Сохраняет записи в файл."""
        test_file = tmp_path / "data" / "history.json"
        entries = [{"id": "1", "operation": "test"}]

        with patch.object(history_service, "HISTORY_FILE", test_file):
            _save_history(entries)

        assert test_file.exists()
        loaded = json.loads(test_file.read_text())
        assert loaded == entries

    def test_limits_entries(self, tmp_path):
        """Ограничивает количество записей."""
        test_file = tmp_path / "data" / "history.json"
        # Создаём больше записей чем MAX_ENTRIES
        entries = [{"id": str(i)} for i in range(MAX_ENTRIES + 100)]

        with patch.object(history_service, "HISTORY_FILE", test_file):
            _save_history(entries)

        loaded = json.loads(test_file.read_text())
        assert len(loaded) == MAX_ENTRIES


class TestAddEntry:
    """Тесты add_entry."""

    def test_adds_entry_with_minimal_params(self, tmp_path):
        """Добавляет запись с минимальными параметрами."""
        test_file = tmp_path / "data" / "history.json"

        with patch.object(history_service, "HISTORY_FILE", test_file):
            entry = add_entry(operation="test", status="success")

        assert entry["operation"] == "test"
        assert entry["status"] == "success"
        assert "id" in entry
        assert "timestamp" in entry

    def test_adds_entry_with_all_params(self, tmp_path):
        """Добавляет запись со всеми параметрами."""
        test_file = tmp_path / "data" / "history.json"

        with patch.object(history_service, "HISTORY_FILE", test_file):
            entry = add_entry(
                operation="sync",
                status="success",
                details={"extra": "info"},
                devices=["10.0.0.1", "10.0.0.2"],
                stats={"created": 5, "updated": 3},
                duration_ms=1500,
                error=None,
            )

        assert entry["operation"] == "sync"
        assert entry["devices"] == ["10.0.0.1", "10.0.0.2"]
        assert entry["device_count"] == 2
        assert entry["stats"]["created"] == 5
        assert entry["duration_ms"] == 1500

    def test_adds_entry_with_error(self, tmp_path):
        """Добавляет запись с ошибкой."""
        test_file = tmp_path / "data" / "history.json"

        with patch.object(history_service, "HISTORY_FILE", test_file):
            entry = add_entry(
                operation="backup",
                status="error",
                error="Connection refused",
            )

        assert entry["status"] == "error"
        assert entry["error"] == "Connection refused"


class TestGetHistory:
    """Тесты get_history."""

    def test_returns_empty_when_no_entries(self, tmp_path):
        """Возвращает пустой список когда нет записей."""
        test_file = tmp_path / "nonexistent.json"

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = get_history()

        assert result["entries"] == []
        assert result["total"] == 0

    def test_returns_entries_with_pagination(self, tmp_path):
        """Возвращает записи с пагинацией."""
        test_file = tmp_path / "data" / "history.json"
        entries = [{"id": str(i), "operation": "test"} for i in range(10)]
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(json.dumps(entries))

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = get_history(limit=5, offset=0)

        assert len(result["entries"]) == 5
        assert result["total"] == 10

    def test_filters_by_operation(self, tmp_path):
        """Фильтрует по типу операции."""
        test_file = tmp_path / "data" / "history.json"
        entries = [
            {"id": "1", "operation": "sync", "status": "success"},
            {"id": "2", "operation": "backup", "status": "success"},
            {"id": "3", "operation": "sync", "status": "error"},
        ]
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(json.dumps(entries))

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = get_history(operation="sync")

        assert len(result["entries"]) == 2
        assert all(e["operation"] == "sync" for e in result["entries"])

    def test_filters_by_status(self, tmp_path):
        """Фильтрует по статусу."""
        test_file = tmp_path / "data" / "history.json"
        entries = [
            {"id": "1", "operation": "sync", "status": "success"},
            {"id": "2", "operation": "backup", "status": "error"},
            {"id": "3", "operation": "sync", "status": "success"},
        ]
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(json.dumps(entries))

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = get_history(status="error")

        assert len(result["entries"]) == 1
        assert result["entries"][0]["status"] == "error"


class TestGetStats:
    """Тесты get_stats."""

    def test_returns_empty_stats_when_no_entries(self, tmp_path):
        """Возвращает пустую статистику когда нет записей."""
        test_file = tmp_path / "nonexistent.json"

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = get_stats()

        assert result["total_operations"] == 0
        assert result["by_operation"] == {}
        assert result["by_status"] == {}
        assert result["last_24h"] == 0

    def test_counts_by_operation(self, tmp_path):
        """Подсчитывает по типу операции."""
        test_file = tmp_path / "data" / "history.json"
        entries = [
            {"id": "1", "operation": "sync", "status": "success", "timestamp": "2024-01-01T00:00:00"},
            {"id": "2", "operation": "backup", "status": "success", "timestamp": "2024-01-01T00:00:00"},
            {"id": "3", "operation": "sync", "status": "error", "timestamp": "2024-01-01T00:00:00"},
        ]
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(json.dumps(entries))

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = get_stats()

        assert result["total_operations"] == 3
        assert result["by_operation"]["sync"] == 2
        assert result["by_operation"]["backup"] == 1

    def test_counts_by_status(self, tmp_path):
        """Подсчитывает по статусу."""
        test_file = tmp_path / "data" / "history.json"
        entries = [
            {"id": "1", "operation": "sync", "status": "success", "timestamp": "2024-01-01T00:00:00"},
            {"id": "2", "operation": "backup", "status": "error", "timestamp": "2024-01-01T00:00:00"},
            {"id": "3", "operation": "sync", "status": "success", "timestamp": "2024-01-01T00:00:00"},
        ]
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(json.dumps(entries))

        with patch.object(history_service, "HISTORY_FILE", test_file):
            result = get_stats()

        assert result["by_status"]["success"] == 2
        assert result["by_status"]["error"] == 1


class TestClearHistory:
    """Тесты clear_history."""

    def test_clears_all_entries(self, tmp_path):
        """Очищает все записи."""
        test_file = tmp_path / "data" / "history.json"
        entries = [{"id": "1"}, {"id": "2"}]
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(json.dumps(entries))

        with patch.object(history_service, "HISTORY_FILE", test_file):
            clear_history()
            result = get_history()

        assert result["entries"] == []
        assert result["total"] == 0
