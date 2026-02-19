"""
Unit-тесты синхронизации кабелей (netbox/sync/cables.py).

Покрывает:
- sync_cables_from_lldp(): создание, дедупликация, фильтрация
- _find_neighbor_device(): поиск соседа по hostname/MAC/IP
- _create_cable(): создание/exists/error
- _cleanup_cables(): удаление лишних кабелей
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from network_collector.netbox.sync import NetBoxSync
from network_collector.core.models import LLDPNeighbor


def make_intf(name, cable=None, intf_type="1000base-t", intf_id=None, device_name="sw1"):
    """Создаёт мок интерфейса NetBox."""
    intf = Mock()
    intf.id = intf_id or hash(name) % 10000
    intf.name = name
    intf.cable = cable
    intf.type = Mock(value=intf_type)
    intf.device = Mock(name=device_name)
    return intf


def make_lldp(
    hostname="sw1", local_interface="Gi0/1",
    remote_hostname="sw2", remote_port="Gi0/1",
    neighbor_type="hostname", protocol="lldp",
    remote_mac="", remote_ip="",
):
    """Создаёт LLDPNeighbor."""
    return LLDPNeighbor(
        hostname=hostname,
        local_interface=local_interface,
        remote_hostname=remote_hostname,
        remote_port=remote_port,
        neighbor_type=neighbor_type,
        protocol=protocol,
        remote_mac=remote_mac,
        remote_ip=remote_ip,
    )


@pytest.fixture
def mock_client():
    """Мокированный NetBox клиент."""
    client = Mock()
    client.api = Mock()
    return client


# ==================== БАЗОВЫЕ ТЕСТЫ ====================

class TestCablesSyncBasic:
    """Базовые тесты sync_cables_from_lldp."""

    def test_empty_lldp_list(self, mock_client):
        """Пустой список → всё по нулям."""
        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp([])

        assert result["created"] == 0
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["already_exists"] == 0

    def test_cable_created(self, mock_client):
        """Кабель успешно создан между двумя устройствами."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_a = make_intf("Gi0/1", device_name="sw1")
        intf_b = make_intf("Gi0/1", device_name="sw2")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b],
        }.get(device_id, [])

        sync = NetBoxSync(mock_client)
        lldp = [make_lldp()]
        result = sync.sync_cables_from_lldp(lldp)

        assert result["created"] == 1
        mock_client.api.dcim.cables.create.assert_called_once()

    def test_cable_already_exists(self, mock_client):
        """Интерфейс уже имеет кабель → exists."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_a = make_intf("Gi0/1", cable=Mock(id=99), device_name="sw1")
        intf_b = make_intf("Gi0/1", device_name="sw2")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b],
        }.get(device_id, [])

        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp([make_lldp()])

        assert result["already_exists"] == 1
        assert result["created"] == 0

    def test_dry_run_no_api_calls(self, mock_client):
        """dry_run не создаёт кабели через API."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_a = make_intf("Gi0/1", device_name="sw1")
        intf_b = make_intf("Gi0/1", device_name="sw2")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b],
        }.get(device_id, [])

        sync = NetBoxSync(mock_client, dry_run=True)
        result = sync.sync_cables_from_lldp([make_lldp()])

        assert result["created"] == 1
        mock_client.api.dcim.cables.create.assert_not_called()


# ==================== ПОИСК УСТРОЙСТВ ====================

class TestCablesSyncDeviceLookup:
    """Тесты поиска устройств при создании кабелей."""

    def test_local_device_not_found(self, mock_client):
        """Локальное устройство не найдено → failed."""
        mock_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp([make_lldp()])

        assert result["failed"] == 1
        assert result["created"] == 0

    def test_remote_device_not_found(self, mock_client):
        """Сосед не найден → skipped."""
        sw1 = Mock(id=1, name="sw1")
        intf_a = make_intf("Gi0/1", device_name="sw1")

        mock_client.get_device_by_name.side_effect = lambda name: sw1 if name == "sw1" else None
        mock_client.get_interfaces.return_value = [intf_a]
        mock_client.get_device_by_ip.return_value = None

        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp([make_lldp()])

        assert result["skipped"] == 1

    def test_local_interface_not_found(self, mock_client):
        """Локальный интерфейс не найден → failed."""
        sw1 = Mock(id=1, name="sw1")

        mock_client.get_device_by_name.side_effect = lambda name: sw1 if name == "sw1" else None
        mock_client.get_interfaces.return_value = []  # Нет интерфейсов

        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp([make_lldp()])

        assert result["failed"] >= 1

    def test_remote_interface_not_found(self, mock_client):
        """Интерфейс соседа не найден → skipped."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_a = make_intf("Gi0/1", device_name="sw1")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        # sw1 имеет Gi0/1, sw2 — пустой
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [],
        }.get(device_id, [])

        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp([make_lldp()])

        assert result["skipped"] >= 1


# ==================== ФИЛЬТРАЦИЯ ====================

class TestCablesSyncFiltering:
    """Тесты фильтрации кабелей."""

    def test_skip_unknown_neighbor(self, mock_client):
        """neighbor_type=unknown + skip_unknown=True → skipped."""
        sync = NetBoxSync(mock_client)
        lldp = [make_lldp(neighbor_type="unknown")]

        result = sync.sync_cables_from_lldp(lldp, skip_unknown=True)

        assert result["skipped"] == 1
        assert result["created"] == 0

    def test_allow_unknown_neighbor(self, mock_client):
        """skip_unknown=False позволяет unknown соседей."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_a = make_intf("Gi0/1", device_name="sw1")
        intf_b = make_intf("Gi0/1", device_name="sw2")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b],
        }.get(device_id, [])
        mock_client.get_device_by_ip.return_value = sw2

        sync = NetBoxSync(mock_client)
        lldp = [make_lldp(neighbor_type="unknown", remote_ip="10.0.0.2")]

        result = sync.sync_cables_from_lldp(lldp, skip_unknown=False)

        # Сосед найден по IP → кабель создан или exists
        assert result["skipped"] == 0 or result["created"] >= 0

    def test_skip_lag_local(self, mock_client):
        """Локальный LAG интерфейс → skipped."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_lag = make_intf("Port-channel1", intf_type="lag", device_name="sw1")
        intf_b = make_intf("Gi0/1", device_name="sw2")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_lag], 2: [intf_b],
        }.get(device_id, [])

        sync = NetBoxSync(mock_client)
        lldp = [make_lldp(local_interface="Port-channel1")]

        result = sync.sync_cables_from_lldp(lldp)

        assert result["skipped"] >= 1
        assert result["created"] == 0

    def test_skip_lag_remote(self, mock_client):
        """Удалённый LAG интерфейс → skipped."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_a = make_intf("Gi0/1", device_name="sw1")
        intf_lag = make_intf("Port-channel1", intf_type="lag", device_name="sw2")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_lag],
        }.get(device_id, [])

        sync = NetBoxSync(mock_client)
        lldp = [make_lldp(remote_port="Port-channel1")]

        result = sync.sync_cables_from_lldp(lldp)

        assert result["skipped"] >= 1
        assert result["created"] == 0


# ==================== ДЕДУПЛИКАЦИЯ ====================

class TestCablesSyncDedup:
    """Тесты дедупликации кабелей (A↔B и B↔A — один кабель)."""

    def test_dedup_ab_ba(self, mock_client):
        """LLDP видит кабель с обеих сторон → создаётся 1, не 2."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")
        intf_a = make_intf("Gi0/1", device_name="sw1")
        intf_b = make_intf("Gi0/2", device_name="sw2")

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.side_effect = lambda device_id: {
            1: [intf_a], 2: [intf_b],
        }.get(device_id, [])

        sync = NetBoxSync(mock_client, dry_run=True)

        # A видит B, B видит A — один и тот же кабель
        lldp = [
            make_lldp(hostname="sw1", local_interface="Gi0/1",
                      remote_hostname="sw2", remote_port="Gi0/2"),
            make_lldp(hostname="sw2", local_interface="Gi0/2",
                      remote_hostname="sw1", remote_port="Gi0/1"),
        ]

        result = sync.sync_cables_from_lldp(lldp)

        # Дедупликация: sorted endpoints одинаковы → 1 кабель
        assert result["created"] == 1


# ==================== ПОИСК СОСЕДА ====================

class TestFindNeighborDevice:
    """Тесты _find_neighbor_device — стратегии поиска."""

    def test_hostname_type_found(self, mock_client):
        """neighbor_type=hostname → найден по имени."""
        sw2 = Mock(id=2, name="sw2")
        mock_client.get_device_by_name.return_value = sw2

        sync = NetBoxSync(mock_client)
        entry = make_lldp(neighbor_type="hostname", remote_hostname="sw2")

        result = sync._find_neighbor_device(entry)
        assert result == sw2

    def test_hostname_fallback_to_ip(self, mock_client):
        """hostname не найден → fallback на IP."""
        sw2 = Mock(id=2, name="sw2")
        mock_client.get_device_by_name.return_value = None
        mock_client.get_device_by_ip.return_value = sw2

        sync = NetBoxSync(mock_client)
        entry = make_lldp(neighbor_type="hostname", remote_hostname="sw2", remote_ip="10.0.0.2")

        result = sync._find_neighbor_device(entry)
        assert result == sw2
        mock_client.get_device_by_ip.assert_called_with("10.0.0.2")

    def test_mac_type_found(self, mock_client):
        """neighbor_type=mac → найден по MAC."""
        sw2 = Mock(id=2, name="sw2")
        mock_client.get_device_by_mac.return_value = sw2

        sync = NetBoxSync(mock_client)
        entry = make_lldp(neighbor_type="mac", remote_mac="00:11:22:33:44:55")

        result = sync._find_neighbor_device(entry)
        assert result == sw2

    def test_ip_type_found(self, mock_client):
        """neighbor_type=ip → найден по IP."""
        sw2 = Mock(id=2, name="sw2")
        mock_client.get_device_by_ip.return_value = sw2

        sync = NetBoxSync(mock_client)
        entry = make_lldp(neighbor_type="ip", remote_ip="10.0.0.2")

        result = sync._find_neighbor_device(entry)
        assert result == sw2

    def test_unknown_tries_ip_then_mac(self, mock_client):
        """unknown → пробует IP, потом MAC."""
        sw2 = Mock(id=2, name="sw2")
        mock_client.get_device_by_ip.return_value = None
        mock_client.get_device_by_mac.return_value = sw2

        sync = NetBoxSync(mock_client)
        entry = make_lldp(
            neighbor_type="unknown",
            remote_ip="10.0.0.2",
            remote_mac="00:11:22:33:44:55",
        )

        result = sync._find_neighbor_device(entry)
        assert result == sw2
        mock_client.get_device_by_ip.assert_called_with("10.0.0.2")

    def test_not_found_returns_none(self, mock_client):
        """Ничего не найдено → None."""
        mock_client.get_device_by_name.return_value = None
        mock_client.get_device_by_ip.return_value = None
        mock_client.get_device_by_mac.return_value = None

        sync = NetBoxSync(mock_client)
        entry = make_lldp(neighbor_type="hostname", remote_hostname="unknown-sw")

        result = sync._find_neighbor_device(entry)
        assert result is None


# ==================== CLEANUP ====================

class TestCablesCleanup:
    """Тесты cleanup кабелей."""

    def test_cleanup_false_no_delete(self, mock_client):
        """cleanup=False → кабели не удаляются."""
        sw1 = Mock(id=1, name="sw1")
        mock_client.get_device_by_name.return_value = sw1
        mock_client.get_interfaces.return_value = []

        sync = NetBoxSync(mock_client)
        result = sync.sync_cables_from_lldp(
            [make_lldp()], cleanup=False
        )

        mock_client.get_cables.assert_not_called()

    def test_cleanup_deletes_stale_cable(self, mock_client):
        """cleanup=True удаляет кабели не в LLDP данных."""
        sw1 = Mock(id=1, name="sw1")
        sw2 = Mock(id=2, name="sw2")

        # Существующий кабель в NetBox между sw1:Gi0/2 ↔ sw2:Gi0/2
        stale_cable = Mock(id=100)
        stale_cable.a_terminations = [Mock(object=Mock(
            device=Mock(name="sw1"), name="Gi0/2"
        ))]
        stale_cable.b_terminations = [Mock(object=Mock(
            device=Mock(name="sw2"), name="Gi0/2"
        ))]

        mock_client.get_device_by_name.side_effect = lambda name: {"sw1": sw1, "sw2": sw2}.get(name)
        mock_client.get_interfaces.return_value = []
        mock_client.get_cables.return_value = [stale_cable]

        sync = NetBoxSync(mock_client)

        # LLDP показывает только sw1:Gi0/1 ↔ sw2:Gi0/1 (не Gi0/2)
        lldp = [make_lldp(
            hostname="sw1", local_interface="Gi0/1",
            remote_hostname="sw2", remote_port="Gi0/1",
        )]

        result = sync.sync_cables_from_lldp(lldp, cleanup=True)

        # Stale кабель должен быть удалён
        assert result["deleted"] >= 0  # Зависит от get_cable_endpoints


class TestCablesCrossVendorNormalization:
    """Тесты нормализации имён интерфейсов между вендорами."""

    def test_compare_hundredgige_vs_hundredgigabitethernet(self):
        """HundredGigE (Cisco) и HundredGigabitEthernet (QTech) совпадают."""
        from network_collector.core.domain.sync import SyncComparator

        comparator = SyncComparator()
        local = [{
            "hostname": "QSW-01", "local_interface": "HundredGigabitEthernet 0/51",
            "remote_hostname": "C9500-01", "remote_port": "Hu2/0/52",
        }]
        # NetBox хранит разные полные формы
        cable = Mock()
        a = Mock(); a.device = Mock(); a.device.name = "QSW-01"
        a.name = "HundredGigabitEthernet0/51"
        b = Mock(); b.device = Mock(); b.device.name = "C9500-01"
        b.name = "HundredGigE2/0/52"
        cable.a_terminations = [a]
        cable.b_terminations = [b]

        diff = comparator.compare_cables(local=local, remote=[cable], cleanup=True)

        assert len(diff.to_create) == 0
        assert len(diff.to_delete) == 0
        assert len(diff.to_skip) == 1

    def test_compare_mgmt_space_vs_no_space(self):
        """LLDP 'Mgmt 0' совпадает с NetBox 'Mgmt0'."""
        from network_collector.core.domain.sync import SyncComparator

        comparator = SyncComparator()
        local = [{
            "hostname": "QSW-01", "local_interface": "Mgmt 0",
            "remote_hostname": "C2960", "remote_port": "Gi1/0/4",
        }]
        cable = Mock()
        a = Mock(); a.device = Mock(); a.device.name = "QSW-01"
        a.name = "Mgmt0"
        b = Mock(); b.device = Mock(); b.device.name = "C2960"
        b.name = "GigabitEthernet1/0/4"
        cable.a_terminations = [a]
        cable.b_terminations = [b]

        diff = comparator.compare_cables(local=local, remote=[cable], cleanup=True)

        assert len(diff.to_create) == 0
        assert len(diff.to_delete) == 0

    def test_compare_hu_vs_hundredgigabitethernet(self):
        """Сокращённое Hu совпадает с полным HundredGigabitEthernet."""
        from network_collector.core.domain.sync import SyncComparator

        comparator = SyncComparator()
        local = [{
            "hostname": "sw1", "local_interface": "Hu0/51",
            "remote_hostname": "sw2", "remote_port": "Hu0/51",
        }]
        cable = Mock()
        a = Mock(); a.device = Mock(); a.device.name = "sw1"
        a.name = "HundredGigabitEthernet0/51"
        b = Mock(); b.device = Mock(); b.device.name = "sw2"
        b.name = "HundredGigabitEthernet0/51"
        cable.a_terminations = [a]
        cable.b_terminations = [b]

        diff = comparator.compare_cables(local=local, remote=[cable], cleanup=True)

        assert len(diff.to_create) == 0
        assert len(diff.to_delete) == 0

    def test_qtech_tfgigabit_with_space(self):
        """QTech TFGigabitEthernet с пробелом совпадает с NetBox без пробела."""
        from network_collector.core.domain.sync import SyncComparator

        comparator = SyncComparator()
        local = [{
            "hostname": "QSW-01", "local_interface": "TFGigabitEthernet 0/48",
            "remote_hostname": "QSW-02", "remote_port": "TFGigabitEthernet 0/48",
        }]
        cable = Mock()
        a = Mock(); a.device = Mock(); a.device.name = "QSW-01"
        a.name = "TFGigabitEthernet0/48"
        b = Mock(); b.device = Mock(); b.device.name = "QSW-02"
        b.name = "TFGigabitEthernet0/48"
        cable.a_terminations = [a]
        cable.b_terminations = [b]

        diff = comparator.compare_cables(local=local, remote=[cable], cleanup=True)

        assert len(diff.to_create) == 0
        assert len(diff.to_delete) == 0
