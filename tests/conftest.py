"""
Pytest configuration и общие fixtures для тестов.

Предоставляет переиспользуемые fixtures:
- load_fixture: Загрузка тестовых данных из файлов
- mock_netbox_client: Mock NetBox клиента
- sample_interface_data: Примеры данных интерфейсов
"""

import pytest
from pathlib import Path
from typing import Dict, Any
from unittest.mock import MagicMock


@pytest.fixture
def fixtures_dir() -> Path:
    """Возвращает путь к директории fixtures."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture(fixtures_dir):
    """
    Fixture для загрузки тестовых данных из файлов.

    Usage:
        output = load_fixture("cisco_ios", "show_etherchannel_summary.txt")

    Args:
        platform: Платформа (cisco_ios, cisco_nxos, arista_eos)
        filename: Имя файла с данными

    Returns:
        str: Содержимое файла
    """
    def _load(platform: str, filename: str) -> str:
        fixture_path = fixtures_dir / platform / filename
        if not fixture_path.exists():
            pytest.skip(f"Fixture не найден: {fixture_path}")
        return fixture_path.read_text(encoding="utf-8")
    return _load


@pytest.fixture
def mock_netbox_client():
    """
    Mock NetBox клиента для тестирования синхронизации.

    Returns:
        MagicMock: Мок объект с базовыми методами NetBox API
    """
    client = MagicMock()

    # Настраиваем базовые методы
    client.get_device_by_name.return_value = None
    client.get_device_type_by_model.return_value = None
    client.create_device.return_value = MagicMock(id=1, name="test-device")
    client.get_interfaces.return_value = []

    return client


@pytest.fixture
def sample_interface_data() -> Dict[str, Any]:
    """
    Примеры данных интерфейсов для тестирования.

    Returns:
        Dict: Словарь с примерами данных интерфейсов
    """
    return {
        # 25G порт с 10G трансивером (Проблема 1 из прода)
        "c9500_25g_with_10g_sfp": {
            "interface": "TwentyFiveGigE1/0/1",
            "status": "up",
            "hardware_type": "Twenty Five Gigabit Ethernet",
            "media_type": "SFP-10GBase-LR",
            "mac": "689e.0b1e.7d21",
            "speed": "10000000 Kbit",
        },
        # 10G порт с 10G трансивером
        "standard_10g_sfp": {
            "interface": "TenGigabitEthernet1/1/1",
            "status": "up",
            "hardware_type": "Ten Gigabit Ethernet",
            "media_type": "SFP-10GBase-SR",
            "speed": "10000000 Kbit",
        },
        # 1G copper порт
        "gigabit_copper": {
            "interface": "GigabitEthernet1/0/1",
            "status": "up",
            "hardware_type": "Gigabit Ethernet",
            "media_type": "RJ45",
            "speed": "1000000 Kbit",
        },
        # 1G SFP порт
        "gigabit_sfp": {
            "interface": "GigabitEthernet1/0/24",
            "status": "up",
            "hardware_type": "Gigabit Ethernet",
            "media_type": "SFP-1000Base-SX",
            "speed": "1000000 Kbit",
        },
        # Port-channel (LAG)
        "port_channel": {
            "interface": "Port-channel1",
            "status": "up",
            "hardware_type": "EtherChannel",
            "media_type": "",
        },
        # VLAN (virtual)
        "vlan_interface": {
            "interface": "Vlan100",
            "status": "up",
            "hardware_type": "Ethernet SVI",
            "media_type": "",
            "ip_address": "10.0.0.1",
            "prefix": "24",
        },
        # NX-OS: Ethernet с несколькими скоростями
        "nxos_ethernet": {
            "interface": "Ethernet1/1",
            "status": "up",
            "hardware_type": "100/1000/10000 Ethernet",  # Поддерживает до 10G
            "media_type": "10GBase-SR",
            "speed": "10000000 Kbit",
        },
    }


@pytest.fixture
def sample_switchport_data() -> Dict[str, Dict[str, Any]]:
    """
    Примеры данных switchport для тестирования mode (tagged vs tagged-all).

    Returns:
        Dict: Словарь с примерами switchport данных
    """
    return {
        "trunk_all_vlans": {
            "interface": "GigabitEthernet1/0/1",
            "switchport_mode": "trunk",
            "access_vlan": "1",
            "trunk_vlans": "ALL",
        },
        "trunk_1_4094": {
            "interface": "GigabitEthernet1/0/2",
            "switchport_mode": "trunk",
            "access_vlan": "1",
            "trunk_vlans": "1-4094",
        },
        "trunk_specific_vlans": {
            "interface": "GigabitEthernet1/0/3",
            "switchport_mode": "trunk",
            "access_vlan": "1",
            "trunk_vlans": "10,20,30",
        },
        "trunk_range_vlans": {
            "interface": "GigabitEthernet1/0/4",
            "switchport_mode": "trunk",
            "access_vlan": "1",
            "trunk_vlans": "10-20,30,40-50",
        },
        "access_mode": {
            "interface": "GigabitEthernet1/0/5",
            "switchport_mode": "access",
            "access_vlan": "100",
            "trunk_vlans": "",
        },
        "trunk_single_vlan": {
            "interface": "GigabitEthernet1/0/6",
            "switchport_mode": "trunk",
            "access_vlan": "1",
            "trunk_vlans": "100",
        },
    }


@pytest.fixture
def expected_fields() -> Dict[str, list]:
    """
    Обязательные поля для каждого типа собираемых данных.

    Используется для проверки единообразия вывода с разных платформ.

    Returns:
        Dict: Словарь с обязательными полями для каждого типа данных
    """
    return {
        "interfaces": [
            "interface",
            "status",
            "description",
            "mac",
            "ip_address",
            "mode",  # access/tagged/tagged-all
        ],
        "mac": [
            "mac",
            "vlan",
            "interface",
            "type",  # dynamic/static
        ],
        "lldp": [
            "local_interface",
            "remote_hostname",
            "remote_port",
            "neighbor_type",  # hostname/mac/ip/unknown
        ],
        "inventory": [
            "name",
            "part_id",
            "serial",
            "description",
        ],
        "lag": [
            "interface",  # Po1
            "members",    # [Gi0/1, Gi0/2]
            "protocol",   # LACP/PAgP/Static
        ],
    }


# Маркеры для группировки тестов
def pytest_configure(config):
    """Регистрация custom markers для pytest."""
    config.addinivalue_line(
        "markers", "unit: Unit tests (быстрые, без внешних зависимостей)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests (требуют fixtures)"
    )
    config.addinivalue_line(
        "markers", "netbox: NetBox sync tests (требуют mock NetBox API)"
    )
    config.addinivalue_line(
        "markers", "slow: Медленные тесты"
    )
