"""
Тесты для _print_sync_summary().

Проверяем что функция не падает при разных входных данных.
"""

import pytest
from unittest.mock import MagicMock
from io import StringIO
import sys


class TestPrintSyncSummary:
    """Тесты вывода сводки синхронизации."""

    def test_summary_with_all_keys(self):
        """Сводка с полным набором ключей."""
        from network_collector.cli import _print_sync_summary

        summary = {
            "devices": {"created": 1, "updated": 2, "deleted": 0, "skipped": 3, "failed": 0},
            "interfaces": {"created": 5, "updated": 0, "deleted": 1, "skipped": 0, "failed": 0},
            "ip_addresses": {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
            "vlans": {"created": 2, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
            "cables": {"created": 0, "deleted": 0, "skipped": 0, "failed": 0, "already_exists": 5},
            "inventory": {"created": 0, "updated": 0, "skipped": 0, "failed": 0},
        }

        args = MagicMock()
        args.dry_run = False
        args.format = None

        # Не должно падать
        _print_sync_summary(summary, args)

    def test_summary_with_missing_keys(self):
        """Сводка с отсутствующими ключами (регрессия KeyError)."""
        from network_collector.cli import _print_sync_summary

        # Минимальный набор — без failed, already_exists
        summary = {
            "devices": {"created": 1, "updated": 0},
            "interfaces": {"created": 2},
            "ip_addresses": {},
            "vlans": {"skipped": 1},
            "cables": {},
            "inventory": {},
        }

        args = MagicMock()
        args.dry_run = False
        args.format = None

        # Не должно падать с KeyError
        _print_sync_summary(summary, args)

    def test_summary_empty(self):
        """Пустая сводка."""
        from network_collector.cli import _print_sync_summary

        summary = {
            "devices": {},
            "interfaces": {},
            "ip_addresses": {},
            "vlans": {},
            "cables": {},
            "inventory": {},
        }

        args = MagicMock()
        args.dry_run = True
        args.format = None

        # Не должно падать
        _print_sync_summary(summary, args)

    def test_summary_dry_run_mode(self):
        """Сводка в режиме dry-run."""
        from network_collector.cli import _print_sync_summary

        summary = {
            "devices": {"created": 5, "updated": 3},
            "interfaces": {"created": 10},
            "ip_addresses": {},
            "vlans": {},
            "cables": {"already_exists": 2},
            "inventory": {},
        }

        args = MagicMock()
        args.dry_run = True
        args.format = None

        # Захватываем stdout
        captured = StringIO()
        sys.stdout = captured

        try:
            _print_sync_summary(summary, args)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()

        # Должен содержать [DRY-RUN]
        assert "DRY-RUN" in output

    def test_summary_json_format(self):
        """Сводка в JSON формате."""
        from network_collector.cli import _print_sync_summary
        import json

        summary = {
            "devices": {"created": 1, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0},
            "interfaces": {},
            "ip_addresses": {},
            "vlans": {},
            "cables": {},
            "inventory": {},
        }

        args = MagicMock()
        args.dry_run = False
        args.format = "json"

        # Захватываем stdout
        captured = StringIO()
        sys.stdout = captured

        try:
            _print_sync_summary(summary, args)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()

        # Должен быть валидный JSON
        data = json.loads(output)
        assert "summary" in data
        assert "totals" in data
        assert data["totals"]["created"] == 1

    def test_summary_with_failures(self):
        """Сводка с ошибками."""
        from network_collector.cli import _print_sync_summary

        summary = {
            "devices": {"created": 1, "failed": 2},
            "interfaces": {"created": 5, "failed": 1},
            "ip_addresses": {},
            "vlans": {},
            "cables": {},
            "inventory": {},
        }

        args = MagicMock()
        args.dry_run = False
        args.format = None

        # Захватываем stdout
        captured = StringIO()
        sys.stdout = captured

        try:
            _print_sync_summary(summary, args)
        finally:
            sys.stdout = sys.__stdout__

        output = captured.getvalue()

        # Должен показать ошибки
        assert "ошибок" in output or "failed" in output.lower() or "✗" in output
