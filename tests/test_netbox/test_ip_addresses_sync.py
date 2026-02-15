"""
Unit-тесты синхронизации IP-адресов (netbox/sync/ip_addresses.py).

Покрывает:
- sync_ip_addresses(): create, update, delete, primary IP
- _batch_create_ip_addresses(): batch + fallback
- _update_ip_address(): обычное обновление и пересоздание при смене маски
- _set_primary_ip(): установка primary_ip4
- _batch_delete_ip_addresses(): batch удаление
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call

from network_collector.netbox.sync import NetBoxSync
from network_collector.core.models import IPAddressEntry


@pytest.fixture
def mock_client():
    """Мокированный NetBox клиент."""
    client = Mock()
    client.api = Mock()
    return client


def make_nb_ip(address="10.0.0.1/24", ip_id=1, intf_id=10, tenant=None):
    """Создаёт мок IP-адреса из NetBox."""
    ip = Mock()
    ip.id = ip_id
    ip.address = address
    ip.assigned_object_id = intf_id
    ip.assigned_object_type = "dcim.interface"
    ip.tenant = tenant
    ip.description = ""
    ip.status = Mock(value="active")
    return ip


def make_nb_intf(name="Gi0/1", intf_id=10, description=""):
    """Создаёт мок интерфейса из NetBox."""
    intf = Mock()
    intf.id = intf_id
    intf.name = name
    intf.description = description
    return intf


# ==================== БАЗОВЫЕ ТЕСТЫ ====================

class TestIPAddressesSyncBasic:
    """Базовые тесты sync_ip_addresses."""

    def test_device_not_found(self, mock_client):
        """Устройство не найдено → failed=1, errors."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        result = sync.sync_ip_addresses("unknown-device", [])

        assert result["failed"] == 1
        assert "errors" in result

    def test_empty_ip_list(self, mock_client):
        """Пустой список IP → всё по нулям."""
        device = Mock(id=1, name="sw1", primary_ip4=None, tenant=None)
        mock_client.get_device_by_name.return_value = device
        mock_client.get_interfaces.return_value = []
        mock_client.get_ip_addresses.return_value = []

        sync = NetBoxSync(mock_client)
        result = sync.sync_ip_addresses("sw1", [])

        assert result["created"] == 0
        assert result["failed"] == 0

    def test_dry_run_counts_but_no_api(self, mock_client):
        """dry_run считает статистику но не вызывает API."""
        device = Mock(id=1, name="sw1", primary_ip4=None, tenant=None)
        intf = make_nb_intf("GigabitEthernet0/1")

        mock_client.get_device_by_name.return_value = device
        mock_client.get_interfaces.return_value = [intf]
        mock_client.get_ip_addresses.return_value = []

        sync = NetBoxSync(mock_client, dry_run=True)
        ip_data = [IPAddressEntry(ip_address="10.0.0.1", interface="GigabitEthernet0/1", mask="24")]

        result = sync.sync_ip_addresses("sw1", ip_data)

        assert result["created"] == 1
        mock_client.bulk_create_ip_addresses.assert_not_called()

    def test_create_new_ip(self, mock_client):
        """Новый IP создан через batch."""
        device = Mock(id=1, name="sw1", primary_ip4=None, tenant=None)
        intf = make_nb_intf("GigabitEthernet0/1")

        mock_client.get_device_by_name.return_value = device
        mock_client.get_interfaces.return_value = [intf]
        mock_client.get_ip_addresses.return_value = []
        mock_client.bulk_create_ip_addresses.return_value = [make_nb_ip()]

        sync = NetBoxSync(mock_client)
        ip_data = [IPAddressEntry(ip_address="10.0.0.1", interface="GigabitEthernet0/1", mask="24")]

        result = sync.sync_ip_addresses("sw1", ip_data)

        assert result["created"] == 1
        mock_client.bulk_create_ip_addresses.assert_called_once()


# ==================== BATCH CREATE ====================

class TestIPAddressBatchCreate:
    """Тесты batch создания IP."""

    def test_batch_create_with_correct_data(self, mock_client):
        """bulk_create вызван с правильными address/status/interface_id."""
        device = Mock(id=1, name="sw1", primary_ip4=None, tenant=None)
        intf = make_nb_intf("GigabitEthernet0/1", intf_id=42)

        mock_client.get_device_by_name.return_value = device
        mock_client.get_interfaces.return_value = [intf]
        mock_client.get_ip_addresses.return_value = []
        mock_client.bulk_create_ip_addresses.return_value = [make_nb_ip()]

        sync = NetBoxSync(mock_client)
        ip_data = [IPAddressEntry(ip_address="10.0.0.1", interface="GigabitEthernet0/1", mask="24")]

        sync.sync_ip_addresses("sw1", ip_data)

        # Проверяем что batch вызван
        call_args = mock_client.bulk_create_ip_addresses.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["address"] == "10.0.0.1/24"
        assert call_args[0]["status"] == "active"
        assert call_args[0]["assigned_object_id"] == 42

    def test_interface_not_found_fails(self, mock_client):
        """Интерфейс не найден → failed += 1."""
        device = Mock(id=1, name="sw1", primary_ip4=None, tenant=None)

        mock_client.get_device_by_name.return_value = device
        mock_client.get_interfaces.return_value = []  # Нет интерфейсов
        mock_client.get_ip_addresses.return_value = []

        sync = NetBoxSync(mock_client)
        ip_data = [IPAddressEntry(ip_address="10.0.0.1", interface="Gi0/99", mask="24")]

        result = sync.sync_ip_addresses("sw1", ip_data)

        assert result["failed"] == 1
        mock_client.bulk_create_ip_addresses.assert_not_called()

    def test_batch_fallback_on_error(self, mock_client):
        """Batch упал → fallback на поштучное создание."""
        device = Mock(id=1, name="sw1", primary_ip4=None, tenant=None)
        intf = make_nb_intf("GigabitEthernet0/1")

        mock_client.get_device_by_name.return_value = device
        mock_client.get_interfaces.return_value = [intf]
        mock_client.get_ip_addresses.return_value = []
        mock_client.bulk_create_ip_addresses.side_effect = Exception("batch error")
        mock_client.api.ipam.ip_addresses.create.return_value = make_nb_ip()

        sync = NetBoxSync(mock_client)
        ip_data = [IPAddressEntry(ip_address="10.0.0.1", interface="GigabitEthernet0/1", mask="24")]

        result = sync.sync_ip_addresses("sw1", ip_data)

        # Fallback на поштучное создание
        assert result["created"] == 1
        mock_client.api.ipam.ip_addresses.create.assert_called()


# ==================== UPDATE ====================

class TestIPAddressUpdate:
    """Тесты обновления IP-адресов."""

    def test_update_no_changes(self, mock_client):
        """Нет изменений → return False."""
        sync = NetBoxSync(mock_client)
        ip_obj = make_nb_ip()
        device = Mock(tenant=None)
        intf = make_nb_intf(intf_id=10)

        result = sync._update_ip_address(ip_obj, device, intf)

        assert result is False

    def test_update_interface_change(self, mock_client):
        """Интерфейс изменился → update()."""
        sync = NetBoxSync(mock_client)
        ip_obj = make_nb_ip(intf_id=10)
        device = Mock(tenant=None)
        intf = make_nb_intf(intf_id=20)  # Другой интерфейс

        result = sync._update_ip_address(ip_obj, device, intf)

        assert result is True
        ip_obj.update.assert_called_once()
        update_args = ip_obj.update.call_args[0][0]
        assert update_args["assigned_object_id"] == 20

    def test_update_mask_change_recreates(self, mock_client):
        """Маска изменилась → delete + create (пересоздание)."""
        sync = NetBoxSync(mock_client)
        ip_obj = make_nb_ip(address="10.0.0.1/24")
        device = Mock(tenant=None)
        intf = make_nb_intf()

        entry = IPAddressEntry(ip_address="10.0.0.1", interface="Gi0/1", mask="30")
        changes = [Mock(field="prefix_length", old_value="24", new_value="30")]

        mock_client.api.ipam.ip_addresses.create.return_value = make_nb_ip(address="10.0.0.1/30")

        result = sync._update_ip_address(ip_obj, device, intf, entry, changes)

        assert result is True
        ip_obj.delete.assert_called_once()
        mock_client.api.ipam.ip_addresses.create.assert_called_once()
        create_data = mock_client.api.ipam.ip_addresses.create.call_args[0][0]
        assert create_data["address"] == "10.0.0.1/30"

    def test_update_dry_run(self, mock_client):
        """dry_run → True, но API не вызывается."""
        sync = NetBoxSync(mock_client, dry_run=True)
        ip_obj = make_nb_ip(intf_id=10)
        device = Mock(tenant=None)
        intf = make_nb_intf(intf_id=20)

        result = sync._update_ip_address(ip_obj, device, intf)

        assert result is True
        ip_obj.update.assert_not_called()


# ==================== DELETE ====================

class TestIPAddressDelete:
    """Тесты удаления IP-адресов."""

    def test_batch_delete_dry_run(self, mock_client):
        """dry_run → stats["deleted"] считается, API не вызывается."""
        device = Mock(id=1, name="sw1", primary_ip4=None, tenant=None)
        existing_ip = make_nb_ip(address="10.0.0.99/24")

        mock_client.get_device_by_name.return_value = device
        mock_client.get_interfaces.return_value = []
        mock_client.get_ip_addresses.return_value = [existing_ip]

        sync = NetBoxSync(mock_client, dry_run=True)

        # Пустой список — все existing должны удалиться при cleanup
        result = sync.sync_ip_addresses("sw1", [], cleanup=True)

        assert result["deleted"] == 1
        mock_client.bulk_delete_ip_addresses.assert_not_called()


# ==================== PRIMARY IP ====================

class TestPrimaryIP:
    """Тесты установки primary IP."""

    def test_primary_ip_already_set(self, mock_client):
        """Primary IP уже установлен → skip (return False)."""
        sync = NetBoxSync(mock_client)
        device = Mock()
        device.primary_ip4 = Mock(address="10.0.0.1/24")

        result = sync._set_primary_ip(device, "10.0.0.1")

        assert result is False

    def test_primary_ip_set_from_existing(self, mock_client):
        """IP существует на устройстве → устанавливает primary."""
        sync = NetBoxSync(mock_client)
        device = Mock(id=1, primary_ip4=None)
        existing_ip = make_nb_ip(address="10.0.0.1/24", ip_id=42)

        mock_client.get_ip_addresses.return_value = [existing_ip]

        result = sync._set_primary_ip(device, "10.0.0.1")

        assert result is True
        device.save.assert_called_once()
        assert device.primary_ip4 == 42

    def test_primary_ip_creates_if_not_exists(self, mock_client):
        """IP не существует → создаёт и устанавливает primary."""
        sync = NetBoxSync(mock_client)
        device = Mock(id=1, primary_ip4=None)
        new_ip = make_nb_ip(address="10.0.0.1/32", ip_id=50)

        mock_client.get_ip_addresses.return_value = []
        mock_client.api.ipam.ip_addresses.get.return_value = None
        mock_client.get_interfaces.return_value = []
        mock_client.api.ipam.ip_addresses.create.return_value = new_ip

        result = sync._set_primary_ip(device, "10.0.0.1")

        assert result is True
        mock_client.api.ipam.ip_addresses.create.assert_called_once()

    def test_primary_ip_dry_run(self, mock_client):
        """dry_run → True, но API не вызывается."""
        sync = NetBoxSync(mock_client, dry_run=True)
        device = Mock(id=1, primary_ip4=None)

        mock_client.get_ip_addresses.return_value = []
        mock_client.api.ipam.ip_addresses.get.return_value = None

        result = sync._set_primary_ip(device, "10.0.0.1")

        assert result is True
        device.save.assert_not_called()

    def test_primary_ip_empty_string(self, mock_client):
        """Пустой ip_address → False."""
        sync = NetBoxSync(mock_client)
        device = Mock()

        result = sync._set_primary_ip(device, "")

        assert result is False
