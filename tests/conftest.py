"""
Pytest configuration и общие fixtures для тестов.

Предоставляет переиспользуемые fixtures:
- load_fixture: Загрузка тестовых данных из файлов
- mock_netbox_client: Mock NetBox клиента
- sample_interface_data: Примеры данных интерфейсов (продовые кейсы)
"""

import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH для импортов типа network_collector.*
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest
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
        "markers", "api: API endpoint tests (FastAPI TestClient)"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests (полный цикл коллектор → нормализация)"
    )
