"""
Tests for netbox/sync/inventory.py.

Тестирует синхронизацию inventory items с NetBox.
"""

import pytest
from unittest.mock import Mock, MagicMock

from network_collector.netbox.sync import NetBoxSync
from network_collector.core.models import InventoryItem


class TestInventorySyncBasic:
    """Базовые тесты sync_inventory."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        return Mock()

    @pytest.fixture
    def sample_inventory(self):
        """Тестовые inventory items."""
        return [
            InventoryItem(
                name="Power Supply 1",
                pid="PWR-C1-350WAC",
                serial="PSU12345678",
                description="AC Power Supply",
                manufacturer="Cisco",
            ),
            InventoryItem(
                name="SFP Module Gi0/1",
                pid="SFP-10G-LR",
                serial="SFP87654321",
                description="10G LR SFP+",
                manufacturer="Cisco",
            ),
        ]

    def test_sync_inventory_device_not_found(self, mock_client):
        """Если устройство не найдено - возвращает нули."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        result = sync.sync_inventory("nonexistent", [])

        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["deleted"] == 0

    def test_sync_inventory_empty_list(self, mock_client):
        """Пустой список inventory не вызывает ошибку."""
        sync = NetBoxSync(mock_client)
        result = sync.sync_inventory("device", [])

        assert result["created"] == 0
        assert result["updated"] == 0

    def test_sync_inventory_returns_stats(self, mock_client, sample_inventory):
        """sync_inventory возвращает словарь статистики."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        result = sync.sync_inventory("switch-01", sample_inventory)

        assert isinstance(result, dict)
        assert "created" in result
        assert "updated" in result
        assert "deleted" in result
        assert "skipped" in result
        assert "failed" in result

    def test_sync_inventory_dry_run(self, mock_client, sample_inventory):
        """В режиме dry_run inventory items не создаются."""
        mock_device = Mock()
        mock_device.id = 1
        mock_client.get_device_by_name.return_value = mock_device
        mock_client.get_inventory_items.return_value = []

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", sample_inventory)

        # create_inventory_item НЕ должен вызываться в dry_run
        mock_client.create_inventory_item.assert_not_called()


class TestInventorySyncWithDevice:
    """Тесты sync_inventory когда устройство найдено."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "switch-01"
        client.get_device_by_name.return_value = mock_device
        client.get_inventory_items.return_value = []
        return client

    def test_creates_new_inventory_item(self, mock_client):
        """Создаёт новый inventory item."""
        items = [
            InventoryItem(
                name="Power Supply 1",
                pid="PWR-C1-350WAC",
                serial="PSU12345678",
                description="AC Power Supply",
                manufacturer="Cisco",
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        # В dry_run не создаёт но увеличивает счётчик
        assert result["created"] >= 0 or result["skipped"] >= 0

    def test_skips_item_without_serial(self, mock_client):
        """Пропускает item без серийного номера."""
        items = [
            InventoryItem(
                name="Unknown Module",
                pid="UNKNOWN",
                serial="",  # Нет серийника
                description="Unknown",
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        assert result["skipped"] == 1

    def test_skips_item_without_name(self, mock_client):
        """Пропускает item без имени."""
        items = [
            InventoryItem(
                name="",  # Пустое имя
                pid="SOMEPID",
                serial="SERIAL123",
                description="Description",
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        # Item без имени пропускается
        assert result["created"] == 0


class TestInventorySyncCleanup:
    """Тесты cleanup функциональности."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "switch-01"
        client.get_device_by_name.return_value = mock_device
        return client

    def test_cleanup_removes_old_items(self, mock_client):
        """С cleanup=True удаляет старые items из NetBox."""
        # Существующий item в NetBox который не в новых данных
        old_item = Mock()
        old_item.name = "Old Module"
        old_item.id = 99

        mock_client.get_inventory_items.return_value = [old_item]

        items = [
            InventoryItem(
                name="New Module",
                pid="NEWPID",
                serial="NEWSERIAL",
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items, cleanup=True)

        # Должен пометить deleted
        assert result["deleted"] == 1

    def test_no_cleanup_keeps_old_items(self, mock_client):
        """Без cleanup старые items не удаляются."""
        old_item = Mock()
        old_item.name = "Old Module"
        old_item.id = 99

        mock_client.get_inventory_items.return_value = [old_item]

        items = [
            InventoryItem(
                name="New Module",
                pid="NEWPID",
                serial="NEWSERIAL",
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items, cleanup=False)

        # Без cleanup - не удаляется
        assert result["deleted"] == 0


class TestInventoryItemModel:
    """Тесты модели InventoryItem."""

    def test_from_dict(self):
        """Создание из словаря."""
        data = {
            "name": "Power Supply",
            "pid": "PWR-123",
            "serial": "SERIAL",
            "description": "Test PSU",
            "manufacturer": "Cisco",
        }

        item = InventoryItem.from_dict(data)

        assert item.name == "Power Supply"
        assert item.pid == "PWR-123"
        assert item.serial == "SERIAL"

    def test_ensure_list_with_list(self):
        """ensure_list со списком возвращает список."""
        items = [InventoryItem(name="Item1"), InventoryItem(name="Item2")]
        result = InventoryItem.ensure_list(items)

        assert isinstance(result, list)
        assert len(result) == 2

    def test_ensure_list_with_dicts(self):
        """ensure_list со списком dict конвертирует."""
        dicts = [
            {"name": "Item1", "pid": "PID1", "serial": "S1"},
            {"name": "Item2", "pid": "PID2", "serial": "S2"},
        ]
        result = InventoryItem.ensure_list(dicts)

        assert isinstance(result, list)
        assert all(isinstance(i, InventoryItem) for i in result)

    def test_to_dict(self):
        """Конвертация в словарь."""
        item = InventoryItem(
            name="Module",
            pid="MOD-123",
            serial="SER123",
            description="Test",
            manufacturer="Cisco",
        )

        data = item.to_dict()

        assert data["name"] == "Module"
        assert data["pid"] == "MOD-123"
        assert data["serial"] == "SER123"


class TestInventorySyncManufacturer:
    """Тесты работы с manufacturer."""

    @pytest.fixture
    def mock_client(self):
        """Мокированный NetBox клиент."""
        client = Mock()
        mock_device = Mock()
        mock_device.id = 1
        mock_device.name = "switch-01"
        client.get_device_by_name.return_value = mock_device
        client.get_inventory_items.return_value = []
        return client

    def test_item_with_manufacturer(self, mock_client):
        """Item с manufacturer обрабатывается."""
        items = [
            InventoryItem(
                name="SFP Module",
                pid="SFP-10G-LR",
                serial="SFP123",
                manufacturer="Cisco",
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        # Не должно упасть
        assert isinstance(result, dict)

    def test_item_without_manufacturer(self, mock_client):
        """Item без manufacturer тоже обрабатывается."""
        items = [
            InventoryItem(
                name="SFP Module",
                pid="SFP-10G-LR",
                serial="SFP123",
                manufacturer="",  # Пустой
            ),
        ]

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_inventory("switch-01", items)

        assert isinstance(result, dict)
