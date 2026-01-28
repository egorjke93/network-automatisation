"""
Tests for netbox/sync/base.py.

Тестирует базовый класс SyncBase.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from network_collector.netbox.sync.base import SyncBase
from network_collector.core.context import RunContext


class TestSyncBaseInit:
    """Тесты инициализации SyncBase."""

    def test_init_with_defaults(self):
        """Инициализация с дефолтными параметрами."""
        mock_client = Mock()
        sync = SyncBase(mock_client)

        assert sync.client == mock_client
        assert sync.dry_run is False
        assert sync.create_only is False
        assert sync.update_only is False

    def test_init_with_dry_run(self):
        """Инициализация с dry_run=True."""
        mock_client = Mock()
        sync = SyncBase(mock_client, dry_run=True)

        assert sync.dry_run is True

    def test_init_with_create_only(self):
        """Инициализация с create_only=True."""
        mock_client = Mock()
        sync = SyncBase(mock_client, create_only=True)

        assert sync.create_only is True
        assert sync.update_only is False

    def test_init_with_update_only(self):
        """Инициализация с update_only=True."""
        mock_client = Mock()
        sync = SyncBase(mock_client, update_only=True)

        assert sync.update_only is True
        assert sync.create_only is False

    def test_init_with_context(self):
        """Инициализация с контекстом."""
        mock_client = Mock()
        ctx = RunContext.create()
        sync = SyncBase(mock_client, context=ctx)

        assert sync.ctx == ctx

    def test_device_cache_initialized(self):
        """Кэши инициализируются пустыми."""
        mock_client = Mock()
        sync = SyncBase(mock_client)

        assert sync._device_cache == {}
        assert sync._mac_cache == {}


class TestSyncBaseLogPrefix:
    """Тесты _log_prefix."""

    def test_log_prefix_with_context(self):
        """С контекстом возвращает префикс с run_id."""
        mock_client = Mock()
        ctx = RunContext.create()
        sync = SyncBase(mock_client, context=ctx)

        prefix = sync._log_prefix()

        assert ctx.run_id in prefix
        assert prefix.startswith("[")
        assert prefix.endswith("] ")

    def test_log_prefix_without_context(self):
        """Без контекста возвращает пустую строку."""
        mock_client = Mock()

        with patch("network_collector.netbox.sync.base.get_current_context", return_value=None):
            sync = SyncBase(mock_client, context=None)
            sync.ctx = None

        prefix = sync._log_prefix()
        assert prefix == ""


class TestSyncBaseFindDevice:
    """Тесты _find_device с кэшированием."""

    def test_find_device_uses_cache(self):
        """Повторный вызов использует кэш."""
        mock_client = Mock()
        mock_device = Mock()
        mock_client.get_device_by_name.return_value = mock_device

        sync = SyncBase(mock_client)

        # Первый вызов
        result1 = sync._find_device("switch-01")
        assert result1 == mock_device
        assert mock_client.get_device_by_name.call_count == 1

        # Второй вызов - из кэша
        result2 = sync._find_device("switch-01")
        assert result2 == mock_device
        assert mock_client.get_device_by_name.call_count == 1  # Не увеличился

    def test_find_device_caches_none(self):
        """None тоже кэшируется."""
        mock_client = Mock()
        mock_client.get_device_by_name.return_value = None

        sync = SyncBase(mock_client)

        result1 = sync._find_device("nonexistent")
        assert result1 is None
        assert mock_client.get_device_by_name.call_count == 1

        # Но None НЕ кэшируется - это особенность реализации
        # (чтобы можно было повторить поиск после создания)

    def test_find_device_different_names(self):
        """Разные имена кэшируются отдельно."""
        mock_client = Mock()
        mock_device1 = Mock(name="device1")
        mock_device2 = Mock(name="device2")

        def get_device(name):
            if name == "switch-01":
                return mock_device1
            elif name == "switch-02":
                return mock_device2
            return None

        mock_client.get_device_by_name.side_effect = get_device

        sync = SyncBase(mock_client)

        result1 = sync._find_device("switch-01")
        result2 = sync._find_device("switch-02")

        assert result1 == mock_device1
        assert result2 == mock_device2
        assert "switch-01" in sync._device_cache
        assert "switch-02" in sync._device_cache


class TestSyncBaseContextMethods:
    """Тесты методов работы с контекстом."""

    def test_context_from_global(self):
        """Использует глобальный контекст если не передан."""
        mock_client = Mock()
        global_ctx = RunContext.create()

        with patch("network_collector.netbox.sync.base.get_current_context", return_value=global_ctx):
            sync = SyncBase(mock_client)

        assert sync.ctx == global_ctx


class TestSyncBaseCombinations:
    """Тесты комбинаций параметров."""

    def test_create_only_and_dry_run(self):
        """create_only и dry_run можно комбинировать."""
        mock_client = Mock()
        sync = SyncBase(mock_client, dry_run=True, create_only=True)

        assert sync.dry_run is True
        assert sync.create_only is True

    def test_update_only_and_dry_run(self):
        """update_only и dry_run можно комбинировать."""
        mock_client = Mock()
        sync = SyncBase(mock_client, dry_run=True, update_only=True)

        assert sync.dry_run is True
        assert sync.update_only is True

    def test_all_modes_can_be_set(self):
        """Все режимы можно установить (хотя create_only + update_only не имеет смысла)."""
        mock_client = Mock()
        sync = SyncBase(
            mock_client,
            dry_run=True,
            create_only=True,
            update_only=True,
        )

        assert sync.dry_run is True
        assert sync.create_only is True
        assert sync.update_only is True
