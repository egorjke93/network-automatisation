"""
Тесты QTech поддержки: Config.get(), interface maps, LAG парсинг, inventory.
"""

import pytest
from unittest.mock import MagicMock

from network_collector.config import Config, ConfigSection
from network_collector.core.constants.interfaces import (
    normalize_interface_short,
    normalize_interface_full,
    get_interface_aliases,
)
from network_collector.collectors.interfaces import InterfaceCollector
from network_collector.core.domain.inventory import InventoryNormalizer


class TestConfigGet:
    """Тесты для Config.get() — исправление cmd_run TypeError."""

    def test_config_has_get_method(self):
        """Config теперь имеет метод .get()."""
        config = Config()
        assert hasattr(config, "get")
        assert callable(config.get)

    def test_config_get_existing_key(self):
        """Config.get() возвращает значение для существующего ключа."""
        config = Config()
        connection = config.get("connection")
        assert connection is not None
        assert isinstance(connection, dict)
        assert "max_retries" in connection

    def test_config_get_missing_key_default(self):
        """Config.get() возвращает дефолт для отсутствующего ключа."""
        config = Config()
        result = config.get("nonexistent_key", "default_value")
        assert result == "default_value"

    def test_config_get_missing_key_none(self):
        """Config.get() возвращает None для отсутствующего ключа без дефолта."""
        config = Config()
        result = config.get("nonexistent_key")
        assert result is None

    def test_config_connection_via_attr(self):
        """config.connection возвращает ConfigSection с .get()."""
        config = Config()
        conn = config.connection
        assert isinstance(conn, ConfigSection)
        # Проверяем что get() работает и возвращает int (значение зависит от config.yaml)
        assert isinstance(conn.get("max_retries", 2), int)


class TestQtechInterfaceMaps:
    """Тесты маппинга QTech интерфейсов."""

    @pytest.mark.parametrize("full_name,expected_short", [
        # QTech-специфичные типы (пробелы в именах)
        ("TFGigabitEthernet 0/1", "TF0/1"),
        ("TFGigabitEthernet 0/48", "TF0/48"),
        ("AggregatePort 1", "Ag1"),
        ("AggregatePort 100", "Ag100"),
        ("HundredGigabitEthernet 0/55", "Hu0/55"),
    ])
    def test_normalize_short(self, full_name, expected_short):
        """Сокращение QTech имён интерфейсов (с пробелами)."""
        result = normalize_interface_short(full_name)
        assert result == expected_short

    @pytest.mark.parametrize("short_name,expected_full", [
        # QTech-специфичные типы
        ("TF0/1", "TFGigabitEthernet0/1"),
        ("TF0/48", "TFGigabitEthernet0/48"),
        ("Ag1", "AggregatePort1"),
        ("Ag100", "AggregatePort100"),
    ])
    def test_normalize_full(self, short_name, expected_full):
        """Расширение QTech имён интерфейсов."""
        result = normalize_interface_full(short_name)
        assert result == expected_full

    def test_get_aliases_tfgigabit(self):
        """Алиасы для TFGigabitEthernet."""
        aliases = get_interface_aliases("TFGigabitEthernet 0/1")
        assert "TFGigabitEthernet0/1" in aliases  # Без пробела
        assert "TF0/1" in aliases  # Короткое

    def test_get_aliases_aggregate(self):
        """Алиасы для AggregatePort."""
        aliases = get_interface_aliases("AggregatePort 1")
        assert "AggregatePort1" in aliases  # Без пробела
        assert "Ag1" in aliases  # Короткое


class TestQtechLagParsing:
    """Тесты парсинга LAG membership для QTech."""

    @pytest.fixture
    def collector(self):
        """Создаём InterfaceCollector с минимальным конфигом."""
        collector = InterfaceCollector.__new__(InterfaceCollector)
        collector._parser = MagicMock()
        collector._parser.parse.return_value = []  # TextFSM вернёт пустой результат
        return collector

    @pytest.fixture
    def aggregate_output(self):
        """Сырой вывод show aggregatePort summary."""
        return """SU-QSW-6900-56F-01#show aggregatePort summary
AggregatePort MaxPorts SwitchPort Mode   Load balance                 Ports
------------- -------- ---------- ------ ---------------------------- -----------------------------------
Ag1           16       Enabled    TRUNK  src-dst-mac                  Hu0/55  ,Hu0/56
Ag10          16       Enabled    ACCESS src-dst-mac                  TF0/1
Ag50          16       Enabled    TRUNK  src-dst-mac                  Hu0/53
SU-QSW-6900-56F-01#
"""

    def test_parse_lag_membership_qtech(self, collector, aggregate_output):
        """Парсинг QTech aggregatePort summary через regex fallback."""
        result = collector._parse_lag_membership_qtech(aggregate_output)

        # Ag1 содержит Hu0/55 и Hu0/56
        assert result.get("Hu0/55") == "Ag1"
        assert result.get("Hu0/56") == "Ag1"

        # Ag10 содержит TF0/1
        assert result.get("TF0/1") == "Ag10"

        # Ag50 содержит Hu0/53
        assert result.get("Hu0/53") == "Ag50"

    def test_lag_full_names_expanded(self, collector, aggregate_output):
        """Короткие имена раскрываются в полные (с пробелом для QTech)."""
        result = collector._parse_lag_membership_qtech(aggregate_output)

        # Hu0/55 → HundredGigabitEthernet 0/55
        assert result.get("HundredGigabitEthernet 0/55") == "Ag1"
        assert result.get("HundredGigE0/55") == "Ag1"

        # TF0/1 → TFGigabitEthernet 0/1
        assert result.get("TFGigabitEthernet 0/1") == "Ag10"

    def test_lag_multiple_members(self, collector, aggregate_output):
        """Ag1 с двумя member портами."""
        result = collector._parse_lag_membership_qtech(aggregate_output)

        # Оба порта должны маппиться на Ag1
        ag1_members = [k for k, v in result.items() if v == "Ag1"]
        # Как минимум Hu0/55, Hu0/56 + их полные имена
        short_members = [m for m in ag1_members if m.startswith("Hu0/")]
        assert len(short_members) == 2


class TestQtechInventoryTransceiver:
    """Тесты нормализации QTech transceiver данных для inventory."""

    def test_normalize_qtech_transceivers(self):
        """QTech transceiver данные нормализуются в формат inventory."""
        normalizer = InventoryNormalizer()

        # Данные как возвращает NTCParser (lowercase ключи)
        parsed = [
            {"interface": "TFGigabitEthernet 0/1", "type": "10GBASE-SR-SFP+",
             "serial": "RQ114410301879", "connector": "LC", "bandwidth": "10300Mbit/s"},
            {"interface": "TFGigabitEthernet 0/2", "type": "",
             "serial": "", "connector": "", "bandwidth": ""},  # absent
        ]

        items = normalizer.normalize_transceivers(parsed, platform="qtech")

        assert len(items) == 1  # Пустые type пропускаются
        assert items[0]["name"] == "Transceiver TFGigabitEthernet 0/1"
        assert items[0]["pid"] == "10GBASE-SR-SFP+"
        assert items[0]["serial"] == "RQ114410301879"

    def test_qtech_no_show_inventory_command(self):
        """QTech НЕ имеет команды show inventory в COLLECTOR_COMMANDS."""
        from network_collector.core.constants.commands import COLLECTOR_COMMANDS

        inventory_commands = COLLECTOR_COMMANDS.get("inventory", {})
        assert "qtech" not in inventory_commands
        assert "qtech_qsw" not in inventory_commands

    def test_qtech_has_transceiver_command(self):
        """QTech имеет команду transceiver в inventory collector."""
        from network_collector.collectors.inventory import InventoryCollector

        assert "qtech" in InventoryCollector.transceiver_commands
        assert "qtech_qsw" in InventoryCollector.transceiver_commands
        assert InventoryCollector.transceiver_commands["qtech"] == "show interface transceiver"
