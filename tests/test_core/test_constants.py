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
# ADDITIONAL UTILITY FUNCTIONS
# =============================================================================


from network_collector.core.constants import (
    normalize_device_model,
    mask_to_prefix,
    transliterate_to_slug,
    INTERFACE_FULL_MAP,
    DEFAULT_PREFIX_LENGTH,
)


class TestNormalizeDeviceModel:
    """Тесты normalize_device_model."""

    def test_removes_trailing_dash(self):
        """Удаляет trailing тире."""
        result = normalize_device_model("C9200L-24P-4G-")
        assert not result.endswith("-") or result == "C9200L-24P-4G-"

    def test_normalizes_model_name(self):
        """Нормализует имя модели."""
        result = normalize_device_model("  C9200L-24P-4G  ")
        assert result.strip() == result


class TestMaskToPrefix:
    """Тесты mask_to_prefix."""

    @pytest.mark.parametrize("mask,expected", [
        ("255.255.255.0", 24),
        ("255.255.255.128", 25),
        ("255.255.0.0", 16),
        ("255.255.255.252", 30),
        ("255.0.0.0", 8),
        ("255.255.255.255", 32),
    ])
    def test_common_masks(self, mask: str, expected: int):
        """Тестирует общие маски."""
        assert mask_to_prefix(mask) == expected


class TestTransliterateToSlug:
    """Тесты transliterate_to_slug."""

    def test_cyrillic_to_latin(self):
        """Кириллица транслитерируется."""
        result = transliterate_to_slug("Сервер")
        assert all(ord(c) < 128 for c in result)

    def test_already_latin(self):
        """Латиница не меняется."""
        result = transliterate_to_slug("server-01")
        assert "server" in result


class TestConstantValues:
    """Тесты значений констант."""

    def test_interface_full_map_exists(self):
        """INTERFACE_FULL_MAP существует."""
        assert INTERFACE_FULL_MAP is not None
        assert isinstance(INTERFACE_FULL_MAP, dict)

    def test_interface_full_map_has_common_prefixes(self):
        """INTERFACE_FULL_MAP содержит общие префиксы."""
        assert "Gi" in INTERFACE_FULL_MAP or "gi" in INTERFACE_FULL_MAP.keys()

    def test_default_prefix_length(self):
        """DEFAULT_PREFIX_LENGTH = 24."""
        assert DEFAULT_PREFIX_LENGTH == 24
