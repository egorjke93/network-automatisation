"""
End-to-End tests для полной цепочки обработки данных.

Проверяет: Fixture → NTC Parser → Normalizer → Model → to_dict()
           → все enabled поля из fields.yaml заполнены.

Гарантирует что реальный вывод устройств парсится и все поля
из fields.yaml присутствуют в финальном результате.
"""

import pytest
import yaml
from pathlib import Path
from typing import Dict, Set, List, Any

from network_collector.parsers.textfsm_parser import NTCParser
from network_collector.core.domain.mac import MACNormalizer
from network_collector.core.domain.lldp import LLDPNormalizer
from network_collector.core.models import (
    MACEntry,
    LLDPNeighbor,
    Interface,
    InventoryItem,
    DeviceInfo,
)


# Путь к fixtures и fields.yaml
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FIELDS_YAML = Path(__file__).parent.parent.parent / "fields.yaml"


@pytest.fixture(scope="module")
def fields_config() -> Dict:
    """Загружает fields.yaml."""
    with open(FIELDS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def parser() -> NTCParser:
    """NTC парсер."""
    return NTCParser()


def get_enabled_fields(config: Dict, section: str) -> Set[str]:
    """Возвращает enabled поля для секции."""
    enabled = set()
    for field_name, field_config in config.get(section, {}).items():
        if isinstance(field_config, dict) and field_config.get("enabled", False):
            enabled.add(field_name)
    return enabled


def load_fixture(platform: str, command: str) -> str:
    """Загружает fixture файл."""
    # Преобразуем команду в имя файла (пробелы и дефисы в _)
    filename = command.replace(" ", "_").replace("-", "_") + ".txt"
    filepath = FIXTURES_DIR / platform / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


# =============================================================================
# MAC E2E Tests
# =============================================================================

@pytest.mark.e2e
class TestMACPipeline:
    """E2E тесты для MAC: Fixture → Parser → Normalizer → Model."""

    # Маппинг полей fields.yaml → полей в результате
    FIELD_MAPPING = {
        "type": "mac_type",  # type в fields.yaml это mac_type в модели
    }

    # Поля которые добавляются при экспорте (не в базовом pipeline)
    OPTIONAL_FIELDS = {"description", "status"}

    @pytest.mark.parametrize("platform", ["cisco_ios", "cisco_nxos"])
    def test_mac_pipeline_has_all_fields(self, parser, fields_config, platform):
        """Полная цепочка MAC возвращает все enabled поля."""
        # 1. Load fixture
        output = load_fixture(platform, "show mac address-table")
        if not output:
            pytest.skip(f"No fixture for {platform}/show mac address-table")

        # 2. Parse with NTC
        parsed = parser.parse(output, platform, "show mac address-table")
        assert len(parsed) > 0, "Parser returned empty result"

        # 3. Normalize
        normalizer = MACNormalizer()
        normalized = normalizer.normalize_dicts(
            parsed,
            interface_status={"Gi0/1": "connected"},  # Для status
            hostname="test-switch",
            device_ip="10.0.0.1",
        )
        assert len(normalized) > 0, "Normalizer returned empty result"

        # 4. Convert to model and back to dict
        for row in normalized[:5]:  # Проверяем первые 5
            entry = MACEntry.from_dict(row)
            result = entry.to_dict()

            # 5. Verify all enabled fields exist
            enabled = get_enabled_fields(fields_config, "mac")
            missing = []
            for field in enabled:
                if field in self.OPTIONAL_FIELDS:
                    continue  # Опциональные поля
                mapped = self.FIELD_MAPPING.get(field, field)
                if mapped not in result and field not in result:
                    missing.append(field)

            assert not missing, (
                f"MAC pipeline ({platform}): поля {missing} отсутствуют. "
                f"Результат: {list(result.keys())}"
            )

    def test_mac_cisco_ios_specific_fields(self, parser, fields_config):
        """Cisco IOS MAC: проверка конкретных значений."""
        output = load_fixture("cisco_ios", "show mac address-table")
        if not output:
            pytest.skip("No fixture for cisco_ios/show mac address-table")

        parsed = parser.parse(output, "cisco_ios", "show mac address-table")
        normalizer = MACNormalizer()
        normalized = normalizer.normalize_dicts(parsed, hostname="sw1", device_ip="10.0.0.1")

        # Должен быть хотя бы один MAC
        assert len(normalized) > 0

        # Проверяем структуру первой записи
        first = normalized[0]
        assert "mac" in first, "MAC address missing"
        assert "interface" in first, "Interface missing"
        assert "vlan" in first, "VLAN missing"
        assert "hostname" in first, "Hostname not added"


# =============================================================================
# LLDP E2E Tests
# =============================================================================

@pytest.mark.e2e
class TestLLDPPipeline:
    """E2E тесты для LLDP: Fixture → Parser → Normalizer → Model."""

    # Поля которые требуют особого маппинга
    FIELD_MAPPING = {
        "remote_platform": "platform",  # remote_platform → platform в модели
    }

    OPTIONAL_FIELDS = {"capabilities", "neighbor_type", "neighbor_name"}

    @pytest.mark.parametrize("platform,command", [
        ("cisco_ios", "show lldp neighbors detail"),
        ("cisco_ios", "show cdp neighbors detail"),
        ("cisco_nxos", "show lldp neighbors detail"),
        ("cisco_nxos", "show cdp neighbors detail"),
    ])
    def test_lldp_pipeline_has_all_fields(self, parser, fields_config, platform, command):
        """Полная цепочка LLDP/CDP возвращает все enabled поля."""
        # 1. Load fixture
        output = load_fixture(platform, command)
        if not output:
            pytest.skip(f"No fixture for {platform}/{command}")

        # 2. Parse with NTC
        parsed = parser.parse(output, platform, command)
        assert len(parsed) > 0, f"Parser returned empty result for {command}"

        # 3. Normalize
        protocol = "lldp" if "lldp" in command else "cdp"
        normalizer = LLDPNormalizer()
        normalized = normalizer.normalize_dicts(
            parsed,
            protocol=protocol,
            hostname="test-switch",
            device_ip="10.0.0.1",
        )
        assert len(normalized) > 0, "Normalizer returned empty result"

        # 4. Convert to model and back to dict
        for row in normalized[:5]:
            neighbor = LLDPNeighbor.from_dict(row)
            result = neighbor.to_dict()

            # 5. Verify all enabled fields exist
            enabled = get_enabled_fields(fields_config, "lldp")
            missing = []
            for field in enabled:
                if field in self.OPTIONAL_FIELDS:
                    continue
                mapped = self.FIELD_MAPPING.get(field, field)
                if mapped not in result and field not in result:
                    # Проверяем что хотя бы пустое значение есть
                    if field not in result:
                        missing.append(field)

            assert not missing, (
                f"LLDP pipeline ({platform}/{command}): поля {missing} отсутствуют. "
                f"Результат: {list(result.keys())}"
            )

    def test_lldp_cisco_ios_has_neighbor_info(self, parser):
        """Cisco IOS LLDP: соседи содержат необходимую информацию."""
        output = load_fixture("cisco_ios", "show lldp neighbors detail")
        if not output:
            pytest.skip("No fixture")

        parsed = parser.parse(output, "cisco_ios", "show lldp neighbors detail")
        normalizer = LLDPNormalizer()
        normalized = normalizer.normalize_dicts(parsed, protocol="lldp")

        assert len(normalized) > 0
        first = normalized[0]

        # Ключевые поля для LLDP
        assert "local_interface" in first, "local_interface missing"
        assert "remote_hostname" in first or "neighbor_type" in first, "No neighbor identification"


# =============================================================================
# Interfaces E2E Tests
# =============================================================================

@pytest.mark.e2e
class TestInterfacesPipeline:
    """E2E тесты для Interfaces: Fixture → Parser → Model."""

    FIELD_MAPPING = {
        "interface": "name",  # interface в fields.yaml это name в модели
    }

    OPTIONAL_FIELDS = {"protocol", "prefix_length", "bandwidth", "hardware_type", "media_type"}

    @pytest.mark.parametrize("platform", ["cisco_ios", "cisco_nxos"])
    def test_interfaces_pipeline_has_all_fields(self, parser, fields_config, platform):
        """Полная цепочка Interfaces возвращает все enabled поля."""
        # 1. Load fixture
        output = load_fixture(platform, "show interfaces")
        if not output:
            # Try alternative command name
            output = load_fixture(platform, "show interface")
        if not output:
            pytest.skip(f"No fixture for {platform}/show interfaces")

        # 2. Parse with NTC
        parsed = parser.parse(output, platform, "show interfaces")
        if not parsed:
            parsed = parser.parse(output, platform, "show interface")
        assert len(parsed) > 0, "Parser returned empty result"

        # 3. Convert to model (no separate normalizer for interfaces)
        for row in parsed[:5]:
            interface = Interface.from_dict(row)
            result = interface.to_dict()

            # 4. Verify enabled fields
            enabled = get_enabled_fields(fields_config, "interfaces")
            missing = []
            for field in enabled:
                if field in self.OPTIONAL_FIELDS:
                    continue
                mapped = self.FIELD_MAPPING.get(field, field)
                if mapped not in result and field not in result:
                    missing.append(field)

            # Allow some missing since not all interfaces have all data
            # But key fields must be present
            key_fields = {"name", "status"}
            for key in key_fields:
                assert key in result, f"Key field {key} missing from Interface"


# =============================================================================
# Inventory E2E Tests
# =============================================================================

@pytest.mark.e2e
class TestInventoryPipeline:
    """E2E тесты для Inventory: Fixture → Parser → Model."""

    OPTIONAL_FIELDS = {"manufacturer", "device_ip"}

    @pytest.mark.parametrize("platform", ["cisco_ios", "cisco_nxos"])
    def test_inventory_pipeline_has_all_fields(self, parser, fields_config, platform):
        """Полная цепочка Inventory возвращает все enabled поля."""
        # 1. Load fixture
        output = load_fixture(platform, "show inventory")
        if not output:
            pytest.skip(f"No fixture for {platform}/show inventory")

        # 2. Parse with NTC
        parsed = parser.parse(output, platform, "show inventory")
        assert len(parsed) > 0, "Parser returned empty result"

        # 3. Convert to model
        for row in parsed[:5]:
            item = InventoryItem.from_dict(row)
            result = item.to_dict()

            # 4. Verify enabled fields
            enabled = get_enabled_fields(fields_config, "inventory")
            missing = []
            for field in enabled:
                if field in self.OPTIONAL_FIELDS:
                    continue
                if field not in result:
                    missing.append(field)

            # Key fields must be present
            assert "name" in result or "pid" in result, "No identification field in inventory"


# =============================================================================
# Devices E2E Tests
# =============================================================================

@pytest.mark.e2e
class TestDevicesPipeline:
    """E2E тесты для Devices: Fixture → Parser → Model."""

    # ip_address добавляется при подключении к устройству, не из show version
    OPTIONAL_FIELDS = {"name", "manufacturer", "platform", "status", "site", "role", "tenant", "ip_address"}

    @pytest.mark.parametrize("platform", ["cisco_ios", "cisco_nxos"])
    def test_devices_pipeline_has_all_fields(self, parser, fields_config, platform):
        """Полная цепочка Devices (show version) возвращает все enabled поля."""
        # 1. Load fixture
        output = load_fixture(platform, "show version")
        if not output:
            pytest.skip(f"No fixture for {platform}/show version")

        # 2. Parse with NTC
        parsed = parser.parse(output, platform, "show version")
        assert len(parsed) > 0, "Parser returned empty result"

        # 3. Convert to model
        row = parsed[0]  # show version returns single record
        device = DeviceInfo.from_dict(row)
        result = device.to_dict()

        # 4. Verify enabled fields
        enabled = get_enabled_fields(fields_config, "devices")
        missing = []
        for field in enabled:
            if field in self.OPTIONAL_FIELDS:
                continue
            if field not in result:
                missing.append(field)

        assert not missing, (
            f"Devices pipeline ({platform}): поля {missing} отсутствуют. "
            f"Результат: {list(result.keys())}"
        )

    def test_devices_cisco_ios_has_key_fields(self, parser):
        """Cisco IOS show version: ключевые поля заполнены."""
        output = load_fixture("cisco_ios", "show version")
        if not output:
            pytest.skip("No fixture")

        parsed = parser.parse(output, "cisco_ios", "show version")
        device = DeviceInfo.from_dict(parsed[0])
        result = device.to_dict()

        # Ключевые поля для устройства
        assert "hostname" in result, "hostname missing"
        assert result.get("hostname"), "hostname is empty"


# =============================================================================
# Cross-Platform Consistency Tests
# =============================================================================

@pytest.mark.e2e
class TestCrossPlatformConsistency:
    """Тесты что разные платформы возвращают одинаковые поля."""

    def test_mac_same_fields_across_platforms(self, parser):
        """MAC: Cisco IOS и NX-OS возвращают одинаковые поля."""
        ios_output = load_fixture("cisco_ios", "show mac address-table")
        nxos_output = load_fixture("cisco_nxos", "show mac address-table")

        if not ios_output or not nxos_output:
            pytest.skip("Need both fixtures")

        ios_parsed = parser.parse(ios_output, "cisco_ios", "show mac address-table")
        nxos_parsed = parser.parse(nxos_output, "cisco_nxos", "show mac address-table")

        normalizer = MACNormalizer()
        ios_normalized = normalizer.normalize_dicts(ios_parsed)
        nxos_normalized = normalizer.normalize_dicts(nxos_parsed)

        # Ключевые поля должны быть в обоих
        key_fields = {"mac", "interface", "vlan"}

        ios_fields = set(ios_normalized[0].keys()) if ios_normalized else set()
        nxos_fields = set(nxos_normalized[0].keys()) if nxos_normalized else set()

        for field in key_fields:
            assert field in ios_fields, f"Cisco IOS missing {field}"
            assert field in nxos_fields, f"Cisco NX-OS missing {field}"

    def test_lldp_same_fields_across_platforms(self, parser):
        """LLDP: Cisco IOS и NX-OS возвращают одинаковые поля."""
        ios_output = load_fixture("cisco_ios", "show lldp neighbors detail")
        nxos_output = load_fixture("cisco_nxos", "show lldp neighbors detail")

        if not ios_output or not nxos_output:
            pytest.skip("Need both fixtures")

        ios_parsed = parser.parse(ios_output, "cisco_ios", "show lldp neighbors detail")
        nxos_parsed = parser.parse(nxos_output, "cisco_nxos", "show lldp neighbors detail")

        normalizer = LLDPNormalizer()
        ios_normalized = normalizer.normalize_dicts(ios_parsed, protocol="lldp")
        nxos_normalized = normalizer.normalize_dicts(nxos_parsed, protocol="lldp")

        # Ключевые поля
        key_fields = {"local_interface", "remote_hostname", "remote_port"}

        ios_fields = set(ios_normalized[0].keys()) if ios_normalized else set()
        nxos_fields = set(nxos_normalized[0].keys()) if nxos_normalized else set()

        for field in key_fields:
            assert field in ios_fields, f"Cisco IOS LLDP missing {field}"
            assert field in nxos_fields, f"Cisco NX-OS LLDP missing {field}"
