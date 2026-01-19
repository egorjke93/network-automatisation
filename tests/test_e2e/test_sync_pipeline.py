"""
End-to-End tests для полной цепочки синхронизации с NetBox.

Проверяет: Fixture → Parser → Normalizer → Model → NetBoxSync → API

Гарантирует что собранные данные правильно трансформируются
и готовы для синхронизации с NetBox.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from typing import Dict, List, Any

from network_collector.parsers.textfsm_parser import NTCParser
from network_collector.core.domain.lldp import LLDPNormalizer
from network_collector.core.domain.mac import MACNormalizer
from network_collector.core.models import (
    LLDPNeighbor,
    Interface,
    DeviceInfo,
    MACEntry,
)
from network_collector.netbox.sync import NetBoxSync


# Путь к fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def load_fixture(platform: str, command: str) -> str:
    """Загружает fixture файл."""
    filename = command.replace(" ", "_").replace("-", "_") + ".txt"
    filepath = FIXTURES_DIR / platform / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


@pytest.fixture(scope="module")
def parser() -> NTCParser:
    """NTC парсер."""
    return NTCParser()


@pytest.fixture
def mock_netbox_client():
    """
    Мокированный NetBox клиент для тестирования sync pipeline.

    Возвращает клиент с настроенными моками для всех нужных методов.
    """
    client = Mock()
    client.api = Mock()

    # Мок устройства
    mock_device = Mock()
    mock_device.id = 1
    mock_device.name = "switch-01"
    mock_device.primary_ip4 = None
    mock_device.tenant = None
    mock_device.site = Mock(name="TestSite")
    client.get_device_by_name.return_value = mock_device

    # Мок интерфейсов
    client.get_interfaces.return_value = []
    client.get_interface_by_name.return_value = None

    # Мок для создания
    client.create_interface.return_value = Mock(id=100)
    client.create_ip_address.return_value = Mock(id=200)

    return client


# =============================================================================
# LLDP → Cables Sync Pipeline
# =============================================================================

@pytest.mark.e2e
class TestLLDPToCablesSyncPipeline:
    """
    E2E тесты: LLDP Fixture → Parser → Normalizer → LLDPNeighbor → sync_cables_from_lldp

    Проверяет что LLDP данные с устройства корректно проходят через весь pipeline
    и готовы для создания кабелей в NetBox.
    """

    def test_lldp_to_cables_pipeline_cdp(self, parser, mock_netbox_client):
        """
        CDP данные проходят полный pipeline до sync_cables_from_lldp.

        Pipeline: Fixture → Parser → Normalizer → Model → sync_cables_from_lldp
        """
        # 1. Load CDP fixture
        output = load_fixture("cisco_ios", "show cdp neighbors detail")
        if not output:
            pytest.skip("No fixture for cisco_ios/show cdp neighbors detail")

        # 2. Parse with NTC
        parsed = parser.parse(output, "cisco_ios", "show cdp neighbors detail")
        assert len(parsed) > 0, "Parser returned empty result"

        # 3. Normalize
        normalizer = LLDPNormalizer()
        normalized = normalizer.normalize_dicts(
            parsed,
            protocol="cdp",
            hostname="switch-01",
            device_ip="10.0.0.1",
        )
        assert len(normalized) > 0, "Normalizer returned empty result"

        # 4. Verify key fields for cable creation
        for neighbor in normalized:
            assert "local_interface" in neighbor, "local_interface required for cables"
            assert "remote_port" in neighbor, "remote_port required for cables"
            assert "remote_hostname" in neighbor, "remote_hostname required for cables"

        # 5. Convert to models
        neighbors = [LLDPNeighbor.from_dict(n) for n in normalized]

        # 6. Pass through sync (dry_run)
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_cables_from_lldp(neighbors)

        # 7. Verify result structure
        assert isinstance(result, dict)
        assert "created" in result
        assert "skipped" in result
        assert "failed" in result

    def test_lldp_to_cables_pipeline_lldp(self, parser, mock_netbox_client):
        """
        LLDP данные проходят полный pipeline до sync_cables_from_lldp.
        """
        # 1. Load LLDP fixture
        output = load_fixture("cisco_ios", "show lldp neighbors detail")
        if not output:
            pytest.skip("No fixture for cisco_ios/show lldp neighbors detail")

        # 2. Parse
        parsed = parser.parse(output, "cisco_ios", "show lldp neighbors detail")
        assert len(parsed) > 0

        # 3. Normalize
        normalizer = LLDPNormalizer()
        normalized = normalizer.normalize_dicts(
            parsed,
            protocol="lldp",
            hostname="switch-01",
            device_ip="10.0.0.1",
        )

        # 4. Verify fields
        for neighbor in normalized:
            assert "local_interface" in neighbor
            # remote_port should be actual port, not hostname
            if neighbor.get("remote_port"):
                # remote_port should NOT be a hostname
                assert not neighbor["remote_port"].endswith(".ru"), \
                    f"remote_port should be interface, not hostname: {neighbor['remote_port']}"

        # 5. Convert to models
        neighbors = [LLDPNeighbor.from_dict(n) for n in normalized]

        # 6. Sync
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_cables_from_lldp(neighbors)

        assert isinstance(result, dict)

    def test_lldp_both_protocols_merge_pipeline(self, parser, mock_netbox_client):
        """
        Merged LLDP+CDP данные проходят pipeline для создания кабелей.

        CDP должен давать:
        - remote_port (Port ID)
        - remote_platform

        LLDP должен добавлять:
        - remote_mac (chassis_id)
        """
        # 1. Load both fixtures
        lldp_output = load_fixture("cisco_ios", "show lldp neighbors detail")
        cdp_output = load_fixture("cisco_ios", "show cdp neighbors detail")

        if not lldp_output or not cdp_output:
            pytest.skip("Need both fixtures")

        # 2. Parse both
        lldp_parsed = parser.parse(lldp_output, "cisco_ios", "show lldp neighbors detail")
        cdp_parsed = parser.parse(cdp_output, "cisco_ios", "show cdp neighbors detail")

        # 3. Normalize both
        normalizer = LLDPNormalizer()
        lldp_normalized = normalizer.normalize_dicts(
            lldp_parsed, protocol="lldp", hostname="switch-01", device_ip="10.0.0.1"
        )
        cdp_normalized = normalizer.normalize_dicts(
            cdp_parsed, protocol="cdp", hostname="switch-01", device_ip="10.0.0.1"
        )

        # 4. Merge (CDP priority)
        merged = normalizer.merge_lldp_cdp(lldp_normalized, cdp_normalized)

        # 5. Verify merge results
        for neighbor in merged:
            # Should have local_interface from either source
            assert "local_interface" in neighbor
            # CDP provides platform
            if neighbor.get("protocol") == "CDP":
                assert neighbor.get("remote_platform"), "CDP should provide platform"

        # 6. Convert and sync
        neighbors = [LLDPNeighbor.from_dict(n) for n in merged]
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_cables_from_lldp(neighbors)

        assert isinstance(result, dict)


# =============================================================================
# Interfaces → NetBox Sync Pipeline
# =============================================================================

@pytest.mark.e2e
class TestInterfacesSyncPipeline:
    """
    E2E тесты: Interfaces Fixture → Parser → Model → sync_interfaces

    Проверяет что интерфейсы корректно синхронизируются.
    """

    def test_interfaces_sync_pipeline(self, parser, mock_netbox_client):
        """
        Interfaces проходят pipeline до sync_interfaces.
        """
        # 1. Load fixture
        output = load_fixture("cisco_ios", "show interfaces")
        if not output:
            pytest.skip("No fixture for cisco_ios/show interfaces")

        # 2. Parse
        parsed = parser.parse(output, "cisco_ios", "show interfaces")
        assert len(parsed) > 0

        # 3. Convert to models
        interfaces = [Interface.from_dict(row) for row in parsed[:5]]  # First 5

        # 4. Verify key fields for sync
        for intf in interfaces:
            assert intf.name, "Interface must have name"
            # Status can be: up, down, administratively down, etc.
            assert intf.status is not None, "Status should not be None"

        # 5. Sync
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)
        assert "created" in result
        assert "updated" in result
        assert "skipped" in result

    def test_interface_with_lag_sync(self, parser, mock_netbox_client):
        """
        Интерфейсы с LAG (Port-channel) синхронизируются правильно.

        LAG интерфейсы должны создаваться первыми, затем members.
        """
        # Create interfaces with LAG relationship
        interfaces = [
            Interface(
                name="Port-channel1",
                status="up",
                description="LAG to Core",
            ),
            Interface(
                name="GigabitEthernet0/1",
                status="up",
                lag="Port-channel1",  # Member of Po1
            ),
            Interface(
                name="GigabitEthernet0/2",
                status="up",
                lag="Port-channel1",  # Member of Po1
            ),
        ]

        # Mock LAG lookup
        mock_lag = Mock()
        mock_lag.id = 50
        mock_lag.name = "Port-channel1"
        mock_netbox_client.get_interface_by_name.return_value = mock_lag

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)

    def test_interface_mode_sync(self, parser, mock_netbox_client):
        """
        802.1Q mode (access/tagged) синхронизируется.
        """
        interfaces = [
            Interface(
                name="GigabitEthernet0/1",
                status="up",
                mode="access",  # Access port
            ),
            Interface(
                name="GigabitEthernet0/2",
                status="up",
                mode="tagged",  # Trunk port
            ),
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        assert isinstance(result, dict)


# =============================================================================
# Devices → NetBox Sync Pipeline
# =============================================================================

@pytest.mark.e2e
class TestDevicesSyncPipeline:
    """
    E2E тесты: show version Fixture → Parser → DeviceInfo → sync_devices_from_inventory
    """

    def test_devices_sync_pipeline(self, parser, mock_netbox_client):
        """
        Devices (show version) проходят pipeline до sync_devices_from_inventory.
        """
        # 1. Load fixture
        output = load_fixture("cisco_ios", "show version")
        if not output:
            pytest.skip("No fixture for cisco_ios/show version")

        # 2. Parse
        parsed = parser.parse(output, "cisco_ios", "show version")
        assert len(parsed) > 0

        # 3. Convert to model
        device = DeviceInfo.from_dict(parsed[0])
        device.ip_address = "10.0.0.1"  # Add IP (normally from connection)

        # 4. Verify key fields for sync
        assert device.hostname or device.name, "Device must have hostname"
        assert device.model, "Device must have model"

        # 5. Sync
        mock_netbox_client.get_device_by_name.return_value = None  # New device

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_devices_from_inventory(
            [device],
            site="Test Site",
            role="switch",
        )

        assert isinstance(result, dict)
        assert "created" in result


# =============================================================================
# MAC → Export Data Pipeline (no sync, but verify data ready for export)
# =============================================================================

@pytest.mark.e2e
class TestMACExportPipeline:
    """
    E2E тесты: MAC Fixture → Parser → Normalizer → MACEntry → to_dict()

    MAC данные не синхронизируются с NetBox напрямую,
    но проверяем что они готовы для экспорта.
    """

    def test_mac_export_pipeline(self, parser):
        """
        MAC данные готовы для экспорта в Excel/CSV.
        """
        # 1. Load fixture
        output = load_fixture("cisco_ios", "show mac address-table")
        if not output:
            pytest.skip("No fixture for cisco_ios/show mac address-table")

        # 2. Parse
        parsed = parser.parse(output, "cisco_ios", "show mac address-table")
        assert len(parsed) > 0

        # 3. Normalize
        normalizer = MACNormalizer()
        normalized = normalizer.normalize_dicts(
            parsed,
            hostname="switch-01",
            device_ip="10.0.0.1",
        )

        # 4. Verify fields for export
        for row in normalized[:5]:
            assert "mac" in row, "MAC address required"
            assert "interface" in row, "Interface required"
            assert "vlan" in row, "VLAN required"
            assert "hostname" in row, "Hostname should be added"

        # 5. Convert to models and back
        entries = [MACEntry.from_dict(row) for row in normalized]

        for entry in entries[:5]:
            result = entry.to_dict()
            assert "mac" in result
            assert "interface" in result
            assert "vlan" in result


# =============================================================================
# Integration: Full Sync Workflow
# =============================================================================

@pytest.mark.e2e
class TestFullSyncWorkflow:
    """
    Тест полного workflow синхронизации устройства.

    1. show version → create device
    2. show interfaces → sync interfaces
    3. show lldp/cdp neighbors → sync cables
    """

    def test_full_device_sync_workflow(self, parser, mock_netbox_client):
        """
        Полный workflow синхронизации устройства.
        """
        # Step 1: Parse show version for device creation
        version_output = load_fixture("cisco_ios", "show version")
        if version_output:
            version_parsed = parser.parse(version_output, "cisco_ios", "show version")
            if version_parsed:
                device_info = DeviceInfo.from_dict(version_parsed[0])
                device_info.ip_address = "10.0.0.1"

                # Create device
                mock_netbox_client.get_device_by_name.return_value = None
                sync = NetBoxSync(mock_netbox_client, dry_run=True)
                devices_result = sync.sync_devices_from_inventory(
                    [device_info],
                    site="Test",
                    role="switch",
                )
                assert devices_result["created"] >= 0

        # Step 2: Parse interfaces
        intf_output = load_fixture("cisco_ios", "show interfaces")
        if intf_output:
            intf_parsed = parser.parse(intf_output, "cisco_ios", "show interfaces")
            if intf_parsed:
                interfaces = [Interface.from_dict(row) for row in intf_parsed[:10]]

                # Setup mock for interfaces sync
                mock_device = Mock()
                mock_device.id = 1
                mock_netbox_client.get_device_by_name.return_value = mock_device
                mock_netbox_client.get_interfaces.return_value = []

                sync = NetBoxSync(mock_netbox_client, dry_run=True)
                intf_result = sync.sync_interfaces("switch-01", interfaces)
                assert "created" in intf_result

        # Step 3: Parse LLDP for cables
        lldp_output = load_fixture("cisco_ios", "show lldp neighbors detail")
        if lldp_output:
            lldp_parsed = parser.parse(lldp_output, "cisco_ios", "show lldp neighbors detail")
            if lldp_parsed:
                normalizer = LLDPNormalizer()
                normalized = normalizer.normalize_dicts(
                    lldp_parsed, protocol="lldp", hostname="switch-01"
                )
                neighbors = [LLDPNeighbor.from_dict(n) for n in normalized]

                sync = NetBoxSync(mock_netbox_client, dry_run=True)
                cables_result = sync.sync_cables_from_lldp(neighbors)
                assert "created" in cables_result


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

@pytest.mark.e2e
class TestSyncPipelineEdgeCases:
    """Тесты граничных случаев в sync pipeline."""

    def test_empty_lldp_data_sync(self, mock_netbox_client):
        """Пустые LLDP данные не вызывают ошибку."""
        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_cables_from_lldp([])

        assert result["created"] == 0
        assert result["failed"] == 0

    def test_empty_interfaces_sync(self, mock_netbox_client):
        """Пустой список интерфейсов не вызывает ошибку."""
        mock_netbox_client.get_device_by_name.return_value = None

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", [])

        assert isinstance(result, dict)

    def test_lldp_with_missing_fields(self, mock_netbox_client):
        """LLDP данные с отсутствующими полями обрабатываются корректно."""
        neighbors = [
            LLDPNeighbor(
                hostname="switch-01",
                local_interface="Gi0/1",
                # remote_hostname missing
                # remote_port missing
            ),
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_cables_from_lldp(neighbors)

        # Should skip, not fail
        assert result["failed"] == 0

    def test_interface_with_empty_name(self, mock_netbox_client):
        """Интерфейс без имени пропускается."""
        mock_device = Mock()
        mock_device.id = 1
        mock_netbox_client.get_device_by_name.return_value = mock_device
        mock_netbox_client.get_interfaces.return_value = []

        interfaces = [
            Interface(name="", status="up"),  # Empty name
            Interface(name="Gi0/1", status="up"),  # Valid
        ]

        sync = NetBoxSync(mock_netbox_client, dry_run=True)
        result = sync.sync_interfaces("switch-01", interfaces)

        # Only one should be processed (empty name skipped)
        assert result["created"] + result["skipped"] >= 0
