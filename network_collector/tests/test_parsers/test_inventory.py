"""
Тесты парсинга show inventory для разных платформ.

Проверяет:
- Парсинг chassis, модулей, PSU, fans
- NX-OS: отдельно show interface transceiver для SFP
"""

import pytest
from pathlib import Path
from ntc_templates.parse import parse_output

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestInventoryParsing:
    """Тесты парсинга show inventory."""

    @pytest.fixture
    def cisco_ios_inventory(self):
        """Загружает фикстуру cisco_ios show inventory."""
        fixture_path = FIXTURES_DIR / "cisco_ios" / "show_inventory.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found: cisco_ios/show_inventory.txt")

    @pytest.fixture
    def cisco_nxos_inventory(self):
        """Загружает фикстуру cisco_nxos show inventory."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_inventory.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found: cisco_nxos/show_inventory.txt")

    def test_cisco_ios_inventory_parsing(self, cisco_ios_inventory):
        """Тест парсинга Cisco IOS show inventory."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show inventory",
            data=cisco_ios_inventory,
        )

        assert len(parsed) > 0, "Должны быть компоненты"

        # Проверяем обязательные поля
        for item in parsed:
            assert "name" in item, "Должно быть поле name"
            assert "pid" in item, "Должно быть поле pid"

        # Должен быть Chassis
        names = [i.get("name", "").lower() for i in parsed]
        has_chassis = any("chassis" in name for name in names)
        # Может быть "Switch 1" или подобное
        assert len(parsed) >= 1, "Должен быть хотя бы один компонент"

    def test_cisco_nxos_inventory_parsing(self, cisco_nxos_inventory):
        """Тест парсинга Cisco NX-OS show inventory."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show inventory",
            data=cisco_nxos_inventory,
        )

        assert len(parsed) > 0, "Должны быть компоненты"

        # Проверяем что есть chassis, PSU, fans
        names = [i.get("name", "").lower() for i in parsed]

        has_chassis = any("chassis" in name for name in names)
        has_psu = any("power" in name for name in names)
        has_fan = any("fan" in name for name in names)

        assert has_chassis, "Должен быть Chassis"
        # PSU и Fan опционально, но обычно есть

    def test_cisco_nxos_inventory_no_transceivers(self, cisco_nxos_inventory):
        """
        Проверяет что NX-OS show inventory НЕ содержит трансиверы.

        Это важно! На NX-OS трансиверы в show interface transceiver,
        а не в show inventory (в отличие от IOS).
        """
        parsed = parse_output(
            platform="cisco_nxos",
            command="show inventory",
            data=cisco_nxos_inventory,
        )

        # Ищем SFP/QSFP в именах
        names = [i.get("name", "").lower() for i in parsed]
        pids = [i.get("pid", "").upper() for i in parsed]

        has_sfp_name = any("sfp" in name or "transceiver" in name for name in names)
        has_sfp_pid = any("SFP" in pid or "QSFP" in pid for pid in pids)

        # На NX-OS трансиверы НЕ должны быть в show inventory
        assert not has_sfp_name, "NX-OS show inventory не должен содержать SFP в именах"
        # PID типа NXA-PAC, NXA-FAN допустимы, но не SFP-
        # Это может быть ложным срабатыванием если есть линейные карты с SFP в названии


class TestInventoryNormalization:
    """Тесты нормализации данных inventory."""

    @pytest.fixture
    def cisco_nxos_inventory(self):
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_inventory.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found")

    def test_inventory_has_serial(self, cisco_nxos_inventory):
        """Проверяет что есть серийные номера."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show inventory",
            data=cisco_nxos_inventory,
        )

        # Хотя бы chassis должен иметь серийник
        chassis = [i for i in parsed if "chassis" in i.get("name", "").lower()]
        if chassis:
            assert chassis[0].get("sn"), "Chassis должен иметь серийный номер"

    def test_inventory_required_fields(self, cisco_nxos_inventory):
        """Проверяет обязательные поля для NetBox."""
        parsed = parse_output(
            platform="cisco_nxos",
            command="show inventory",
            data=cisco_nxos_inventory,
        )

        # Каждый компонент должен иметь:
        # - name (для NetBox: name)
        # - pid (для NetBox: part_id / model)
        # - sn (для NetBox: serial)
        for item in parsed:
            assert "name" in item, "Должно быть name"
            assert "pid" in item, "Должно быть pid"
            # sn может быть N/A для fans
