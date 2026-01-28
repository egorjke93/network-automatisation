"""
Tests for MACNormalizer.

Проверяет нормализацию MAC-таблицы:
- Форматирование MAC
- Фильтрация интерфейсов/VLAN
- Дедупликация
- Определение online/offline статуса
"""

import pytest

from network_collector.core.domain import MACNormalizer
from network_collector.core.models import MACEntry


@pytest.mark.unit
class TestMACNormalizerBasic:
    """Базовые тесты нормализации MAC."""

    def setup_method(self):
        self.normalizer = MACNormalizer()

    def test_normalize_basic(self):
        """Базовая нормализация MAC записей."""
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"},
            {"mac": "0011.2233.4466", "interface": "Gi0/2", "vlan": "20"},
        ]
        result = self.normalizer.normalize(raw_data)

        assert len(result) == 2
        assert isinstance(result[0], MACEntry)
        assert result[0].interface == "Gi0/1"
        assert result[0].vlan == "10"

    def test_normalize_with_metadata(self):
        """Нормализация с hostname и device_ip."""
        raw_data = [{"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"}]
        result = self.normalizer.normalize(
            raw_data, hostname="switch-01", device_ip="192.168.1.1"
        )

        assert result[0].hostname == "switch-01"
        assert result[0].device_ip == "192.168.1.1"

    def test_normalize_interface_short(self):
        """Сокращение имён интерфейсов."""
        normalizer = MACNormalizer(normalize_interfaces=True)
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "GigabitEthernet0/1", "vlan": "10"}
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert result[0]["interface"] == "Gi0/1"

    def test_normalize_interface_preserve_full(self):
        """Сохранение полных имён интерфейсов."""
        normalizer = MACNormalizer(normalize_interfaces=False)
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "GigabitEthernet0/1", "vlan": "10"}
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert result[0]["interface"] == "GigabitEthernet0/1"


@pytest.mark.unit
class TestMACNormalizerMACFormat:
    """Тесты форматирования MAC-адресов."""

    @pytest.mark.parametrize("mac_format, input_mac, expected", [
        ("ieee", "0011.2233.4455", "00:11:22:33:44:55"),
        ("cisco", "00:11:22:33:44:55", "0011.2233.4455"),
        ("ieee", "001122334455", "00:11:22:33:44:55"),
    ])
    def test_mac_format(self, mac_format, input_mac, expected):
        """Тест разных форматов MAC."""
        normalizer = MACNormalizer(mac_format=mac_format)
        raw_data = [{"mac": input_mac, "interface": "Gi0/1", "vlan": "10"}]
        result = normalizer.normalize_dicts(raw_data)

        assert result[0]["mac"] == expected


@pytest.mark.unit
class TestMACNormalizerFiltering:
    """Тесты фильтрации записей."""

    def test_exclude_interfaces_regex(self):
        """Исключение интерфейсов по regex."""
        # Паттерны должны учитывать нормализованные имена (Vlan10 → Vl10)
        normalizer = MACNormalizer(exclude_interfaces=["Po.*", "Vl.*"])
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"},
            {"mac": "0011.2233.4466", "interface": "Po1", "vlan": "10"},
            {"mac": "0011.2233.4477", "interface": "Vlan10", "vlan": "10"},  # → Vl10
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        assert result[0]["interface"] == "Gi0/1"

    def test_exclude_vlans(self):
        """Исключение VLAN."""
        normalizer = MACNormalizer(exclude_vlans=[1, 1000, 4094])
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"},
            {"mac": "0011.2233.4466", "interface": "Gi0/2", "vlan": "1"},
            {"mac": "0011.2233.4477", "interface": "Gi0/3", "vlan": "1000"},
            {"mac": "0011.2233.4488", "interface": "Gi0/4", "vlan": "4094"},
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        assert result[0]["vlan"] == "10"

    def test_filter_trunk_ports(self):
        """Фильтрация trunk портов."""
        normalizer = MACNormalizer()
        data = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1"},
            {"mac": "0011.2233.4466", "interface": "Gi0/2"},
            {"mac": "0011.2233.4477", "interface": "Po1"},
        ]
        trunk_interfaces = {"Gi0/2", "Po1"}

        result = normalizer.filter_trunk_ports(data, trunk_interfaces)

        assert len(result) == 1
        assert result[0]["interface"] == "Gi0/1"


@pytest.mark.unit
class TestMACNormalizerDeduplication:
    """Тесты дедупликации."""

    def test_deduplicate_same_mac_vlan_interface(self):
        """Дедупликация одинаковых записей."""
        normalizer = MACNormalizer()
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"},
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"},  # Дубликат
            {"mac": "0011.2233.4455", "interface": "Gi0/2", "vlan": "10"},  # Другой порт
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 2  # Дубликат удалён

    def test_deduplicate_different_mac_formats(self):
        """Дедупликация MAC в разных форматах."""
        normalizer = MACNormalizer()
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"},
            {"mac": "00:11:22:33:44:55", "interface": "Gi0/1", "vlan": "10"},  # Тот же MAC
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1

    def test_deduplicate_final(self):
        """Финальная дедупликация по полному ключу."""
        normalizer = MACNormalizer()
        data = [
            {"hostname": "sw1", "mac": "0011.2233.4455", "vlan": "10", "interface": "Gi0/1"},
            {"hostname": "sw1", "mac": "0011.2233.4455", "vlan": "10", "interface": "Gi0/1"},
            {"hostname": "sw2", "mac": "0011.2233.4455", "vlan": "10", "interface": "Gi0/1"},
        ]
        result = normalizer.deduplicate(data)

        assert len(result) == 2  # sw1 + sw2


@pytest.mark.unit
class TestMACNormalizerStatus:
    """Тесты определения online/offline статуса."""

    def test_status_online(self):
        """Порт connected → online."""
        normalizer = MACNormalizer()
        raw_data = [{"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"}]
        interface_status = {"Gi0/1": "connected"}

        result = normalizer.normalize_dicts(raw_data, interface_status)

        assert result[0]["status"] == "online"

    def test_status_offline(self):
        """Порт notconnect → offline."""
        normalizer = MACNormalizer()
        raw_data = [{"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"}]
        interface_status = {"Gi0/1": "notconnect"}

        result = normalizer.normalize_dicts(raw_data, interface_status)

        assert result[0]["status"] == "offline"

    def test_status_unknown(self):
        """Нет данных о порте → unknown."""
        normalizer = MACNormalizer()
        raw_data = [{"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"}]
        interface_status = {}  # Нет данных

        result = normalizer.normalize_dicts(raw_data, interface_status)

        assert result[0]["status"] == "unknown"

    @pytest.mark.parametrize("port_status, expected", [
        ("connected", "online"),
        ("up", "online"),
        ("notconnect", "offline"),
        ("disabled", "offline"),
        ("err-disabled", "offline"),
    ])
    def test_status_mapping(self, port_status, expected):
        """Тест маппинга статусов портов."""
        normalizer = MACNormalizer()
        raw_data = [{"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10"}]
        interface_status = {"Gi0/1": port_status}

        result = normalizer.normalize_dicts(raw_data, interface_status)

        assert result[0]["status"] == expected


@pytest.mark.unit
class TestMACNormalizerMerge:
    """Тесты объединения MAC-таблиц."""

    def test_merge_sticky_macs(self):
        """Объединение с sticky MAC."""
        normalizer = MACNormalizer()
        mac_table = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "status": "online"},
        ]
        sticky_macs = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1"},  # Уже есть
            {"mac": "0011.2233.4466", "interface": "Gi0/2"},  # Новый
        ]

        result = normalizer.merge_sticky_macs(mac_table, sticky_macs)

        assert len(result) == 2
        # Sticky MAC помечен как offline
        assert result[1]["status"] == "offline"

    def test_merge_sticky_macs_empty(self):
        """Пустой sticky список."""
        normalizer = MACNormalizer()
        mac_table = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1"},
        ]
        sticky_macs = []

        result = normalizer.merge_sticky_macs(mac_table, sticky_macs)

        assert len(result) == 1


@pytest.mark.unit
class TestMACNormalizerMACType:
    """Тесты определения типа MAC."""

    @pytest.mark.parametrize("raw_type, expected", [
        ("DYNAMIC", "dynamic"),
        ("dynamic", "dynamic"),
        ("STATIC", "static"),
        ("static", "static"),
        ("sticky", "static"),
        ("", "static"),
    ])
    def test_mac_type_normalization(self, raw_type, expected):
        """Тест нормализации типа MAC."""
        normalizer = MACNormalizer()
        raw_data = [
            {"mac": "0011.2233.4455", "interface": "Gi0/1", "vlan": "10", "type": raw_type}
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert result[0]["type"] == expected


@pytest.mark.unit
class TestMACNormalizerEdgeCases:
    """Тесты edge cases и NTC Templates особенностей."""

    def test_destination_port_as_list(self):
        """destination_port от NTC Templates может быть списком (например ['CPU'])."""
        normalizer = MACNormalizer()
        # NTC Templates возвращает destination_port как список для некоторых записей
        raw_data = [
            {"mac": "0011.2233.4455", "destination_port": ["CPU"], "vlan": "1"},
            {"mac": "0011.2233.4466", "destination_port": ["Router"], "vlan": "1"},
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 2
        assert result[0]["interface"] == "CPU"
        assert result[1]["interface"] == "Router"

    def test_destination_port_empty_list(self):
        """Пустой список destination_port обрабатывается корректно."""
        normalizer = MACNormalizer()
        raw_data = [
            {"mac": "0011.2233.4455", "destination_port": [], "vlan": "1"},
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        assert result[0]["interface"] == ""

    def test_interface_as_list(self):
        """interface как список тоже обрабатывается."""
        normalizer = MACNormalizer()
        raw_data = [
            {"mac": "0011.2233.4455", "interface": ["Gi0/1", "Gi0/2"], "vlan": "10"},
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        # Берётся первый элемент списка
        assert result[0]["interface"] == "Gi0/1"

    def test_destination_port_string(self):
        """destination_port как строка работает (fallback от interface)."""
        normalizer = MACNormalizer()
        raw_data = [
            {"mac": "0011.2233.4455", "destination_port": "Gi0/1", "vlan": "10"},
        ]
        result = normalizer.normalize_dicts(raw_data)

        assert len(result) == 1
        assert result[0]["interface"] == "Gi0/1"
