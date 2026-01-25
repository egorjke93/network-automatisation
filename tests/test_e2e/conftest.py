"""
E2E тесты: fixtures для коллекторов.

Предоставляет mock устройства и helper функции для тестирования
полного цикла обработки данных без реального SSH подключения.
"""

import pytest
from typing import Optional
from unittest.mock import MagicMock

from network_collector.core.device import Device


def create_mock_device(
    platform: str = "cisco_ios",
    hostname: str = "test-switch",
    host: str = "10.0.0.1",
) -> Device:
    """
    Создаёт mock Device для тестирования.

    Args:
        platform: Платформа устройства (cisco_ios, cisco_nxos, etc.)
        hostname: Имя устройства
        host: IP-адрес устройства

    Returns:
        Device: Mock объект устройства
    """
    device = MagicMock(spec=Device)
    device.platform = platform
    device.hostname = hostname
    device.host = host
    device.device_type = platform
    device.name = hostname
    return device


@pytest.fixture
def mock_device():
    """
    Fixture для создания mock устройства.

    Usage:
        def test_something(mock_device):
            device = mock_device("cisco_ios")
            # или
            device = mock_device("cisco_nxos", hostname="nxos-switch")
    """
    return create_mock_device


@pytest.fixture
def cisco_ios_device():
    """Mock Cisco IOS устройства."""
    return create_mock_device("cisco_ios", "ios-switch")


@pytest.fixture
def cisco_nxos_device():
    """Mock Cisco NX-OS устройства."""
    return create_mock_device("cisco_nxos", "nxos-switch")


@pytest.fixture
def qtech_device():
    """Mock QTech устройства."""
    return create_mock_device("qtech", "qtech-switch")


# Платформы для параметризованных тестов
SUPPORTED_PLATFORMS = [
    "cisco_ios",
    "cisco_nxos",
    "qtech",
]

# Маппинг платформы -> файлы fixtures
PLATFORM_FIXTURES = {
    "cisco_ios": {
        "interfaces": "show_interfaces.txt",
        "mac": "show_mac_address_table.txt",
        "lldp": "show_lldp_neighbors_detail.txt",
        "cdp": "show_cdp_neighbors_detail.txt",
        "inventory": "show_inventory.txt",
        "version": "show_version.txt",
        "switchport": "show_interfaces_switchport.txt",
        "interface_status": "show_interface_status.txt",
    },
    "cisco_nxos": {
        "interfaces": "show_interface.txt",
        "mac": "show_mac_address_table.txt",
        "lldp": "show_lldp_neighbors_detail.txt",
        "cdp": "show_cdp_neighbors_detail.txt",
        "inventory": "show_inventory.txt",
        "version": "show_version.txt",
        "switchport": "show_interface_switchport.txt",
        "interface_status": "show_interface_status.txt",
    },
    "qtech": {
        "interfaces": "show_interface.txt",
        "mac": "show_mac_address_table.txt",
        "lldp": "show_lldp_neighbors_detail.txt",
        "version": "show_version.txt",
        "switchport": "show_interface_switchport.txt",
        "interface_status": "show_interface_status.txt",
    },
}


@pytest.fixture
def platform_fixture_map():
    """Возвращает маппинг fixtures для платформ."""
    return PLATFORM_FIXTURES


def get_fixture_filename(platform: str, fixture_type: str) -> Optional[str]:
    """
    Получает имя файла fixture для платформы.

    Args:
        platform: Платформа (cisco_ios, cisco_nxos, etc.)
        fixture_type: Тип fixture (interfaces, mac, lldp, etc.)

    Returns:
        str: Имя файла или None если не найден
    """
    return PLATFORM_FIXTURES.get(platform, {}).get(fixture_type)
