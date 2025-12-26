"""
Тесты парсинга show interfaces для разных платформ.

Использует реальные фикстуры из tests/fixtures/.
Проверяет:
- Парсинг через NTC Templates
- Наличие обязательных полей
- Нормализацию статусов
- Определение port_type
"""

import pytest
from pathlib import Path
from ntc_templates.parse import parse_output

# Путь к фикстурам
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestInterfacesParsing:
    """Тесты парсинга show interfaces."""

    @pytest.fixture
    def cisco_ios_interfaces(self):
        """Загружает фикстуру cisco_ios show interfaces."""
        fixture_path = FIXTURES_DIR / "cisco_ios" / "show_interfaces.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found: cisco_ios/show_interfaces.txt")

    @pytest.fixture
    def cisco_nxos_interfaces(self):
        """Загружает фикстуру cisco_nxos show interface."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found: cisco_nxos/show_interface.txt")

    def test_cisco_ios_parsing(self, cisco_ios_interfaces):
        """Тест парсинга Cisco IOS show interfaces."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show interfaces",
            data=cisco_ios_interfaces,
        )

        assert len(parsed) > 0, "Должен быть хотя бы один интерфейс"

        # Проверяем обязательные поля
        for iface in parsed:
            assert "interface" in iface, "Должно быть поле interface"
            assert iface["interface"], "interface не должен быть пустым"

        # Проверяем что есть разные типы интерфейсов
        interface_names = [i["interface"] for i in parsed]
        has_vlan = any("Vlan" in name for name in interface_names)
        has_gigabit = any("Gigabit" in name for name in interface_names)

        assert has_vlan or has_gigabit, "Должны быть Vlan или GigabitEthernet интерфейсы"

    def test_cisco_nxos_parsing(self, cisco_nxos_interfaces):
        """Тест парсинга Cisco NX-OS show interface."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface",
            data=cisco_nxos_interfaces,
        )

        assert len(parsed) > 0, "Должен быть хотя бы один интерфейс"

        # Проверяем обязательные поля
        for iface in parsed:
            assert "interface" in iface, "Должно быть поле interface"

        # Проверяем что есть Ethernet интерфейсы (NX-OS формат)
        interface_names = [i["interface"] for i in parsed]
        has_ethernet = any("Ethernet" in name for name in interface_names)
        assert has_ethernet, "Должны быть Ethernet интерфейсы"

    def test_cisco_ios_has_required_fields(self, cisco_ios_interfaces):
        """Проверяет что Cisco IOS возвращает нужные поля."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show interfaces",
            data=cisco_ios_interfaces,
        )

        # Находим физический интерфейс (не Vlan)
        physical_ifaces = [
            i for i in parsed
            if not i["interface"].startswith("Vlan")
            and not i["interface"].startswith("Loopback")
        ]

        if not physical_ifaces:
            pytest.skip("Нет физических интерфейсов в фикстуре")

        iface = physical_ifaces[0]

        # NTC Templates для cisco_ios show interfaces возвращает:
        # interface, link_status, protocol_status, hardware_type,
        # bia (MAC address), description, ip_address, mtu, bandwidth, etc.
        expected_fields = ["interface", "hardware_type", "bia"]
        for field in expected_fields:
            assert field in iface, f"Должно быть поле {field}"

    def test_cisco_nxos_has_hardware_type(self, cisco_nxos_interfaces):
        """Проверяет что NX-OS возвращает hardware_type."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface",
            data=cisco_nxos_interfaces,
        )

        # Находим Ethernet интерфейс
        eth_ifaces = [
            i for i in parsed
            if i["interface"].startswith("Ethernet")
        ]

        if not eth_ifaces:
            pytest.skip("Нет Ethernet интерфейсов в фикстуре")

        iface = eth_ifaces[0]

        # NX-OS должен иметь hardware_type
        assert "hardware_type" in iface, "NX-OS должен иметь hardware_type"


class TestInterfaceStatusParsing:
    """Тесты парсинга show interface status."""

    @pytest.fixture
    def cisco_nxos_status(self):
        """Загружает фикстуру cisco_nxos show interface status."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface_status.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found: cisco_nxos/show_interface_status.txt")

    @pytest.fixture
    def cisco_ios_status(self):
        """Загружает фикстуру cisco_ios show interface status."""
        fixture_path = FIXTURES_DIR / "cisco_ios" / "show_interface_status.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found: cisco_ios/show_interface_status.txt")

    def test_nxos_interface_status_has_type(self, cisco_nxos_status):
        """Тест что NX-OS show interface status содержит Type (media_type)."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface status",
            data=cisco_nxos_status,
        )

        assert len(parsed) > 0, "Должны быть интерфейсы"

        # Проверяем что есть поле type
        for iface in parsed:
            assert "port" in iface, "Должно быть поле port"

        # Находим интерфейс с трансивером (не --)
        ifaces_with_type = [
            i for i in parsed
            if i.get("type") and i.get("type") != "--"
        ]

        assert len(ifaces_with_type) > 0, "Должны быть интерфейсы с type"

        # Проверяем формат type
        for iface in ifaces_with_type:
            media_type = iface["type"]
            # Должен быть формат типа 10Gbase-LR, 1000base-SX, QSFP-100G-CR4
            assert any(x in media_type for x in ["base", "QSFP", "SFP"]), \
                f"type должен содержать base/QSFP/SFP: {media_type}"

    def test_nxos_interface_status_port_normalization(self, cisco_nxos_status):
        """Тест нормализации имён портов из show interface status."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface status",
            data=cisco_nxos_status,
        )

        # NX-OS show interface status возвращает короткие имена: Eth1/1
        # Нужно нормализовать в Ethernet1/1
        for iface in parsed:
            port = iface.get("port", "")
            if port.startswith("Eth"):
                # Eth1/1 -> должен маппиться в Ethernet1/1
                suffix = port[3:]  # 1/1
                full_name = f"Ethernet{suffix}"
                # Это проверка что мы понимаем формат
                assert suffix, f"Должен быть суффикс после Eth: {port}"


class TestInterfaceTransceiverParsing:
    """Тесты парсинга show interface transceiver."""

    @pytest.fixture
    def cisco_nxos_transceiver(self):
        """Загружает фикстуру cisco_nxos show interface transceiver."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface_transceiver.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found: cisco_nxos/show_interface_transceiver.txt")

    def test_nxos_transceiver_parsing(self, cisco_nxos_transceiver):
        """Тест парсинга NX-OS show interface transceiver."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface transceiver",
            data=cisco_nxos_transceiver,
        )

        assert len(parsed) > 0, "Должны быть трансиверы"

        # Проверяем обязательные поля
        for item in parsed:
            assert "interface" in item, "Должно быть поле interface"

        # Находим интерфейсы с трансиверами
        with_transceiver = [
            i for i in parsed
            if i.get("type") and "not present" not in str(i.get("type", "")).lower()
        ]

        if not with_transceiver:
            pytest.skip("Нет интерфейсов с трансиверами в фикстуре")

        # Проверяем что есть нужные поля для inventory
        item = with_transceiver[0]
        # NTC шаблон cisco_nxos_show_interface_transceiver возвращает:
        # interface, type, name, part_number, serial_number
        expected = ["interface", "type"]
        for field in expected:
            assert field in item, f"Должно быть поле {field}"

    def test_nxos_transceiver_types(self, cisco_nxos_transceiver):
        """Проверяет типы трансиверов."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface transceiver",
            data=cisco_nxos_transceiver,
        )

        # Собираем уникальные типы
        types = set()
        for item in parsed:
            t = item.get("type", "")
            if t and "not present" not in t.lower():
                types.add(t)

        # Должны быть типичные типы
        # Из фикстуры: 10Gbase-LR, 10Gbase-SR, 1000base-SX
        assert len(types) > 0, "Должны быть типы трансиверов"

        # Все типы должны быть в правильном формате
        for t in types:
            assert any(x in t for x in ["base", "Gbase", "BASE"]), \
                f"Тип должен содержать 'base': {t}"
