"""
Тесты для get_netbox_interface_type() - маппинг в NetBox interface types.

Проверяет конвертацию наших нормализованных данных в типы NetBox API.

Критично для:
- Правильной синхронизации интерфейсов с NetBox
- Исправления продовых багов (SFP-10GBase-LR → 10gbase-lr)
"""

import pytest

from network_collector.core.constants import get_netbox_interface_type


def _parse_speed(speed_str: str) -> int:
    """Конвертирует строку скорости в Mbps для тестов.

    Примеры:
        "1000000 Kbit" → 1000
        "10000000 Kbit" → 10000
    """
    if not speed_str:
        return 0
    speed_str = speed_str.lower().strip()
    if "kbit" in speed_str:
        kbit = int(speed_str.replace("kbit", "").strip())
        return kbit // 1000  # Kbit → Mbps
    return 0


def _call_interface_type(data: dict) -> str:
    """Обёртка для вызова get_netbox_interface_type из dict."""
    return get_netbox_interface_type(
        interface_name=data.get("interface", ""),
        media_type=data.get("media_type", ""),
        hardware_type=data.get("hardware_type", ""),
        port_type=data.get("port_type", ""),
        speed_mbps=_parse_speed(data.get("speed", "")),
    )


@pytest.mark.netbox
@pytest.mark.unit
class TestInterfaceTypeMapping:
    """Тесты маппинга типов интерфейсов для NetBox."""

    @pytest.mark.parametrize("interface_data, expected_netbox_type", [
        # === ПРОБЛЕМА 1 ИЗ ПРОДА ===
        # media_type должен иметь ВЫСШИЙ приоритет
        (
            {
                "interface": "TwentyFiveGigE1/0/1",
                "media_type": "SFP-10GBase-LR",
                "port_type": "10g-sfp+",
                "hardware_type": "Twenty Five Gigabit Ethernet",
            },
            "10gbase-lr",  # По media_type, не по port_type или hardware_type!
        ),

        # === MEDIA_TYPE - ВЫСШИЙ ПРИОРИТЕТ ===
        # 10G оптика
        ({"media_type": "SFP-10GBase-SR"}, "10gbase-sr"),
        ({"media_type": "SFP-10GBase-LR"}, "10gbase-lr"),
        ({"media_type": "SFP-10GBase-LRM"}, "10gbase-lrm"),
        ({"media_type": "SFP-10GBase-ER"}, "10gbase-er"),
        ({"media_type": "SFP-10GBase-ZR"}, "10gbase-zr"),
        ({"media_type": "10GBase-SR"}, "10gbase-sr"),
        ({"media_type": "10GBase-LR"}, "10gbase-lr"),

        # 1G оптика
        ({"media_type": "SFP-1000Base-SX"}, "1000base-sx"),
        ({"media_type": "SFP-1000Base-LX"}, "1000base-lx"),
        ({"media_type": "1000Base-SX"}, "1000base-sx"),

        # 25G оптика
        ({"media_type": "SFP-25GBase-SR"}, "25gbase-sr"),  # Конкретный тип оптики
        ({"media_type": "25GBase-SR"}, "25gbase-sr"),

        # 40G оптика - SR4 это конкретный тип (IEEE 802.3ba)
        ({"media_type": "QSFP-40G-SR4"}, "40gbase-sr4"),
        ({"media_type": "40GBase-SR4"}, "40gbase-sr4"),

        # 100G оптика - SR4 это конкретный тип (IEEE 802.3bm)
        ({"media_type": "QSFP-100G-SR4"}, "100gbase-sr4"),
        ({"media_type": "100GBase-SR4"}, "100gbase-sr4"),

        # Copper
        ({"media_type": "RJ45"}, "1000base-t"),
        ({"media_type": "1000Base-T"}, "1000base-t"),
        ({"media_type": "10GBase-T"}, "10gbase-t"),

        # === PORT_TYPE - если media_type пустой ===
        ({"media_type": "", "port_type": "100g-qsfp28"}, "100gbase-x-qsfp28"),
        ({"media_type": "", "port_type": "40g-qsfp"}, "40gbase-x-qsfpp"),
        ({"media_type": "", "port_type": "25g-sfp28"}, "25gbase-x-sfp28"),
        ({"media_type": "", "port_type": "10g-sfp+"}, "10gbase-x-sfpp"),
        ({"media_type": "", "port_type": "1g-sfp"}, "1000base-x-sfp"),
        ({"media_type": "", "port_type": "1g-rj45"}, "1000base-t"),
        ({"media_type": "", "port_type": "100m-rj45"}, "100base-tx"),
        ({"media_type": "", "port_type": "lag"}, "lag"),
        ({"media_type": "", "port_type": "virtual"}, "virtual"),

        # === HARDWARE_TYPE - fallback если media и port пустые ===
        (
            {"media_type": "", "port_type": "", "hardware_type": "Hundred Gigabit Ethernet"},
            "100gbase-x-qsfp28",
        ),
        (
            {"media_type": "", "port_type": "", "hardware_type": "Forty Gigabit Ethernet"},
            "40gbase-x-qsfpp",
        ),
        (
            {"media_type": "", "port_type": "", "hardware_type": "Twenty Five Gigabit Ethernet"},
            "25gbase-x-sfp28",
        ),
        (
            {"media_type": "", "port_type": "", "hardware_type": "Ten Gigabit Ethernet"},
            "10gbase-x-sfpp",
        ),
        (
            {"media_type": "", "port_type": "", "hardware_type": "Gigabit Ethernet"},
            "1000base-t",
        ),
        (
            {"media_type": "", "port_type": "", "hardware_type": "Fast Ethernet"},
            "100base-tx",
        ),

        # NX-OS: множественные скорости
        (
            {"media_type": "", "port_type": "", "hardware_type": "100/1000/10000 Ethernet"},
            "10gbase-x-sfpp",  # Максимальная скорость
        ),

        # === SPEED + INTERFACE - последний fallback ===
        (
            {
                "media_type": "",
                "port_type": "",
                "hardware_type": "",
                "speed": "100000000 Kbit",
                "interface": "HundredGigE1/0/1",
            },
            "100gbase-x-qsfp28",
        ),
        (
            {
                "media_type": "",
                "port_type": "",
                "hardware_type": "",
                "speed": "40000000 Kbit",
                "interface": "FortyGigE1/0/1",
            },
            "40gbase-x-qsfpp",
        ),
        (
            {
                "media_type": "",
                "port_type": "",
                "hardware_type": "",
                "speed": "25000000 Kbit",
                "interface": "TwentyFiveGigE1/0/1",
            },
            "25gbase-x-sfp28",
        ),
        (
            {
                "media_type": "",
                "port_type": "",
                "hardware_type": "",
                "speed": "10000000 Kbit",
                "interface": "TenGigE1/0/1",
            },
            "10gbase-x-sfpp",
        ),
        (
            {
                "media_type": "",
                "port_type": "",
                "hardware_type": "",
                "speed": "1000000 Kbit",
                "interface": "GigE1/0/1",
            },
            "1000base-t",
        ),

        # === EDGE CASES ===
        # media_type = "unknown" - игнорируется, используем port_type
        (
            {"media_type": "unknown", "port_type": "10g-sfp+"},
            "10gbase-x-sfpp",
        ),
        # media_type = "not present" - игнорируется
        (
            {"media_type": "not present", "port_type": "1g-rj45"},
            "1000base-t",
        ),
        # media_type = "" - используем port_type
        (
            {"media_type": "", "port_type": "25g-sfp28"},
            "25gbase-x-sfp28",
        ),
        # Все поля пустые - дефолт 1000base-t (самый распространённый тип)
        (
            {"media_type": "", "port_type": "", "hardware_type": "", "speed": ""},
            "1000base-t",  # Дефолт из конфига
        ),
    ])
    def test_get_interface_type(self, interface_data, expected_netbox_type):
        """
        Тест маппинга типа интерфейса в NetBox тип.

        Проверяет приоритет:
        1. media_type (конкретный трансивер) - ВЫСШИЙ ПРИОРИТЕТ
        2. port_type (наш нормализованный тип)
        3. hardware_type (максимальная скорость порта)
        4. speed + interface name (fallback)
        """
        result = _call_interface_type(interface_data)

        assert result == expected_netbox_type, (
            f"Interface: {interface_data.get('interface', 'N/A')}\n"
            f"Media Type: {interface_data.get('media_type', 'N/A')}\n"
            f"Port Type: {interface_data.get('port_type', 'N/A')}\n"
            f"Hardware: {interface_data.get('hardware_type', 'N/A')}\n"
            f"Expected: {expected_netbox_type}, Got: {result}"
        )

    def test_production_bug_media_type_priority(self, sample_interface_data):
        """
        Регрессионный тест для Проблемы 1 из прода.

        C9500-48Y4C: TwentyFiveGigE1/0/1 с SFP-10GBase-LR трансивером.
        До фикса: определялся как "10gbase-x-sfpp" (по port_type)
        После фикса: должен быть "10gbase-lr" (по media_type)
        """
        data = sample_interface_data["c9500_25g_with_10g_sfp"]

        result = _call_interface_type(data)

        assert result == "10gbase-lr", (
            f"Проблема 1 из прода: 25G порт с 10G SFP-10GBase-LR\n"
            f"media_type='SFP-10GBase-LR' должен иметь приоритет!\n"
            f"Expected: '10gbase-lr', Got: '{result}'\n"
            f"Data: {data}"
        )

    def test_media_type_case_insensitive(self):
        """Тест что поиск media_type не зависит от регистра."""
        test_cases = [
            {"media_type": "SFP-10GBase-LR"},
            {"media_type": "sfp-10gbase-lr"},
            {"media_type": "SFP-10GBASE-LR"},
            {"media_type": "Sfp-10GbAsE-Lr"},
        ]

        for data in test_cases:
            result = _call_interface_type(data)
            assert result == "10gbase-lr", f"Failed for media_type: {data['media_type']}"

    def test_priority_media_over_port_type(self):
        """
        Тест что media_type имеет приоритет над port_type.

        Сценарий: 25G порт (port_type="25g-sfp28") с 10G трансивером (media_type="SFP-10GBase-SR").
        Результат должен быть "10gbase-sr" (по трансиверу), не "25gbase-x-sfp28" (по порту).
        """
        data = {
            "media_type": "SFP-10GBase-SR",
            "port_type": "25g-sfp28",
            "hardware_type": "Twenty Five Gigabit Ethernet",
        }

        result = _call_interface_type(data)

        assert result == "10gbase-sr", (
            "media_type должен иметь приоритет над port_type!\n"
            f"Expected: '10gbase-sr', Got: '{result}'"
        )

    def test_priority_port_type_over_hardware(self):
        """
        Тест что port_type имеет приоритет над hardware_type.
        """
        data = {
            "media_type": "",
            "port_type": "10g-sfp+",
            "hardware_type": "Twenty Five Gigabit Ethernet",
        }

        result = _call_interface_type(data)

        assert result == "10gbase-x-sfpp", (
            "port_type должен иметь приоритет над hardware_type!\n"
            f"Expected: '10gbase-x-sfpp', Got: '{result}'"
        )

    def test_lag_interface(self):
        """Тест что LAG интерфейсы определяются как 'lag'."""
        data = {"port_type": "lag"}
        result = _call_interface_type(data)
        assert result == "lag"

    def test_virtual_interface(self):
        """Тест что виртуальные интерфейсы определяются как 'virtual'."""
        data = {"port_type": "virtual"}
        result = _call_interface_type(data)
        assert result == "virtual"

    def test_empty_data_returns_default(self):
        """Тест что пустые данные возвращают дефолтный тип."""
        data = {}
        result = _call_interface_type(data)
        assert result == "1000base-t"  # Дефолт из конфига (самый распространённый тип)

    def test_unknown_media_type_fallback_to_port_type(self):
        """
        Тест что неизвестный media_type игнорируется и используется port_type.
        """
        data = {
            "media_type": "unknown",
            "port_type": "1g-rj45",
        }

        result = _call_interface_type(data)

        assert result == "1000base-t", (
            "media_type='unknown' должен игнорироваться!\n"
            f"Expected: '1000base-t', Got: '{result}'"
        )

    def test_not_present_media_type_fallback(self):
        """
        Тест что media_type='not present' игнорируется.
        """
        data = {
            "media_type": "not present",
            "port_type": "10g-sfp+",
        }

        result = _call_interface_type(data)

        assert result == "10gbase-x-sfpp", (
            "media_type='not present' должен игнорироваться!\n"
            f"Expected: '10gbase-x-sfpp', Got: '{result}'"
        )


class TestQtechInterfaceTypeMapping:
    """Тесты get_netbox_interface_type для QTech интерфейсов."""

    @pytest.mark.parametrize("interface_name,expected", [
        # AggregatePort → LAG
        ("AggregatePort 1", "lag"),
        ("AggregatePort 100", "lag"),
        ("Ag1", "lag"),
        ("Ag10", "lag"),
        # TFGigabitEthernet → 10G SFP+
        ("TFGigabitEthernet 0/1", "10gbase-x-sfpp"),
        ("TF0/1", "10gbase-x-sfpp"),
        ("TF0/48", "10gbase-x-sfpp"),
        # HundredGigabitEthernet → 100G
        ("HundredGigabitEthernet 0/55", "100gbase-x-qsfp28"),
        ("Hu0/55", "100gbase-x-qsfp28"),
    ])
    def test_qtech_interface_types(self, interface_name, expected):
        """QTech интерфейсы правильно маппятся в NetBox типы."""
        result = get_netbox_interface_type(interface_name=interface_name)
        assert result == expected, (
            f"Interface: {interface_name}\n"
            f"Expected: {expected}, Got: {result}"
        )
