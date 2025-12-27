"""
Тесты для функций нормализации в core/constants.py.

Тестируем:
- normalize_mac_* — все форматы MAC
- normalize_interface_short — сокращение интерфейсов
- slugify — генерация slug для NetBox
"""

import pytest

from network_collector.core.constants import (
    normalize_mac_raw,
    normalize_mac_ieee,
    normalize_mac_netbox,
    normalize_mac_cisco,
    normalize_mac,
    normalize_interface_short,
    normalize_interface_full,
    slugify,
)


# =============================================================================
# MAC NORMALIZATION TESTS
# =============================================================================


class TestNormalizeMacRaw:
    """Тесты normalize_mac_raw — 12 символов, lowercase."""

    @pytest.mark.parametrize("mac,expected", [
        # IEEE формат
        ("00:11:22:33:44:55", "001122334455"),
        ("AA:BB:CC:DD:EE:FF", "aabbccddeeff"),
        # Cisco формат
        ("0011.2233.4455", "001122334455"),
        ("aabb.ccdd.eeff", "aabbccddeeff"),
        # Unix формат
        ("00-11-22-33-44-55", "001122334455"),
        ("AA-BB-CC-DD-EE-FF", "aabbccddeeff"),
        # Без разделителей
        ("001122334455", "001122334455"),
        ("AABBCCDDEEFF", "aabbccddeeff"),
        # С пробелами
        ("  00:11:22:33:44:55  ", "001122334455"),
    ])
    def test_valid_mac(self, mac: str, expected: str):
        """Валидные MAC нормализуются в 12 символов lowercase."""
        assert normalize_mac_raw(mac) == expected

    @pytest.mark.parametrize("mac", [
        "",
        None,
        "invalid",
        "00:11:22:33:44",  # слишком короткий
        "00:11:22:33:44:55:66",  # слишком длинный
        # Примечание: hex валидность не проверяется — MAC приходит от устройств
    ])
    def test_invalid_mac_returns_empty(self, mac):
        """Невалидные MAC возвращают пустую строку."""
        result = normalize_mac_raw(mac) if mac else normalize_mac_raw("")
        assert result == ""


class TestNormalizeMacIeee:
    """Тесты normalize_mac_ieee — формат aa:bb:cc:dd:ee:ff."""

    @pytest.mark.parametrize("mac,expected", [
        ("0011.2233.4455", "00:11:22:33:44:55"),
        ("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"),
        ("00-11-22-33-44-55", "00:11:22:33:44:55"),
        ("001122334455", "00:11:22:33:44:55"),
    ])
    def test_formats_as_ieee(self, mac: str, expected: str):
        assert normalize_mac_ieee(mac) == expected

    def test_invalid_returns_empty(self):
        assert normalize_mac_ieee("invalid") == ""
        assert normalize_mac_ieee("") == ""


class TestNormalizeMacNetbox:
    """Тесты normalize_mac_netbox — формат AA:BB:CC:DD:EE:FF."""

    @pytest.mark.parametrize("mac,expected", [
        ("0011.2233.4455", "00:11:22:33:44:55".upper()),
        ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),
        ("00-11-22-33-44-55", "00:11:22:33:44:55".upper()),
    ])
    def test_formats_as_netbox(self, mac: str, expected: str):
        assert normalize_mac_netbox(mac) == expected

    def test_invalid_returns_empty(self):
        assert normalize_mac_netbox("invalid") == ""


class TestNormalizeMacCisco:
    """Тесты normalize_mac_cisco — формат aabb.ccdd.eeff."""

    @pytest.mark.parametrize("mac,expected", [
        ("00:11:22:33:44:55", "0011.2233.4455"),
        ("AA:BB:CC:DD:EE:FF", "aabb.ccdd.eeff"),
        ("00-11-22-33-44-55", "0011.2233.4455"),
        ("001122334455", "0011.2233.4455"),
    ])
    def test_formats_as_cisco(self, mac: str, expected: str):
        assert normalize_mac_cisco(mac) == expected

    def test_invalid_returns_empty(self):
        assert normalize_mac_cisco("invalid") == ""


class TestNormalizeMacWithFormat:
    """Тесты normalize_mac с параметром format."""

    @pytest.mark.parametrize("format,expected", [
        ("raw", "aabbccddeeff"),
        ("ieee", "aa:bb:cc:dd:ee:ff"),
        ("netbox", "AA:BB:CC:DD:EE:FF"),
        ("cisco", "aabb.ccdd.eeff"),
        ("unix", "aa-bb-cc-dd-ee-ff"),
    ])
    def test_all_formats(self, format: str, expected: str):
        mac = "AA:BB:CC:DD:EE:FF"
        assert normalize_mac(mac, format=format) == expected

    def test_default_format_is_ieee(self):
        mac = "AABBCCDDEEFF"
        assert normalize_mac(mac) == "aa:bb:cc:dd:ee:ff"

    def test_invalid_mac_returns_empty(self):
        assert normalize_mac("invalid", format="ieee") == ""


# =============================================================================
# INTERFACE NORMALIZATION TESTS
# =============================================================================


class TestNormalizeInterfaceShort:
    """Тесты normalize_interface_short — сокращение интерфейсов."""

    @pytest.mark.parametrize("interface,expected", [
        # Полные имена → короткие
        ("GigabitEthernet0/1", "Gi0/1"),
        ("GigabitEthernet1/0/24", "Gi1/0/24"),
        ("FastEthernet0/1", "Fa0/1"),
        ("TenGigabitEthernet1/1/1", "Te1/1/1"),
        ("Ethernet1/1", "Eth1/1"),  # NX-OS standard
        ("Port-channel1", "Po1"),
        ("Vlan100", "Vl100"),
        ("Loopback0", "Lo0"),
        # Короткие — без изменений
        ("Gi0/1", "Gi0/1"),
        ("Fa0/1", "Fa0/1"),
        ("Te1/1/1", "Te1/1/1"),
        ("Eth1/1", "Eth1/1"),  # уже короткий
        # CDP/LLDP форматы с пробелами
        ("Ten 1/1/4", "Te1/1/4"),
        ("Twe 1/0/17", "Twe1/0/17"),
        # TwentyFiveGigabitEthernet
        ("TwentyFiveGigabitEthernet1/0/1", "Twe1/0/1"),
    ])
    def test_shortens_interface(self, interface: str, expected: str):
        assert normalize_interface_short(interface) == expected

    def test_empty_returns_empty(self):
        assert normalize_interface_short("") == ""
        assert normalize_interface_short(None) == ""

    def test_unknown_interface_unchanged(self):
        """Неизвестные интерфейсы возвращаются как есть."""
        assert normalize_interface_short("mgmt0") == "mgmt0"
        assert normalize_interface_short("Null0") == "Null0"


class TestNormalizeInterfaceShortLowercase:
    """Тесты lowercase параметра для сравнения интерфейсов."""

    @pytest.mark.parametrize("interface,expected", [
        ("GigabitEthernet0/1", "gi0/1"),
        ("Ten 1/1/4", "te1/1/4"),
        ("TenGigabitEthernet1/1/4", "te1/1/4"),
        ("Twe1/0/17", "twe1/0/17"),
    ])
    def test_lowercase_for_comparison(self, interface: str, expected: str):
        result = normalize_interface_short(interface, lowercase=True)
        assert result == expected


class TestNormalizeInterfaceFull:
    """Тесты normalize_interface_full — расширение сокращений."""

    @pytest.mark.parametrize("interface,expected", [
        ("Gi0/1", "GigabitEthernet0/1"),
        ("Fa0/1", "FastEthernet0/1"),
        ("Te1/1/1", "TenGigabitEthernet1/1/1"),
        ("Et1/1", "Ethernet1/1"),
        ("Po1", "Port-channel1"),
        ("Vl100", "Vlan100"),
        ("Lo0", "Loopback0"),
        # Полные — без изменений
        ("GigabitEthernet0/1", "GigabitEthernet0/1"),
    ])
    def test_expands_interface(self, interface: str, expected: str):
        assert normalize_interface_full(interface) == expected


# =============================================================================
# SLUGIFY TESTS
# =============================================================================


class TestSlugify:
    """Тесты slugify — генерация slug для NetBox."""

    @pytest.mark.parametrize("name,expected", [
        # Пробелы → дефисы
        ("Main Office", "main-office"),
        ("Data Center 1", "data-center-1"),
        # Подчёркивания → дефисы
        ("my_site", "my-site"),
        ("data_center_1", "data-center-1"),
        # Слэши → дефисы
        ("C9200L-24P/4X", "c9200l-24p-4x"),
        ("N9K-C93180YC/EX", "n9k-c93180yc-ex"),
        # Смешанный регистр → lowercase
        ("MainOffice", "mainoffice"),
        ("DATACENTER", "datacenter"),
        # Комбинации
        ("Main Office/DC-1", "main-office-dc-1"),
        ("My_Site Name/Zone", "my-site-name-zone"),
    ])
    def test_generates_valid_slug(self, name: str, expected: str):
        assert slugify(name) == expected

    def test_empty_returns_empty(self):
        assert slugify("") == ""
        assert slugify(None) == ""

    def test_already_valid_slug(self):
        """Валидные slug не меняются."""
        assert slugify("main-office") == "main-office"
        assert slugify("switch-01") == "switch-01"


# =============================================================================
# NETBOX INTERFACE TYPE TESTS
# =============================================================================


from network_collector.core.constants import get_netbox_interface_type


class TestGetNetboxInterfaceType:
    """Тесты get_netbox_interface_type — определение типа для NetBox."""

    # LAG интерфейсы
    @pytest.mark.parametrize("name,expected", [
        ("Port-channel1", "lag"),
        ("Po1", "lag"),
        ("port-channel10", "lag"),
    ])
    def test_lag_interfaces(self, name: str, expected: str):
        assert get_netbox_interface_type(name) == expected

    def test_lag_by_port_type(self):
        assert get_netbox_interface_type("Eth1/1", port_type="lag") == "lag"

    # Виртуальные интерфейсы
    @pytest.mark.parametrize("name,expected", [
        ("Vlan100", "virtual"),
        ("Loopback0", "virtual"),
        ("lo0", "virtual"),
        ("Null0", "virtual"),
    ])
    def test_virtual_interfaces(self, name: str, expected: str):
        assert get_netbox_interface_type(name) == expected

    # Management интерфейсы
    @pytest.mark.parametrize("name", ["mgmt0", "Management1", "oob0"])
    def test_mgmt_interfaces_are_copper(self, name: str):
        assert get_netbox_interface_type(name) == "1000base-t"

    # По media_type (высший приоритет)
    @pytest.mark.parametrize("media,expected", [
        ("SFP-10GBase-SR", "10gbase-sr"),
        ("SFP-10GBase-LR", "10gbase-lr"),
        ("QSFP 100G LR4", "100gbase-lr4"),
        ("SFP-25GBase-SR", "25gbase-sr"),
    ])
    def test_media_type_detection(self, media: str, expected: str):
        result = get_netbox_interface_type("Eth1/1", media_type=media)
        assert result == expected

    # По имени интерфейса
    @pytest.mark.parametrize("name,expected", [
        ("GigabitEthernet0/1", "1000base-t"),
        ("Gi0/1", "1000base-t"),
        ("TenGigabitEthernet1/1", "10gbase-x-sfpp"),
        ("Te1/1", "10gbase-x-sfpp"),
        ("TwentyFiveGigE1/0/1", "25gbase-x-sfp28"),
        ("Twe1/0/1", "25gbase-x-sfp28"),
        ("FortyGigabitEthernet1/0/1", "40gbase-x-qsfpp"),
        ("HundredGigE1/0/49", "100gbase-x-qsfp28"),
        ("FastEthernet0/1", "100base-tx"),
        ("Fa0/1", "100base-tx"),
    ])
    def test_interface_name_detection(self, name: str, expected: str):
        assert get_netbox_interface_type(name) == expected

    # SFP порты по media_type
    def test_gi_with_sfp_media(self):
        result = get_netbox_interface_type("Gi0/1", media_type="no transceiver")
        assert result == "1000base-x-sfp"

    def test_gi_with_sfp_hardware(self):
        result = get_netbox_interface_type("Gi0/1", hardware_type="Gigabit Ethernet SFP")
        assert result == "1000base-x-sfp"

    # По скорости (fallback)
    @pytest.mark.parametrize("speed,expected", [
        (100, "100base-tx"),
        (1000, "1000base-t"),
        (10000, "10gbase-t"),
        (25000, "25gbase-x-sfp28"),
        (40000, "40gbase-x-qsfpp"),
        (100000, "100gbase-x-qsfp28"),
    ])
    def test_speed_fallback(self, speed: int, expected: str):
        # Неизвестное имя + скорость
        result = get_netbox_interface_type("unknown0/1", speed_mbps=speed)
        assert result == expected

    # NX-OS Ethernet
    def test_nxos_ethernet_10g(self):
        result = get_netbox_interface_type(
            "Ethernet1/1",
            hardware_type="100/1000/10000 Ethernet",
        )
        assert result == "10gbase-x-sfpp"

    def test_nxos_ethernet_1g(self):
        result = get_netbox_interface_type(
            "Ethernet1/1",
            hardware_type="100/1000 Ethernet",
        )
        assert result == "1000base-t"

    # Default
    def test_default_type(self):
        result = get_netbox_interface_type("unknown0/0")
        assert result == "1000base-t"
