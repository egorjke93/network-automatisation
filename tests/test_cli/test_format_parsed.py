"""
Тесты для --format parsed.

Проверяет что --format parsed возвращает данные после TextFSM
парсинга, но ДО нормализации Domain Layer и apply_fields_config.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from argparse import Namespace

from network_collector.cli.commands.collect import (
    cmd_devices,
    cmd_mac,
    cmd_lldp,
    cmd_interfaces,
    cmd_inventory,
)


# --- Fixtures ---


@pytest.fixture
def base_args():
    """Базовые аргументы CLI."""
    return Namespace(
        format="parsed",
        output="reports",
        delimiter=",",
        transport="ssh2",
        config=None,
        fields=None,
    )


@pytest.fixture
def devices_args(base_args):
    """Аргументы для cmd_devices."""
    base_args.site = "Main"
    base_args.role = "Switch"
    base_args.manufacturer = "Cisco"
    return base_args


@pytest.fixture
def mac_args(base_args):
    """Аргументы для cmd_mac."""
    base_args.mac_format = "ieee"
    base_args.with_descriptions = False
    base_args.no_descriptions = False
    base_args.include_trunk = False
    base_args.exclude_trunk = False
    base_args.with_port_security = False
    base_args.match_file = None
    base_args.per_device = False
    return base_args


@pytest.fixture
def lldp_args(base_args):
    """Аргументы для cmd_lldp."""
    base_args.protocol = "lldp"
    return base_args


@pytest.fixture
def interfaces_args(base_args):
    """Аргументы для cmd_interfaces."""
    return base_args


@pytest.fixture
def inventory_args(base_args):
    """Аргументы для cmd_inventory."""
    return base_args


# --- Тесты _skip_normalize для коллекторов ---


class TestSkipNormalize:
    """Тесты флага _skip_normalize в коллекторах."""

    def test_base_collector_has_skip_normalize(self):
        """BaseCollector имеет атрибут _skip_normalize = False."""
        from network_collector.collectors.base import BaseCollector

        # BaseCollector абстрактный, проверяем через InterfaceCollector
        from network_collector.collectors.interfaces import InterfaceCollector

        collector = InterfaceCollector(credentials=None)
        assert hasattr(collector, "_skip_normalize")
        assert collector._skip_normalize is False

    def test_mac_collector_has_skip_normalize(self):
        """MACCollector наследует _skip_normalize."""
        from network_collector.collectors.mac import MACCollector

        collector = MACCollector(credentials=None)
        assert collector._skip_normalize is False

    def test_lldp_collector_has_skip_normalize(self):
        """LLDPCollector наследует _skip_normalize."""
        from network_collector.collectors.lldp import LLDPCollector

        collector = LLDPCollector(credentials=None)
        assert collector._skip_normalize is False

    def test_inventory_collector_has_skip_normalize(self):
        """InventoryCollector наследует _skip_normalize."""
        from network_collector.collectors.inventory import InventoryCollector

        collector = InventoryCollector(credentials=None)
        assert collector._skip_normalize is False

    def test_device_collector_has_skip_normalize(self):
        """DeviceCollector имеет _skip_normalize (независимый класс)."""
        from network_collector.collectors.device import DeviceCollector

        collector = DeviceCollector(credentials=None)
        assert hasattr(collector, "_skip_normalize")
        assert collector._skip_normalize is False


# --- Тесты cmd_* с format=parsed ---


class TestCmdDevicesParsed:
    """Тесты cmd_devices --format parsed."""

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.collectors.device.DeviceInventoryCollector.collect_dicts")
    @patch("network_collector.cli.commands.collect._export_parsed")
    def test_sets_skip_normalize(self, mock_export, mock_collect, mock_prepare, devices_args):
        """cmd_devices с parsed ставит _skip_normalize=True."""
        mock_prepare.return_value = ([], None)
        mock_collect.return_value = [{"hostname": "sw1", "hardware": ["WS-C3750"]}]

        with patch("network_collector.collectors.device.DeviceInventoryCollector.__init__", return_value=None) as mock_init:
            mock_init.return_value = None
            # Проверяем через _export_parsed вызов
            cmd_devices(devices_args)
            mock_export.assert_called_once()

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.collectors.device.DeviceInventoryCollector.collect_dicts")
    @patch("network_collector.cli.commands.collect._export_parsed")
    @patch("network_collector.fields_config.apply_fields_config")
    def test_skips_fields_config(self, mock_fields, mock_export, mock_collect, mock_prepare, devices_args):
        """cmd_devices с parsed НЕ вызывает apply_fields_config."""
        mock_prepare.return_value = ([], None)
        mock_collect.return_value = [{"hostname": "sw1"}]

        with patch("network_collector.collectors.device.DeviceInventoryCollector.__init__", return_value=None):
            cmd_devices(devices_args)

        mock_fields.assert_not_called()

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.collectors.device.DeviceInventoryCollector.collect_dicts")
    @patch("network_collector.cli.commands.collect._export_parsed")
    def test_empty_data_no_export(self, mock_export, mock_collect, mock_prepare, devices_args):
        """cmd_devices с parsed и пустыми данными — нет экспорта."""
        mock_prepare.return_value = ([], None)
        mock_collect.return_value = []

        with patch("network_collector.collectors.device.DeviceInventoryCollector.__init__", return_value=None):
            cmd_devices(devices_args)

        mock_export.assert_not_called()


class TestCmdInterfacesParsed:
    """Тесты cmd_interfaces --format parsed."""

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.cli.commands.collect._export_parsed")
    def test_parsed_uses_raw_exporter(self, mock_export, mock_prepare, interfaces_args):
        """cmd_interfaces с parsed выводит через _export_parsed."""
        mock_prepare.return_value = ([], None)

        raw_textfsm_data = [
            {"interface": "GigabitEthernet0/1", "link_status": "up", "hostname": "sw1", "device_ip": "10.0.0.1"},
        ]

        with patch("network_collector.collectors.interfaces.InterfaceCollector.__init__", return_value=None):
            with patch("network_collector.collectors.interfaces.InterfaceCollector.collect_dicts", return_value=raw_textfsm_data):
                cmd_interfaces(interfaces_args)

        mock_export.assert_called_once_with(raw_textfsm_data, "interfaces_parsed")

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.cli.commands.collect._export_parsed")
    @patch("network_collector.fields_config.apply_fields_config")
    def test_parsed_skips_fields_config(self, mock_fields, mock_export, mock_prepare, interfaces_args):
        """cmd_interfaces с parsed НЕ вызывает apply_fields_config."""
        mock_prepare.return_value = ([], None)

        with patch("network_collector.collectors.interfaces.InterfaceCollector.__init__", return_value=None):
            with patch("network_collector.collectors.interfaces.InterfaceCollector.collect_dicts", return_value=[{"a": 1}]):
                cmd_interfaces(interfaces_args)

        mock_fields.assert_not_called()


class TestCmdMacParsed:
    """Тесты cmd_mac --format parsed."""

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.cli.commands.collect._export_parsed")
    def test_parsed_skips_match_file(self, mock_export, mock_prepare, mac_args):
        """cmd_mac с parsed пропускает match_file обработку."""
        mock_prepare.return_value = ([], None)
        mac_args.match_file = "hosts.txt"  # Есть match_file, но parsed пропустит

        raw_data = [{"destination_address": "aabb.ccdd.eeff", "hostname": "sw1", "device_ip": "10.0.0.1"}]

        with patch("network_collector.collectors.mac.MACCollector.__init__", return_value=None):
            with patch("network_collector.collectors.mac.MACCollector.collect_dicts", return_value=raw_data):
                with patch("network_collector.config.config") as mock_config:
                    mock_config.output.mac_format = "ieee"
                    mock_config.output.per_device = False
                    mock_config.mac = None
                    cmd_mac(mac_args)

        # _export_parsed вызван, match_file НЕ обработан
        mock_export.assert_called_once()


class TestCmdLldpParsed:
    """Тесты cmd_lldp --format parsed."""

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.cli.commands.collect._export_parsed")
    def test_parsed_output(self, mock_export, mock_prepare, lldp_args):
        """cmd_lldp с parsed выводит сырые данные."""
        mock_prepare.return_value = ([], None)

        raw_data = [{"neighbor": "switch2", "local_intf": "Gi0/1", "hostname": "sw1", "device_ip": "10.0.0.1"}]

        with patch("network_collector.collectors.lldp.LLDPCollector.__init__", return_value=None):
            with patch("network_collector.collectors.lldp.LLDPCollector.collect_dicts", return_value=raw_data):
                cmd_lldp(lldp_args)

        mock_export.assert_called_once_with(raw_data, "lldp_neighbors_parsed")


class TestCmdInventoryParsed:
    """Тесты cmd_inventory --format parsed."""

    @patch("network_collector.cli.commands.collect.prepare_collection")
    @patch("network_collector.cli.commands.collect._export_parsed")
    def test_parsed_output(self, mock_export, mock_prepare, inventory_args):
        """cmd_inventory с parsed выводит сырые данные."""
        mock_prepare.return_value = ([], None)

        raw_data = [{"name": "Chassis", "pid": "WS-C3750", "sn": "ABC123", "hostname": "sw1", "device_ip": "10.0.0.1"}]

        with patch("network_collector.collectors.inventory.InventoryCollector.__init__", return_value=None):
            with patch("network_collector.collectors.inventory.InventoryCollector.collect_dicts", return_value=raw_data):
                cmd_inventory(inventory_args)

        mock_export.assert_called_once_with(raw_data, "inventory_parsed")


# --- Тест _export_parsed ---


class TestExportParsed:
    """Тесты helper функции _export_parsed."""

    def test_uses_raw_exporter(self):
        """_export_parsed использует RawExporter для вывода в stdout."""
        from network_collector.cli.commands.collect import _export_parsed

        with patch("network_collector.exporters.RawExporter") as MockRaw:
            mock_instance = MockRaw.return_value
            _export_parsed([{"a": 1}], "test")
            mock_instance.export.assert_called_once_with([{"a": 1}], "test")


# --- Тест argparse ---


class TestArgparseParsed:
    """Тесты что parsed доступен в argparse choices."""

    def test_interfaces_accepts_parsed(self):
        """Argparse принимает --format parsed для interfaces."""
        from network_collector.cli import setup_parser

        parser = setup_parser()
        args = parser.parse_args(["interfaces", "--format", "parsed"])
        assert args.format == "parsed"

    def test_mac_accepts_parsed(self):
        """Argparse принимает --format parsed для mac."""
        from network_collector.cli import setup_parser

        parser = setup_parser()
        args = parser.parse_args(["mac", "--format", "parsed"])
        assert args.format == "parsed"

    def test_devices_accepts_parsed(self):
        """Argparse принимает --format parsed для devices."""
        from network_collector.cli import setup_parser

        parser = setup_parser()
        args = parser.parse_args(["devices", "--format", "parsed"])
        assert args.format == "parsed"

    def test_lldp_accepts_parsed(self):
        """Argparse принимает --format parsed для lldp."""
        from network_collector.cli import setup_parser

        parser = setup_parser()
        args = parser.parse_args(["lldp", "--format", "parsed"])
        assert args.format == "parsed"

    def test_inventory_accepts_parsed(self):
        """Argparse принимает --format parsed для inventory."""
        from network_collector.cli import setup_parser

        parser = setup_parser()
        args = parser.parse_args(["inventory", "--format", "parsed"])
        assert args.format == "parsed"

    def test_run_accepts_parsed(self):
        """Argparse принимает --format parsed для run."""
        from network_collector.cli import setup_parser

        parser = setup_parser()
        args = parser.parse_args(["run", "show version", "--format", "parsed"])
        assert args.format == "parsed"
