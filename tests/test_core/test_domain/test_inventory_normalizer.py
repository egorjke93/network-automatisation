"""
Tests for InventoryNormalizer.

Проверяет нормализацию inventory:
- Унификация полей (descr → description, sn → serial)
- Определение manufacturer по платформе и PID
- Нормализация трансиверов
"""

import pytest

from network_collector.core.domain import InventoryNormalizer
from network_collector.core.models import InventoryItem


@pytest.mark.unit
class TestInventoryNormalizerBasic:
    """Базовые тесты нормализации inventory."""

    def setup_method(self):
        self.normalizer = InventoryNormalizer()

    def test_normalize_basic(self):
        """Базовая нормализация inventory."""
        raw_data = [
            {"name": "Chassis", "pid": "C9200L-24P-4X", "sn": "ABC123"},
        ]
        result = self.normalizer.normalize(raw_data)

        assert len(result) == 1
        assert isinstance(result[0], InventoryItem)
        assert result[0].name == "Chassis"
        assert result[0].pid == "C9200L-24P-4X"
        assert result[0].serial == "ABC123"

    def test_normalize_with_metadata(self):
        """Нормализация с hostname и device_ip."""
        raw_data = [{"name": "Chassis", "pid": "C9200L", "sn": "ABC123"}]
        result = self.normalizer.normalize(
            raw_data, hostname="switch-01", device_ip="192.168.1.1"
        )

        assert result[0].hostname == "switch-01"
        assert result[0].device_ip == "192.168.1.1"

    def test_normalize_field_unification(self):
        """Унификация полей из NTC."""
        raw_data = [
            {"name": "Chassis", "descr": "Cisco Switch", "sn": "ABC123", "pid": "C9200L"},
        ]
        result = self.normalizer.normalize_dicts(raw_data)

        # descr → description, sn → serial
        assert result[0]["description"] == "Cisco Switch"
        assert result[0]["serial"] == "ABC123"


@pytest.mark.unit
class TestInventoryNormalizerManufacturer:
    """Тесты определения manufacturer."""

    def setup_method(self):
        self.normalizer = InventoryNormalizer()

    @pytest.mark.parametrize("platform, expected", [
        ("cisco_ios", "Cisco"),
        ("cisco_iosxe", "Cisco"),
        ("cisco_nxos", "Cisco"),
        ("arista_eos", "Arista"),
        ("juniper_junos", "Juniper"),
        ("qtech", "Qtech"),
        ("unknown_platform", ""),
        ("", ""),
    ])
    def test_detect_manufacturer_by_platform(self, platform, expected):
        """Тест определения manufacturer по платформе."""
        result = self.normalizer.detect_manufacturer_by_platform(platform)
        assert result == expected

    @pytest.mark.parametrize("pid, expected", [
        ("WS-C3750X-48P-S", "Cisco"),
        ("C9200L-24P-4X", "Cisco"),
        ("N9K-C93180YC-EX", "Cisco"),
        ("SFP-10G-LR", "Cisco"),
        ("GLC-SX-MMD", "Cisco"),
        ("DCS-7050TX-48-F", "Arista"),
        ("EX4300-48T", "Juniper"),
        ("QFX5100-48S", "Juniper"),
        ("MX204", "Juniper"),
        ("FINISAR-FTLX1471", "Finisar"),
        ("UNKNOWN-123", ""),
        ("", ""),
    ])
    def test_detect_manufacturer_by_pid(self, pid, expected):
        """Тест определения manufacturer по PID."""
        result = self.normalizer.detect_manufacturer_by_pid(pid)
        assert result == expected

    def test_manufacturer_from_platform(self):
        """Manufacturer берётся из платформы если PID не распознан."""
        raw_data = [{"name": "Module", "pid": "UNKNOWN-123", "sn": "ABC"}]
        result = self.normalizer.normalize_dicts(raw_data, platform="arista_eos")

        assert result[0]["manufacturer"] == "Arista"

    def test_manufacturer_from_pid_priority(self):
        """PID имеет приоритет над платформой."""
        raw_data = [{"name": "SFP", "pid": "GLC-SX-MMD", "sn": "ABC"}]
        # Даже если платформа Arista, Cisco PID даёт Cisco
        result = self.normalizer.normalize_dicts(raw_data, platform="arista_eos")

        assert result[0]["manufacturer"] == "Cisco"


@pytest.mark.unit
class TestInventoryNormalizerTransceivers:
    """Тесты нормализации трансиверов."""

    def setup_method(self):
        self.normalizer = InventoryNormalizer()

    def test_normalize_transceivers(self):
        """Конвертация трансиверов в формат inventory."""
        raw_data = [
            {
                "interface": "Ethernet1/1",
                "type": "10Gbase-LR",
                "part_number": "SFP-10G-LR",
                "serial": "ABC123",
                "name": "CISCO-FINISAR",
            },
        ]
        result = self.normalizer.normalize_transceivers(raw_data, platform="cisco_nxos")

        assert len(result) == 1
        assert result[0]["name"] == "Transceiver Ethernet1/1"
        assert result[0]["description"] == "10Gbase-LR"
        assert result[0]["pid"] == "SFP-10G-LR"
        assert result[0]["serial"] == "ABC123"
        assert result[0]["manufacturer"] == "Cisco"

    def test_skip_not_present_transceivers(self):
        """Пропуск интерфейсов без трансиверов."""
        raw_data = [
            {"interface": "Ethernet1/1", "type": "10Gbase-LR", "part_number": "SFP-10G-LR"},
            {"interface": "Ethernet1/2", "type": "not present", "part_number": ""},
            {"interface": "Ethernet1/3", "type": "", "part_number": ""},
        ]
        result = self.normalizer.normalize_transceivers(raw_data)

        assert len(result) == 1
        assert result[0]["name"] == "Transceiver Ethernet1/1"

    def test_transceiver_manufacturer_oem(self):
        """OEM трансиверы получают manufacturer устройства."""
        raw_data = [
            {"interface": "Eth1/1", "type": "10G", "part_number": "OEM-123", "name": "OEM"},
        ]
        result = self.normalizer.normalize_transceivers(raw_data, platform="cisco_nxos")

        assert result[0]["manufacturer"] == "Cisco"

    def test_transceiver_manufacturer_finisar(self):
        """Finisar трансиверы."""
        raw_data = [
            {"interface": "Eth1/1", "type": "10G", "part_number": "FTLX1471", "name": "FINISAR"},
        ]
        result = self.normalizer.normalize_transceivers(raw_data)

        assert result[0]["manufacturer"] == "Finisar"


@pytest.mark.unit
class TestInventoryNormalizerMerge:
    """Тесты объединения и фильтрации."""

    def setup_method(self):
        self.normalizer = InventoryNormalizer()

    def test_merge_with_transceivers(self):
        """Объединение inventory с трансиверами."""
        inventory = [{"name": "Chassis", "pid": "C9200L"}]
        transceivers = [{"name": "Transceiver Eth1/1", "pid": "SFP-10G-LR"}]

        result = self.normalizer.merge_with_transceivers(inventory, transceivers)

        assert len(result) == 2
        assert result[0]["name"] == "Chassis"
        assert result[1]["name"] == "Transceiver Eth1/1"

    def test_filter_with_serial(self):
        """Фильтрация записей без серийника."""
        data = [
            {"name": "Chassis", "serial": "ABC123"},
            {"name": "Module", "serial": ""},
            {"name": "SFP", "serial": "DEF456"},
        ]
        result = self.normalizer.filter_with_serial(data)

        assert len(result) == 2
        assert result[0]["name"] == "Chassis"
        assert result[1]["name"] == "SFP"
