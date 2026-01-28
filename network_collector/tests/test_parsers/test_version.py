"""
Тесты парсинга show version для разных платформ.

Использует фикстуры из tests/fixtures/ для проверки
парсинга реального вывода команд.
"""

import pytest
from ntc_templates.parse import parse_output


class TestCiscoIOSVersionParsing:
    """Тесты парсинга show version Cisco IOS/IOS-XE."""

    def test_parse_show_version(self, load_fixture):
        """Парсинг show version."""
        output = load_fixture("cisco_ios", "show_version.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_version_field(self, load_fixture):
        """Проверка поля version."""
        output = load_fixture("cisco_ios", "show_version.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        entry = result[0]
        version = entry.get("version", "")
        assert version, "version должен быть заполнен"
        assert "17.3" in version

    def test_hostname_field(self, load_fixture):
        """Проверка поля hostname."""
        output = load_fixture("cisco_ios", "show_version.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        entry = result[0]
        hostname = entry.get("hostname", "")
        assert hostname, "hostname должен быть заполнен"
        assert "SU-724" in hostname

    def test_hardware_field(self, load_fixture):
        """Проверка поля hardware (модель)."""
        output = load_fixture("cisco_ios", "show_version.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        entry = result[0]
        hardware = entry.get("hardware", [])
        assert hardware, "hardware должен быть заполнен"
        # NTC возвращает список
        if isinstance(hardware, list):
            assert "C9200L-48P-4X" in hardware[0]
        else:
            assert "C9200L" in hardware

    def test_serial_field(self, load_fixture):
        """Проверка поля serial."""
        output = load_fixture("cisco_ios", "show_version.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        entry = result[0]
        serial = entry.get("serial", [])
        assert serial, "serial должен быть заполнен"
        # NTC возвращает список
        if isinstance(serial, list):
            assert "JAE23320NQB" in serial[0]
        else:
            assert len(serial) > 5

    def test_uptime_field(self, load_fixture):
        """Проверка поля uptime."""
        output = load_fixture("cisco_ios", "show_version.txt")

        result = parse_output(
            platform="cisco_ios",
            command="show version",
            data=output,
        )

        entry = result[0]
        uptime = entry.get("uptime", "")
        assert uptime, "uptime должен быть заполнен"


class TestCiscoNXOSVersionParsing:
    """Тесты парсинга show version Cisco NX-OS."""

    def test_parse_show_version(self, load_fixture):
        """Парсинг show version."""
        output = load_fixture("cisco_nxos", "show_version.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show version",
            data=output,
        )

        assert isinstance(result, list)
        assert len(result) > 0

    def test_os_version_field(self, load_fixture):
        """Проверка поля os (версия NX-OS)."""
        output = load_fixture("cisco_nxos", "show_version.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show version",
            data=output,
        )

        entry = result[0]
        os_version = entry.get("os", "")
        assert os_version, "os должен быть заполнен"
        assert "9.3" in os_version

    def test_hostname_field(self, load_fixture):
        """Проверка поля hostname."""
        output = load_fixture("cisco_nxos", "show_version.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show version",
            data=output,
        )

        entry = result[0]
        hostname = entry.get("hostname", "")
        assert hostname, "hostname должен быть заполнен"
        assert "N9K" in hostname

    def test_platform_field(self, load_fixture):
        """Проверка поля platform (модель)."""
        output = load_fixture("cisco_nxos", "show_version.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show version",
            data=output,
        )

        entry = result[0]
        platform = entry.get("platform", "")
        assert platform, "platform должен быть заполнен"
        assert "C93180" in platform

    def test_serial_field(self, load_fixture):
        """Проверка поля serial."""
        output = load_fixture("cisco_nxos", "show_version.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show version",
            data=output,
        )

        entry = result[0]
        serial = entry.get("serial", "")
        assert serial, "serial должен быть заполнен"
        assert "FDO23210NEQ" in serial

    def test_uptime_field(self, load_fixture):
        """Проверка поля uptime."""
        output = load_fixture("cisco_nxos", "show_version.txt")

        result = parse_output(
            platform="cisco_nxos",
            command="show version",
            data=output,
        )

        entry = result[0]
        uptime = entry.get("uptime", "")
        assert uptime, "uptime должен быть заполнен"
        assert "day" in uptime
