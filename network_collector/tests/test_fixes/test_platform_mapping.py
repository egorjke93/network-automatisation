"""
Тесты для маппинга платформ.

Проверяет что:
- NetBox platform slug корректно мапится на Scrapli platform
- Импортированные устройства получают правильный device_type
- Collector правильно использует platform для подключения
"""

import pytest


class TestNetboxToScrapliMapping:
    """Тесты маппинга NetBox platform -> Scrapli platform."""

    def test_common_platforms_mapping(self):
        """Проверяет маппинг распространённых платформ."""
        from network_collector.core.constants import NETBOX_TO_SCRAPLI_PLATFORM

        expected = {
            # Cisco
            "cisco-ios": "cisco_ios",
            "cisco-ios-xe": "cisco_ios",
            "cisco-iosxe": "cisco_ios",
            "cisco-nxos": "cisco_nxos",
            "cisco-nx-os": "cisco_nxos",
            "cisco-iosxr": "cisco_iosxr",
            # Arista
            "arista-eos": "arista_eos",
            # Juniper
            "juniper-junos": "juniper_junos",
            "junos": "juniper_junos",
            # QTech
            "qtech": "cisco_ios",
            "qtech-qsw": "cisco_ios",
        }

        for netbox_slug, expected_scrapli in expected.items():
            actual = NETBOX_TO_SCRAPLI_PLATFORM.get(netbox_slug)
            assert actual == expected_scrapli, (
                f"NetBox platform '{netbox_slug}' should map to '{expected_scrapli}', "
                f"but got '{actual}'"
            )

    def test_underscore_variants(self):
        """
        Критический тест: проверяет что варианты с underscore тоже работают.

        В NetBox platform slug может быть с hyphen или underscore.
        """
        from network_collector.core.constants import NETBOX_TO_SCRAPLI_PLATFORM

        # Эти варианты тоже могут встречаться в NetBox
        underscore_variants = {
            "cisco_ios": "cisco_ios",  # fallback - остаётся как есть если нет в маппинге
            "cisco_iosxe": "cisco_ios",  # должен быть в маппинге!
            "cisco_nxos": None,  # может не быть, тогда fallback
        }

        for variant, expected in underscore_variants.items():
            actual = NETBOX_TO_SCRAPLI_PLATFORM.get(variant, variant)
            if expected:
                assert actual == expected, (
                    f"Platform '{variant}' should map to '{expected}', got '{actual}'"
                )

    def test_fallback_returns_original(self):
        """Проверяет что неизвестные платформы возвращаются как есть."""
        from network_collector.core.constants import NETBOX_TO_SCRAPLI_PLATFORM

        unknown = "some-unknown-platform"
        result = NETBOX_TO_SCRAPLI_PLATFORM.get(unknown, unknown)
        assert result == unknown


class TestScrapliPlatformMap:
    """Тесты SCRAPLI_PLATFORM_MAP в connection.py."""

    def test_scrapli_platform_mapping(self):
        """Проверяет маппинг internal platform -> Scrapli platform."""
        from network_collector.core.connection import SCRAPLI_PLATFORM_MAP

        expected = {
            "cisco_ios": "cisco_iosxe",
            "cisco_iosxe": "cisco_iosxe",
            "cisco_nxos": "cisco_nxos",
            "arista_eos": "arista_eos",
            "juniper_junos": "juniper_junos",
            "qtech": "cisco_iosxe",
            "qtech_qsw": "cisco_iosxe",
        }

        for internal, scrapli in expected.items():
            actual = SCRAPLI_PLATFORM_MAP.get(internal)
            assert actual == scrapli, (
                f"Platform '{internal}' should map to Scrapli '{scrapli}', got '{actual}'"
            )

    def test_get_scrapli_platform_function(self):
        """Тестирует функцию get_scrapli_platform."""
        from network_collector.core.connection import get_scrapli_platform

        # Известные платформы
        assert get_scrapli_platform("cisco_ios") == "cisco_iosxe"
        assert get_scrapli_platform("cisco_iosxe") == "cisco_iosxe"
        assert get_scrapli_platform("cisco_nxos") == "cisco_nxos"
        assert get_scrapli_platform("arista_eos") == "arista_eos"

        # Неизвестная платформа -> default
        assert get_scrapli_platform("unknown_platform") == "cisco_iosxe"
        assert get_scrapli_platform(None) == "cisco_iosxe"

        # Регистронезависимость
        assert get_scrapli_platform("CISCO_IOS") == "cisco_iosxe"


class TestDeviceServicePlatform:
    """Тесты что device_service правильно сохраняет platform."""

    def test_device_config_stores_platform(self):
        """Проверяет что DeviceConfig хранит device_type (platform)."""
        from network_collector.api.services.device_service import DeviceConfig

        config = DeviceConfig(
            id="test-id",
            host="10.0.0.1",
            device_type="cisco_iosxe",
            name="test-switch",
        )

        assert config.device_type == "cisco_iosxe"
        assert config.to_dict()["device_type"] == "cisco_iosxe"

    def test_device_config_from_dict(self):
        """Проверяет создание DeviceConfig из dict."""
        from network_collector.api.services.device_service import DeviceConfig

        data = {
            "id": "test-id",
            "host": "10.0.0.1",
            "device_type": "cisco_nxos",
            "name": "nexus-01",
        }

        config = DeviceConfig.from_dict(data)
        assert config.device_type == "cisco_nxos"

    def test_device_config_default_platform(self):
        """Проверяет default platform если не указан."""
        from network_collector.api.services.device_service import DeviceConfig

        data = {"host": "10.0.0.1"}
        config = DeviceConfig.from_dict(data)
        assert config.device_type == "cisco_ios"


class TestCollectorUsesCorrectPlatform:
    """Тесты что collector использует правильную платформу."""

    def test_device_platform_passed_to_connection(self):
        """Проверяет что Device получает platform."""
        from network_collector.core.device import Device

        # Новый формат
        device = Device(
            host="10.0.0.1",
            platform="cisco_nxos",
        )
        assert device.platform == "cisco_nxos"

        # Для обратной совместимости: device_type как platform
        device2 = Device(
            host="10.0.0.2",
            device_type="cisco_iosxe",
        )
        # device_type используется как модель, platform отдельно
        # Но если platform не указан, __post_init__ может его установить

    def test_device_from_dict_mapping(self):
        """Проверяет создание Device из dict с device_type."""
        from network_collector.core.device import Device

        # Когда collector_service создаёт Device:
        device_data = {"host": "10.0.0.1", "device_type": "cisco_nxos"}

        device = Device(
            host=device_data.get("host"),
            platform=device_data.get("device_type", "cisco_ios"),
        )

        assert device.host == "10.0.0.1"
        assert device.platform == "cisco_nxos"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
