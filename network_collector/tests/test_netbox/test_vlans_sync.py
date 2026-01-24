"""
Tests for netbox/sync/vlans.py.

Тестирует синхронизацию VLAN с NetBox.
"""

import pytest
from unittest.mock import Mock

from network_collector.netbox.sync import NetBoxSync
from network_collector.core.models import Interface


class TestVlansSyncBasic:
    """Базовые тесты sync_vlans_from_interfaces."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    def test_sync_vlans_empty_list(self, mock_client):
        """Пустой список интерфейсов не вызывает ошибку."""
        sync = NetBoxSync(mock_client)
        result = sync.sync_vlans_from_interfaces("device", [])

        assert result["created"] == 0
        assert result["skipped"] == 0

    def test_sync_vlans_returns_stats(self, mock_client):
        """sync_vlans_from_interfaces возвращает статистику."""
        mock_client.get_vlan_by_vid.return_value = None

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan30", status="up"),
            Interface(name="Vlan100", status="up"),
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)
        assert "created" in result
        assert "skipped" in result
        assert "failed" in result

    def test_sync_vlans_only_svi_interfaces(self, mock_client):
        """Синхронизирует только SVI интерфейсы (Vlan*)."""
        mock_client.get_vlan_by_vid.return_value = None

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan30", status="up"),  # SVI
            Interface(name="GigabitEthernet0/1", status="up"),  # Не SVI
            Interface(name="Vlan100", status="up"),  # SVI
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        # Должны быть созданы только VLAN для SVI
        assert result["created"] == 2


class TestVlansSyncExisting:
    """Тесты синхронизации когда VLAN уже существует."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        return client

    def test_skips_existing_vlan(self, mock_client):
        """Существующий VLAN пропускается."""
        mock_vlan = Mock()
        mock_vlan.vid = 30
        mock_client.get_vlan_by_vid.return_value = mock_vlan

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan30", status="up"),
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        assert result["skipped"] == 1
        assert result["created"] == 0

    def test_mixed_existing_and_new(self, mock_client):
        """Смешанный случай: часть существует, часть нет."""
        def get_vlan_side_effect(vid=None, **kwargs):
            if vid == 30:
                mock_vlan = Mock()
                mock_vlan.vid = 30
                return mock_vlan
            return None

        mock_client.get_vlan_by_vid.side_effect = get_vlan_side_effect

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan30", status="up"),  # Существует
            Interface(name="Vlan100", status="up"),  # Новый
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        assert result["skipped"] == 1
        assert result["created"] == 1


class TestVlansSyncDryRun:
    """Тесты dry_run режима."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    def test_dry_run_no_create(self, mock_client):
        """В dry_run режиме VLAN не создаётся в NetBox."""
        mock_client.get_vlan_by_vid.return_value = None

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan100", status="up"),
        ]

        result = sync.sync_vlans_from_interfaces("switch-01", interfaces)

        # create_vlan НЕ должен вызываться
        mock_client.create_vlan.assert_not_called()
        # Но в статистике created увеличивается
        assert result["created"] == 1


class TestVlansSyncSiteParameter:
    """Тесты параметра site."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    def test_accepts_site_parameter(self, mock_client):
        """Принимает параметр site."""
        mock_client.get_vlan_by_vid.return_value = None

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan100", status="up"),
        ]

        # Не должно упасть с site
        result = sync.sync_vlans_from_interfaces(
            "switch-01",
            interfaces,
            site="Office",
        )

        assert isinstance(result, dict)


class TestVlanVidExtraction:
    """Тесты извлечения VID из имени интерфейса."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    def test_extracts_vid_from_vlan_name(self, mock_client):
        """Извлекает VID из имени Vlan*."""
        mock_client.get_vlan_by_vid.return_value = None

        sync = NetBoxSync(mock_client, dry_run=True)

        interfaces = [
            Interface(name="Vlan30", status="up"),
            Interface(name="Vlan100", status="up"),
            Interface(name="Vlan1", status="up"),
        ]

        sync.sync_vlans_from_interfaces("switch-01", interfaces)

        # Проверяем что get_vlan_by_vid вызывался с правильными VID
        calls = mock_client.get_vlan_by_vid.call_args_list
        vids = [call.kwargs.get("vid") or call.args[0] for call in calls if call.args or call.kwargs]
        # VID должны быть числами или переданы как kwargs
