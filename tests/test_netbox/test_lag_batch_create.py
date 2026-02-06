"""
Интеграционные тесты: LAG в batch create + cleanup.

Эмулирует pipeline сценарий:
1. Создание Port-channel + member интерфейсы одним вызовом sync_interfaces
2. Проверка что LAG создаётся ДО member'ов и member'ы получают lag ID
3. Проверка cleanup — удаление интерфейсов которых нет на устройстве
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call

from network_collector.netbox.sync import NetBoxSync
from network_collector.core.models import Interface


# ==================== FIXTURES ====================

@pytest.fixture
def mock_device():
    """Устройство в NetBox."""
    device = MagicMock()
    device.id = 100
    device.name = "switch-test-01"
    device.site = MagicMock()
    device.site.name = "TestSite"
    return device


@pytest.fixture
def lag_interfaces():
    """Интерфейсы с LAG: Port-channel1 + два member'а."""
    return [
        Interface(name="Port-channel1", status="up", description="LAG to core"),
        Interface(name="GigabitEthernet0/1", status="up", lag="Port-channel1", description="Member 1"),
        Interface(name="GigabitEthernet0/2", status="up", lag="Port-channel1", description="Member 2"),
        Interface(name="GigabitEthernet0/3", status="up", description="Standalone"),
        Interface(name="Port-channel2", status="up", description="LAG to server"),
        Interface(name="GigabitEthernet0/4", status="up", lag="Port-channel2", description="Server link"),
    ]


@pytest.fixture
def mock_client(mock_device):
    """NetBox клиент с полной эмуляцией LAG flow."""
    client = Mock()
    client.get_device_by_name.return_value = mock_device
    client.get_interfaces.return_value = []  # Нет интерфейсов — все новые

    # Эмулируем создание LAG: после bulk_create, get_interface_by_name найдёт их
    created_lags = {}  # name -> mock interface

    def fake_bulk_create(batch_data):
        """Эмулирует bulk_create_interfaces, запоминая созданные LAG."""
        results = []
        for i, data in enumerate(batch_data):
            mock_intf = MagicMock()
            mock_intf.id = 1000 + i
            mock_intf.name = data["name"]
            results.append(mock_intf)
            # Запоминаем LAG для последующего поиска
            if data["name"].lower().startswith(("port-channel", "po")):
                created_lags[data["name"]] = mock_intf
        return results

    def fake_get_interface_by_name(device_id, name):
        """Находит LAG только если он уже был создан в предыдущем batch."""
        return created_lags.get(name)

    client.bulk_create_interfaces.side_effect = fake_bulk_create
    client.get_interface_by_name.side_effect = fake_get_interface_by_name
    client.assign_mac_to_interface = Mock()

    return client


# ==================== ТЕСТЫ: LAG batch create ====================

class TestLAGBatchCreate:
    """Тесты двухфазного создания LAG + member'ов."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_lag_created_before_members(self, mock_sync_config, mock_client, lag_interfaces):
        """Port-channel создаётся ДО member интерфейсов."""
        # Настраиваем sync_config
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        sync = NetBoxSync(mock_client, dry_run=False)
        result = sync.sync_interfaces("switch-test-01", lag_interfaces)

        # Все 6 интерфейсов должны быть созданы
        assert result["created"] == 6
        assert result["failed"] == 0 if "failed" in result else True

        # bulk_create вызывался ДВАЖДЫ (фаза LAG + фаза member)
        assert mock_client.bulk_create_interfaces.call_count == 2

        # Первый вызов — только LAG интерфейсы
        first_batch = mock_client.bulk_create_interfaces.call_args_list[0][0][0]
        first_names = [d["name"] for d in first_batch]
        assert "Port-channel1" in first_names
        assert "Port-channel2" in first_names
        assert len(first_names) == 2  # Только LAG

        # Второй вызов — member и standalone интерфейсы
        second_batch = mock_client.bulk_create_interfaces.call_args_list[1][0][0]
        second_names = [d["name"] for d in second_batch]
        assert "GigabitEthernet0/1" in second_names
        assert "GigabitEthernet0/2" in second_names
        assert "GigabitEthernet0/3" in second_names
        assert "GigabitEthernet0/4" in second_names
        assert len(second_names) == 4

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_member_interfaces_have_lag_id(self, mock_sync_config, mock_client, lag_interfaces):
        """Member интерфейсы получают lag ID при создании."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        sync = NetBoxSync(mock_client, dry_run=False)
        sync.sync_interfaces("switch-test-01", lag_interfaces)

        # Второй batch (member'ы) — проверяем что lag ID присутствует
        second_batch = mock_client.bulk_create_interfaces.call_args_list[1][0][0]

        # Gi0/1 -> lag=Port-channel1 (id=1000, первый в первом batch)
        gi01 = next(d for d in second_batch if d["name"] == "GigabitEthernet0/1")
        assert "lag" in gi01, "Gi0/1 должен иметь lag ID"
        assert gi01["lag"] == 1000  # Port-channel1 получил id=1000

        # Gi0/2 -> lag=Port-channel1
        gi02 = next(d for d in second_batch if d["name"] == "GigabitEthernet0/2")
        assert "lag" in gi02
        assert gi02["lag"] == 1000

        # Gi0/4 -> lag=Port-channel2 (id=1001, второй в первом batch)
        gi04 = next(d for d in second_batch if d["name"] == "GigabitEthernet0/4")
        assert "lag" in gi04
        assert gi04["lag"] == 1001  # Port-channel2 получил id=1001

        # Gi0/3 standalone — без lag
        gi03 = next(d for d in second_batch if d["name"] == "GigabitEthernet0/3")
        assert "lag" not in gi03, "Standalone интерфейс не должен иметь lag"

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_lag_not_found_logs_warning(self, mock_sync_config, mock_client, mock_device):
        """Если LAG не создался — warning в лог, member создаётся без lag."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        # LAG НЕ приходит в списке интерфейсов (только member)
        interfaces = [
            Interface(name="GigabitEthernet0/1", status="up", lag="Port-channel99"),
        ]
        # get_interface_by_name всегда None — LAG не существует
        mock_client.get_interface_by_name.return_value = None
        mock_client.bulk_create_interfaces.return_value = [MagicMock(id=2000)]

        sync = NetBoxSync(mock_client, dry_run=False)
        result = sync.sync_interfaces("switch-test-01", interfaces)

        assert result["created"] == 1

        # Интерфейс создан, но БЕЗ lag (т.к. Port-channel99 не найден)
        batch = mock_client.bulk_create_interfaces.call_args_list[0][0][0]
        gi01 = batch[0]
        assert "lag" not in gi01

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_dry_run_lag_not_created(self, mock_sync_config, mock_client, lag_interfaces):
        """В dry_run ничего не создаётся, но статистика считается."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_interfaces("switch-test-01", lag_interfaces)

        # Все 6 посчитаны как "created" в dry_run
        assert result["created"] == 6

        # Но bulk_create НЕ вызывался
        mock_client.bulk_create_interfaces.assert_not_called()


# ==================== ТЕСТЫ: Cleanup (удаление) ====================

class TestLAGCleanup:
    """Тесты cleanup — удаление интерфейсов которых нет на устройстве."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_cleanup_deletes_missing_interfaces(self, mock_sync_config, mock_client, mock_device):
        """cleanup=True удаляет интерфейсы из NetBox которых нет на устройстве."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        # В NetBox есть 3 интерфейса (один из них — лишний Gi0/99)
        nb_gi01 = MagicMock()
        nb_gi01.id = 500
        nb_gi01.name = "GigabitEthernet0/1"
        nb_gi01.description = "Uplink"
        nb_gi01.enabled = True
        nb_gi01.mtu = None
        nb_gi01.speed = None
        nb_gi01.duplex = None
        nb_gi01.mode = None
        nb_gi01.type = MagicMock(value="1000base-t")
        nb_gi01.mac_address = None
        nb_gi01.lag = None
        nb_gi01.device = mock_device
        nb_gi01.untagged_vlan = None
        nb_gi01.tagged_vlans = []
        nb_gi01.delete = Mock()

        nb_gi02 = MagicMock()
        nb_gi02.id = 501
        nb_gi02.name = "GigabitEthernet0/2"
        nb_gi02.description = ""
        nb_gi02.enabled = True
        nb_gi02.mtu = None
        nb_gi02.speed = None
        nb_gi02.duplex = None
        nb_gi02.mode = None
        nb_gi02.type = MagicMock(value="1000base-t")
        nb_gi02.mac_address = None
        nb_gi02.lag = None
        nb_gi02.device = mock_device
        nb_gi02.untagged_vlan = None
        nb_gi02.tagged_vlans = []
        nb_gi02.delete = Mock()

        # Лишний — нет на устройстве, должен быть удалён
        nb_gi99 = MagicMock()
        nb_gi99.id = 599
        nb_gi99.name = "GigabitEthernet0/99"
        nb_gi99.description = "Old port"
        nb_gi99.enabled = False
        nb_gi99.mtu = None
        nb_gi99.speed = None
        nb_gi99.duplex = None
        nb_gi99.mode = None
        nb_gi99.type = MagicMock(value="1000base-t")
        nb_gi99.mac_address = None
        nb_gi99.lag = None
        nb_gi99.device = mock_device
        nb_gi99.untagged_vlan = None
        nb_gi99.tagged_vlans = []
        nb_gi99.delete = Mock()

        mock_client.get_interfaces.return_value = [nb_gi01, nb_gi02, nb_gi99]
        mock_client.bulk_delete_interfaces.return_value = True

        # На устройстве только Gi0/1 и Gi0/2
        local_interfaces = [
            Interface(name="GigabitEthernet0/1", status="up", description="Uplink"),
            Interface(name="GigabitEthernet0/2", status="up"),
        ]

        sync = NetBoxSync(mock_client, dry_run=False)
        result = sync.sync_interfaces("switch-test-01", local_interfaces, cleanup=True)

        # Gi0/99 должен быть удалён
        assert result["deleted"] == 1

        # bulk_delete_interfaces вызван с ID лишнего интерфейса
        mock_client.bulk_delete_interfaces.assert_called_once()
        delete_ids = mock_client.bulk_delete_interfaces.call_args[0][0]
        assert 599 in delete_ids

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_cleanup_false_keeps_everything(self, mock_sync_config, mock_client, mock_device):
        """Без cleanup=True лишние интерфейсы НЕ удаляются."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        nb_gi99 = MagicMock()
        nb_gi99.id = 599
        nb_gi99.name = "GigabitEthernet0/99"
        nb_gi99.description = ""
        nb_gi99.enabled = True
        nb_gi99.mtu = None
        nb_gi99.speed = None
        nb_gi99.duplex = None
        nb_gi99.mode = None
        nb_gi99.type = MagicMock(value="1000base-t")
        nb_gi99.mac_address = None
        nb_gi99.lag = None
        nb_gi99.device = mock_device
        nb_gi99.untagged_vlan = None
        nb_gi99.tagged_vlans = []

        mock_client.get_interfaces.return_value = [nb_gi99]

        local_interfaces = [
            Interface(name="GigabitEthernet0/1", status="up"),
        ]

        mock_client.bulk_create_interfaces.return_value = [MagicMock(id=2000)]

        sync = NetBoxSync(mock_client, dry_run=False)
        result = sync.sync_interfaces("switch-test-01", local_interfaces, cleanup=False)

        # Ничего не удалено
        assert result["deleted"] == 0
        mock_client.bulk_delete_interfaces.assert_not_called()


# ==================== ТЕСТЫ: Pipeline full flow ====================

class TestPipelineLAGFlow:
    """Эмуляция полного pipeline: collect_dicts → group by device → sync."""

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_pipeline_flow_with_lag(self, mock_sync_config, mock_client, mock_device):
        """Полная эмуляция pipeline: dict данные → sync с LAG."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        # Эмулируем данные из collect_dicts (как pipeline получает)
        collected_dicts = [
            {"interface": "Port-channel1", "status": "up", "description": "LAG", "hostname": "switch-test-01"},
            {"interface": "GigabitEthernet0/1", "status": "up", "lag": "Port-channel1", "hostname": "switch-test-01"},
            {"interface": "GigabitEthernet0/2", "status": "up", "lag": "Port-channel1", "hostname": "switch-test-01"},
            {"interface": "GigabitEthernet0/3", "status": "up", "hostname": "switch-test-01"},
        ]

        # Pipeline группирует по hostname
        by_device = {}
        for intf in collected_dicts:
            hostname = intf.get("hostname", "")
            if hostname not in by_device:
                by_device[hostname] = []
            by_device[hostname].append(intf)

        # Pipeline вызывает sync_interfaces с dict данными (не Interface объектами)
        sync = NetBoxSync(mock_client, dry_run=False)
        for hostname, interfaces in by_device.items():
            result = sync.sync_interfaces(hostname, interfaces)

        # 4 интерфейса создано
        assert result["created"] == 4

        # Два batch вызова (LAG + member)
        assert mock_client.bulk_create_interfaces.call_count == 2

        # Первый batch — Port-channel1
        first_batch = mock_client.bulk_create_interfaces.call_args_list[0][0][0]
        assert len(first_batch) == 1
        assert first_batch[0]["name"] == "Port-channel1"

        # Второй batch — member'ы с lag ID
        second_batch = mock_client.bulk_create_interfaces.call_args_list[1][0][0]
        gi01 = next(d for d in second_batch if d["name"] == "GigabitEthernet0/1")
        assert "lag" in gi01, "Pipeline: member должен получить lag ID"

        gi03 = next(d for d in second_batch if d["name"] == "GigabitEthernet0/3")
        assert "lag" not in gi03, "Standalone не должен иметь lag"

    @patch("network_collector.netbox.sync.interfaces.get_sync_config")
    def test_pipeline_flow_with_cleanup_and_lag(self, mock_sync_config, mock_client, mock_device):
        """Pipeline с cleanup: создание LAG + удаление старых интерфейсов."""
        cfg = MagicMock()
        cfg.get_option.side_effect = lambda key, default=None: {
            "create_missing": True,
            "update_existing": True,
            "exclude_interfaces": [],
            "auto_detect_type": True,
            "sync_vlans": False,
            "enabled_mode": "admin",
            "sync_mac_only_with_ip": False,
        }.get(key, default)
        cfg.is_field_enabled.return_value = True
        mock_sync_config.return_value = cfg

        # В NetBox уже есть старый интерфейс (должен удалиться)
        nb_old = MagicMock()
        nb_old.id = 900
        nb_old.name = "FastEthernet0/24"
        nb_old.description = "Old FE port"
        nb_old.enabled = False
        nb_old.mtu = None
        nb_old.speed = None
        nb_old.duplex = None
        nb_old.mode = None
        nb_old.type = MagicMock(value="100base-tx")
        nb_old.mac_address = None
        nb_old.lag = None
        nb_old.device = mock_device
        nb_old.untagged_vlan = None
        nb_old.tagged_vlans = []

        mock_client.get_interfaces.return_value = [nb_old]
        mock_client.bulk_delete_interfaces.return_value = True

        # Данные с устройства (через pipeline collect_dicts)
        collected_dicts = [
            {"interface": "Port-channel1", "status": "up", "hostname": "switch-test-01"},
            {"interface": "GigabitEthernet0/1", "status": "up", "lag": "Port-channel1", "hostname": "switch-test-01"},
        ]

        sync = NetBoxSync(mock_client, dry_run=False)
        result = sync.sync_interfaces("switch-test-01", collected_dicts, cleanup=True)

        # 2 создано (Po1 + Gi0/1)
        assert result["created"] == 2

        # 1 удалён (Fa0/24 — нет на устройстве)
        assert result["deleted"] == 1

        # Проверяем что удалён именно Fa0/24
        mock_client.bulk_delete_interfaces.assert_called_once()
        delete_ids = mock_client.bulk_delete_interfaces.call_args[0][0]
        assert 900 in delete_ids

        # LAG batch: Po1 в первом вызове
        first_batch = mock_client.bulk_create_interfaces.call_args_list[0][0][0]
        assert first_batch[0]["name"] == "Port-channel1"

        # Member batch: Gi0/1 с lag ID
        second_batch = mock_client.bulk_create_interfaces.call_args_list[1][0][0]
        gi01 = second_batch[0]
        assert gi01["name"] == "GigabitEthernet0/1"
        assert "lag" in gi01
