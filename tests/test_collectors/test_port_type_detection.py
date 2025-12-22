"""
Тесты для _detect_port_type() - нормализация типа порта в коллекторе.

Проверяет что данные с разных платформ нормализуются в единый формат:
- "10g-sfp+", "1g-rj45", "25g-sfp28", "lag", "virtual" и т.д.

Критично для:
- Единообразия данных с разных платформ
- Правильной синхронизации с NetBox
"""

import pytest
from network_collector.collectors.interfaces import InterfaceCollector


@pytest.fixture
def collector():
    """Создаём InterfaceCollector для тестирования."""
    return InterfaceCollector()


@pytest.mark.unit
class TestPortTypeDetection:
    """Тесты определения port_type в коллекторе."""

    @pytest.mark.parametrize("interface_data,expected_port_type", [
        # === ПРОБЛЕМА 1 ИЗ ПРОДА ===
        # 25G порт с 10G трансивером - media_type важнее hardware_type
        (
            {
                "interface": "TwentyFiveGigE1/0/1",
                "hardware_type": "Twenty Five Gigabit Ethernet",
                "media_type": "SFP-10GBase-LR",
            },
            "10g-sfp+",  # По media_type, не по hardware_type!
        ),

        # === MEDIA_TYPE - высший приоритет ===
        (
            {
                "interface": "Ethernet1/1",
                "hardware_type": "100/1000/10000 Ethernet",
                "media_type": "10GBase-SR",
            },
            "10g-sfp+",
        ),
        (
            {
                "interface": "GigabitEthernet1/0/1",
                "hardware_type": "Gigabit Ethernet",
                "media_type": "SFP-1000Base-SX",
            },
            "1g-sfp",
        ),
        (
            {
                "interface": "GigabitEthernet1/0/2",
                "hardware_type": "Gigabit Ethernet",
                "media_type": "RJ45",
            },
            "1g-rj45",
        ),
        (
            {
                "interface": "Ethernet1/1",
                "hardware_type": "Ethernet",
                "media_type": "QSFP-40G-SR4",
            },
            "40g-qsfp",
        ),
        (
            {
                "interface": "Ethernet1/1",
                "hardware_type": "Ethernet",
                "media_type": "QSFP-100G-SR4",
            },
            "100g-qsfp28",
        ),

        # === HARDWARE_TYPE - если media_type пустой ===
        (
            {
                "interface": "TenGigabitEthernet1/1/1",
                "hardware_type": "Ten Gigabit Ethernet",
                "media_type": "",
            },
            "10g-sfp+",
        ),
        (
            {
                "interface": "TwentyFiveGigE1/0/1",
                "hardware_type": "Twenty Five Gigabit Ethernet",
                "media_type": "",
            },
            "25g-sfp28",
        ),
        (
            {
                "interface": "GigabitEthernet1/0/1",
                "hardware_type": "Gigabit Ethernet",
                "media_type": "",
            },
            "1g-rj45",  # По умолчанию copper для GigE
        ),
        # NX-OS: порт с несколькими скоростями
        (
            {
                "interface": "Ethernet1/1",
                "hardware_type": "100/1000/10000 Ethernet",
                "media_type": "",
            },
            "10g-sfp+",  # Максимальная скорость
        ),

        # === ИМЕНА ИНТЕРФЕЙСОВ - fallback ===
        # LAG интерфейсы
        (
            {
                "interface": "Port-channel1",
                "hardware_type": "EtherChannel",
                "media_type": "",
            },
            "lag",
        ),
        (
            {
                "interface": "Po1",
                "hardware_type": "",
                "media_type": "",
            },
            "lag",
        ),

        # Виртуальные интерфейсы
        (
            {
                "interface": "Vlan100",
                "hardware_type": "Ethernet SVI",
                "media_type": "",
            },
            "virtual",
        ),
        (
            {
                "interface": "Loopback0",
                "hardware_type": "",
                "media_type": "",
            },
            "virtual",
        ),
        (
            {
                "interface": "Null0",
                "hardware_type": "",
                "media_type": "",
            },
            "virtual",
        ),

        # Management интерфейсы
        (
            {
                "interface": "mgmt0",
                "hardware_type": "Ethernet",
                "media_type": "",
            },
            "1g-rj45",
        ),

        # По имени интерфейса (IOS/IOS-XE)
        (
            {
                "interface": "HundredGigE1/0/1",
                "hardware_type": "",
                "media_type": "",
            },
            "100g-qsfp28",
        ),
        (
            {
                "interface": "FortyGigabitEthernet1/1/1",
                "hardware_type": "",
                "media_type": "",
            },
            "40g-qsfp",
        ),
        (
            {
                "interface": "TwentyFiveGigE1/0/1",
                "hardware_type": "",
                "media_type": "",
            },
            "25g-sfp28",
        ),
        (
            {
                "interface": "TenGigabitEthernet1/0/1",
                "hardware_type": "",
                "media_type": "",
            },
            "10g-sfp+",
        ),
        # Короткий формат Te1/1
        (
            {
                "interface": "Te1/1/1",
                "hardware_type": "",
                "media_type": "",
            },
            "10g-sfp+",
        ),
        (
            {
                "interface": "GigabitEthernet1/0/1",
                "hardware_type": "",
                "media_type": "",
            },
            "1g-rj45",
        ),
        (
            {
                "interface": "FastEthernet0/1",
                "hardware_type": "",
                "media_type": "",
            },
            "100m-rj45",
        ),

        # === EDGE CASES ===
        # media_type = "unknown" - игнорируется
        (
            {
                "interface": "TenGigabitEthernet1/1/1",
                "hardware_type": "Ten Gigabit Ethernet",
                "media_type": "unknown",
            },
            "10g-sfp+",  # Используем hardware_type
        ),
        # media_type = "not present" - игнорируется
        (
            {
                "interface": "GigabitEthernet1/0/24",
                "hardware_type": "Gigabit Ethernet",
                "media_type": "not present",
            },
            "1g-rj45",  # Используем hardware_type
        ),
        # SFP в hardware_type - это SFP порт, не copper
        (
            {
                "interface": "GigabitEthernet1/0/24",
                "hardware_type": "Gigabit Ethernet SFP",
                "media_type": "",
            },
            "1g-sfp",  # SFP, не RJ45
        ),
    ])
    def test_detect_port_type(self, collector, interface_data, expected_port_type):
        """
        Тест определения port_type на основе данных интерфейса.

        Проверяет приоритет:
        1. Имя интерфейса (LAG, Virtual, Management)
        2. media_type (если присутствует трансивер)
        3. hardware_type (максимальная скорость порта)
        4. Имя интерфейса (IOS формат)
        """
        iface_lower = interface_data["interface"].lower()
        result = collector._detect_port_type(interface_data, iface_lower)

        assert result == expected_port_type, (
            f"Interface: {interface_data['interface']}\n"
            f"Hardware: {interface_data.get('hardware_type', '')}\n"
            f"Media: {interface_data.get('media_type', '')}\n"
            f"Expected: {expected_port_type}, Got: {result}"
        )

    def test_production_bug_25g_port_with_10g_sfp(self, collector, sample_interface_data):
        """
        Регрессионный тест для Проблемы 1 из прода.

        C9500-48Y4C: 25G порт с 10G трансивером.
        Должен определяться как "10g-sfp+" (по трансиверу), не "25g-sfp28" (по порту).
        """
        data = sample_interface_data["c9500_25g_with_10g_sfp"]
        iface_lower = data["interface"].lower()

        result = collector._detect_port_type(data, iface_lower)

        assert result == "10g-sfp+", (
            f"Проблема 1 из прода: 25G порт с 10G SFP-10GBase-LR\n"
            f"media_type должен иметь приоритет над hardware_type!\n"
            f"Expected: '10g-sfp+', Got: '{result}'"
        )

    def test_empty_data(self, collector):
        """Тест с пустыми данными."""
        data = {"interface": "Ethernet1/1", "hardware_type": "", "media_type": ""}
        result = collector._detect_port_type(data, "ethernet1/1")

        # Не удалось определить тип
        assert result == ""

    def test_case_insensitivity(self, collector):
        """Тест что поиск не зависит от регистра."""
        # Media type в разных регистрах
        data1 = {"interface": "Eth1/1", "hardware_type": "", "media_type": "SFP-10GBase-LR"}
        data2 = {"interface": "Eth1/1", "hardware_type": "", "media_type": "sfp-10gbase-lr"}
        data3 = {"interface": "Eth1/1", "hardware_type": "", "media_type": "SFP-10GBASE-LR"}

        result1 = collector._detect_port_type(data1, "eth1/1")
        result2 = collector._detect_port_type(data2, "eth1/1")
        result3 = collector._detect_port_type(data3, "eth1/1")

        assert result1 == result2 == result3 == "10g-sfp+"
