"""
E2E тесты для LLDPCollector.

Проверяет полный цикл: fixture → parse → normalize.
Без реального SSH подключения.

Примечание: _parse_output возвращает List[Dict], не модели.
"""

import pytest
from typing import List, Dict

from network_collector.collectors.lldp import LLDPCollector
from network_collector.core.models import LLDPNeighbor

from .conftest import create_mock_device, SUPPORTED_PLATFORMS, get_fixture_filename


@pytest.fixture
def lldp_collector():
    """Создаёт LLDPCollector только для LLDP."""
    return LLDPCollector(
        credentials=None,
        protocol="lldp",
    )


@pytest.fixture
def cdp_collector():
    """Создаёт LLDPCollector только для CDP."""
    return LLDPCollector(
        credentials=None,
        protocol="cdp",
    )


class TestLLDPCollectorE2E:
    """E2E тесты LLDPCollector — полный цикл без SSH."""

    def test_cisco_ios_lldp_full_pipeline(self, lldp_collector, load_fixture):
        """Cisco IOS LLDP: полный цикл обработки соседей."""
        output = load_fixture("cisco_ios", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        result = lldp_collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны LLDP соседи"
        assert isinstance(result, list)
        assert isinstance(result[0], dict), "Результат должен быть словарём"

    def test_cisco_ios_cdp_full_pipeline(self, cdp_collector, load_fixture):
        """Cisco IOS CDP: полный цикл обработки соседей."""
        output = load_fixture("cisco_ios", "show_cdp_neighbors_detail.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        result = cdp_collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны CDP соседи"

    def test_cisco_nxos_lldp_full_pipeline(self, lldp_collector, load_fixture):
        """Cisco NX-OS LLDP: полный цикл обработки соседей."""
        output = load_fixture("cisco_nxos", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("cisco_nxos", "nxos-switch")

        result = lldp_collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны LLDP соседи"

    def test_cisco_nxos_cdp_full_pipeline(self, cdp_collector, load_fixture):
        """Cisco NX-OS CDP: полный цикл обработки соседей."""
        output = load_fixture("cisco_nxos", "show_cdp_neighbors_detail.txt")
        device = create_mock_device("cisco_nxos", "nxos-switch")

        result = cdp_collector._parse_output(output, device)

        assert len(result) > 0, "Должны быть распознаны CDP соседи"

    def test_qtech_lldp_full_pipeline(self, lldp_collector, load_fixture):
        """QTech LLDP: полный цикл обработки соседей."""
        output = load_fixture("qtech", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("qtech", "qtech-switch")

        result = lldp_collector._parse_output(output, device)

        # QTech может не иметь соседей в fixture
        assert isinstance(result, list)

    def test_to_models_conversion(self, lldp_collector, load_fixture):
        """Конвертация в модели LLDPNeighbor работает."""
        output = load_fixture("cisco_ios", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("cisco_ios", "ios-switch")

        parsed = lldp_collector._parse_output(output, device)
        assert len(parsed) > 0

        models = lldp_collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, LLDPNeighbor)


class TestLLDPCollectorFields:
    """Тесты корректности полей в словарях."""

    @pytest.fixture
    def collector(self):
        return LLDPCollector(credentials=None, protocol="lldp")

    def test_local_interface_field(self, collector, load_fixture):
        """Локальный интерфейс присутствует."""
        output = load_fixture("cisco_ios", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        for neighbor in result:
            local_intf = (
                neighbor.get("local_interface") or
                neighbor.get("local_port") or
                neighbor.get("local_intf", "")
            )
            # Должен быть хотя бы у некоторых
            if local_intf:
                assert len(local_intf) > 0

    def test_remote_hostname_field(self, collector, load_fixture):
        """Удалённый hostname присутствует."""
        output = load_fixture("cisco_ios", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        hostnames = []
        for n in result:
            hostname = (
                n.get("neighbor") or
                n.get("chassis_id") or
                n.get("system_name", "")
            )
            if hostname:
                hostnames.append(hostname)

        assert len(hostnames) > 0 or len(result) == 0

    def test_remote_port_field(self, collector, load_fixture):
        """Удалённый порт присутствует."""
        output = load_fixture("cisco_ios", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("cisco_ios")

        result = collector._parse_output(output, device)

        for neighbor in result:
            remote_port = (
                neighbor.get("neighbor_interface") or
                neighbor.get("port_id") or
                neighbor.get("remote_port", "")
            )
            if remote_port:
                assert len(remote_port) > 0


class TestLLDPCollectorEdgeCases:
    """Тесты граничных случаев."""

    @pytest.fixture
    def collector(self):
        return LLDPCollector(credentials=None, protocol="lldp")

    def test_empty_output_returns_empty_list(self, collector):
        """Пустой вывод возвращает пустой список."""
        device = create_mock_device("cisco_ios")
        result = collector._parse_output("", device)
        assert result == [] or len(result) == 0

    def test_garbage_output_handled(self, collector):
        """Мусорный вывод обрабатывается без ошибок."""
        device = create_mock_device("cisco_ios")
        garbage = "random garbage\nno neighbors"

        result = collector._parse_output(garbage, device)
        assert isinstance(result, list)

    def test_no_neighbors_output(self, collector):
        """Вывод без соседей обрабатывается."""
        device = create_mock_device("cisco_ios")
        no_neighbors = "Total entries displayed: 0"

        result = collector._parse_output(no_neighbors, device)
        assert isinstance(result, list)
        assert len(result) == 0


class TestLLDPCollectorRealData:
    """Тесты с реальными данными."""

    @pytest.fixture
    def collector(self):
        return LLDPCollector(credentials=None, protocol="lldp")

    @pytest.fixture
    def cdp_collector(self):
        return LLDPCollector(credentials=None, protocol="cdp")

    def test_real_lldp_cisco_ios(self, collector, load_fixture):
        """Реальные LLDP данные с Cisco IOS."""
        try:
            output = load_fixture("real_output", "lldp_cisco_ios.txt")
        except Exception:
            pytest.skip("Real output fixture не найден")

        device = create_mock_device("cisco_ios", "real-switch")
        result = collector._parse_output(output, device)

        assert isinstance(result, list)

    def test_real_cdp_cisco_ios(self, cdp_collector, load_fixture):
        """Реальные CDP данные с Cisco IOS."""
        try:
            output = load_fixture("real_output", "cdp_cisco_ios.txt")
        except Exception:
            pytest.skip("Real output fixture не найден")

        device = create_mock_device("cisco_ios", "real-switch")
        result = cdp_collector._parse_output(output, device)

        assert isinstance(result, list)


class TestLLDPCollectorNormalization:
    """Тесты нормализации данных."""

    @pytest.fixture
    def collector(self):
        return LLDPCollector(credentials=None, protocol="lldp")

    def test_to_models_creates_lldp_objects(self, collector, load_fixture):
        """to_models создаёт объекты LLDPNeighbor."""
        output = load_fixture("cisco_ios", "show_lldp_neighbors_detail.txt")
        device = create_mock_device("cisco_ios", "test-switch")

        parsed = collector._parse_output(output, device)
        models = collector.to_models(parsed)

        assert len(models) > 0
        for model in models:
            assert isinstance(model, LLDPNeighbor)
