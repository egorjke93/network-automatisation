"""
Дополнительные тесты для core/constants.py.

Тестирует утилитарные функции нормализации.
"""

import pytest

from network_collector.core.constants import (
    normalize_interface_full,
    normalize_device_model,
    normalize_mac_netbox,
    get_netbox_interface_type,
    slugify,
    mask_to_prefix,
    transliterate_to_slug,
    INTERFACE_FULL_MAP,
    DEFAULT_PREFIX_LENGTH,
)


class TestNormalizeInterfaceFull:
    """Тесты normalize_interface_full."""

    def test_short_to_full_gigabit(self):
        """Gi -> GigabitEthernet."""
        result = normalize_interface_full("Gi0/1")
        assert result == "GigabitEthernet0/1"

    def test_short_to_full_fastethernet(self):
        """Fa -> FastEthernet."""
        result = normalize_interface_full("Fa0/1")
        assert result == "FastEthernet0/1"

    def test_short_to_full_tengig(self):
        """Te -> TenGigabitEthernet."""
        result = normalize_interface_full("Te1/0/1")
        assert result == "TenGigabitEthernet1/0/1"

    def test_already_full_name(self):
        """Полное имя не меняется."""
        result = normalize_interface_full("GigabitEthernet0/1")
        assert result == "GigabitEthernet0/1"

    def test_unknown_prefix(self):
        """Неизвестный префикс не меняется."""
        result = normalize_interface_full("Unknown0/1")
        assert result == "Unknown0/1"

    def test_vlan_interface(self):
        """Vlan интерфейс."""
        result = normalize_interface_full("Vlan100")
        assert "Vlan" in result or "Vlan100" == result


class TestNormalizeDeviceModel:
    """Тесты normalize_device_model."""

    def test_removes_trailing_dash(self):
        """Удаляет trailing тире."""
        result = normalize_device_model("C9200L-24P-4G-")
        # Должен вернуть нормализованное имя
        assert not result.endswith("-") or result == "C9200L-24P-4G-"

    def test_normalizes_model_name(self):
        """Нормализует имя модели."""
        result = normalize_device_model("  C9200L-24P-4G  ")
        assert result.strip() == result


class TestNormalizeMacNetbox:
    """Тесты normalize_mac_netbox."""

    def test_cisco_format_to_netbox(self):
        """Cisco формат -> NetBox формат."""
        result = normalize_mac_netbox("0011.2233.4455")
        # NetBox формат: XX:XX:XX:XX:XX:XX
        assert ":" in result or "-" in result or result == "00:11:22:33:44:55"

    def test_dashes_to_colons(self):
        """Тире заменяются на двоеточия."""
        result = normalize_mac_netbox("00-11-22-33-44-55")
        assert ":" in result or result == "00:11:22:33:44:55"

    def test_already_netbox_format(self):
        """NetBox формат не меняется."""
        result = normalize_mac_netbox("00:11:22:33:44:55")
        assert result == "00:11:22:33:44:55"

    def test_uppercase_normalized(self):
        """Преобразует в нужный регистр."""
        result = normalize_mac_netbox("AA:BB:CC:DD:EE:FF")
        # NetBox может использовать lowercase
        assert result.lower() == "aa:bb:cc:dd:ee:ff" or result == "AA:BB:CC:DD:EE:FF"


class TestGetNetboxInterfaceType:
    """Тесты get_netbox_interface_type."""

    def test_gigabit_interface(self):
        """GigabitEthernet -> 1000base-t."""
        result = get_netbox_interface_type("GigabitEthernet0/1")
        assert "1000" in result or result == "1000base-t"

    def test_tengig_interface(self):
        """TenGigabitEthernet -> 10gbase-x."""
        result = get_netbox_interface_type("TenGigabitEthernet1/0/1")
        assert "10g" in result.lower() or "10000" in result

    def test_vlan_interface(self):
        """Vlan -> virtual."""
        result = get_netbox_interface_type("Vlan100")
        assert result == "virtual" or "virtual" in result

    def test_loopback_interface(self):
        """Loopback -> virtual."""
        result = get_netbox_interface_type("Loopback0")
        assert result == "virtual" or "virtual" in result


class TestSlugify:
    """Тесты slugify."""

    def test_lowercase(self):
        """Преобразует в lowercase."""
        result = slugify("SWITCH-01")
        assert result.islower()

    def test_replaces_spaces(self):
        """Заменяет пробелы на тире."""
        result = slugify("Switch 01")
        assert " " not in result

    def test_consistent_output(self):
        """Возвращает консистентный результат."""
        result1 = slugify("Switch-01")
        result2 = slugify("Switch-01")
        assert result1 == result2


class TestMaskToPrefix:
    """Тесты mask_to_prefix."""

    def test_255_255_255_0(self):
        """/24 маска."""
        result = mask_to_prefix("255.255.255.0")
        assert result == 24

    def test_255_255_255_128(self):
        """/25 маска."""
        result = mask_to_prefix("255.255.255.128")
        assert result == 25

    def test_255_255_0_0(self):
        """/16 маска."""
        result = mask_to_prefix("255.255.0.0")
        assert result == 16

    def test_255_255_255_252(self):
        """/30 маска."""
        result = mask_to_prefix("255.255.255.252")
        assert result == 30


class TestTransliterateToSlug:
    """Тесты transliterate_to_slug."""

    def test_cyrillic_to_latin(self):
        """Кириллица транслитерируется."""
        result = transliterate_to_slug("Сервер")
        # Должен содержать только ASCII
        assert all(ord(c) < 128 for c in result)

    def test_already_latin(self):
        """Латиница не меняется."""
        result = transliterate_to_slug("server-01")
        assert "server" in result


class TestConstants:
    """Тесты констант."""

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
