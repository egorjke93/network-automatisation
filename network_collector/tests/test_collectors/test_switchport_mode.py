"""
Тесты для логики определения switchport mode (access/tagged/tagged-all).

Проверяет правильное определение режима порта для NetBox:
- access: порт в access mode
- tagged: trunk с ограниченным списком VLAN (10,20,30)
- tagged-all: trunk со всеми VLAN (ALL, 1-4094)

Критично для:
- Правильной синхронизации switchport mode с NetBox
- Корректного определения "полного транка" vs "частичный транк"
"""

import pytest
from ntc_templates.parse import parse_output
from network_collector.collectors.interfaces import InterfaceCollector


@pytest.fixture
def collector():
    """Создаём InterfaceCollector для тестирования."""
    return InterfaceCollector()


def make_switchport_output(interfaces: list[dict]) -> str:
    """
    Генерирует вывод show interfaces switchport из списка интерфейсов.

    Args:
        interfaces: список словарей с ключами:
            - name: имя интерфейса (Gi1/0/1)
            - admin_mode: administrative mode (static access, trunk)
            - oper_mode: operational mode (static access, trunk, down)
            - access_vlan: VLAN для access (35)
            - native_vlan: native VLAN для trunk (1)
            - trunking_vlans: список VLAN для trunk (ALL, 10,20,30)
    """
    output = ""
    for iface in interfaces:
        output += f"""
Name: {iface['name']}
Switchport: Enabled
Administrative Mode: {iface.get('admin_mode', 'static access')}
Operational Mode: {iface.get('oper_mode', iface.get('admin_mode', 'static access'))}
Administrative Trunking Encapsulation: dot1q
Negotiation of Trunking: Off
Access Mode VLAN: {iface.get('access_vlan', '1')} (VLAN)
Trunking Native Mode VLAN: {iface.get('native_vlan', '1')} (default)
Voice VLAN: none
Trunking VLANs Enabled: {iface.get('trunking_vlans', 'ALL')}
Pruning VLANs Enabled: 2-1001
"""
    return output


@pytest.mark.unit
class TestSwitchportModeLogic:
    """Тесты логики определения switchport mode через реальный парсер."""

    @pytest.mark.parametrize("admin_mode,trunking_vlans,expected_mode", [
        # === ACCESS MODE ===
        ("static access", "ALL", "access"),
        ("access", "ALL", "access"),
        ("dynamic access", "ALL", "access"),

        # === TAGGED-ALL (полный транк) ===
        ("trunk", "ALL", "tagged-all"),
        ("trunk", "all", "tagged-all"),
        ("trunk", "1-4094", "tagged-all"),
        ("trunk", "1-4093", "tagged-all"),
        ("trunk", "1-4095", "tagged-all"),
        ("dynamic desirable", "ALL", "tagged-all"),
        ("dynamic auto", "ALL", "tagged-all"),

        # === TAGGED (ограниченный транк) ===
        ("trunk", "10", "tagged"),
        ("trunk", "10,20,30", "tagged"),
        ("trunk", "10-20", "tagged"),
        ("trunk", "10-20,30,40-50", "tagged"),
        ("trunk", "1,10,20", "tagged"),
        ("trunk", "100-200", "tagged"),
        ("trunk", "2-100", "tagged"),
        ("trunk", "1-100", "tagged"),
    ])
    def test_switchport_mode_determination(
        self, collector, admin_mode, trunking_vlans, expected_mode
    ):
        """Тест определения NetBox режима через реальный парсер."""
        output = make_switchport_output([{
            "name": "Gi1/0/1",
            "admin_mode": admin_mode,
            "trunking_vlans": trunking_vlans,
        }])

        result = collector._parse_switchport_modes(output, "cisco_ios", "show interfaces switchport")

        gi1 = result.get("Gi1/0/1", result.get("GigabitEthernet1/0/1", {}))
        assert gi1.get("mode") == expected_mode, (
            f"admin_mode={admin_mode}, trunking_vlans={trunking_vlans}\n"
            f"Expected: {expected_mode}, Got: {gi1.get('mode')}"
        )

    def test_access_vlan_parsed(self, collector):
        """Access VLAN парсится корректно."""
        output = make_switchport_output([{
            "name": "Gi1/0/1",
            "admin_mode": "static access",
            "access_vlan": "35",
        }])

        result = collector._parse_switchport_modes(output, "cisco_ios", "show interfaces switchport")
        gi1 = result.get("Gi1/0/1", result.get("GigabitEthernet1/0/1", {}))

        assert gi1.get("mode") == "access"
        assert gi1.get("access_vlan") == "35"

    def test_native_vlan_parsed(self, collector):
        """Native VLAN парсится корректно."""
        output = make_switchport_output([{
            "name": "Gi1/0/1",
            "admin_mode": "trunk",
            "native_vlan": "100",
            "trunking_vlans": "ALL",
        }])

        result = collector._parse_switchport_modes(output, "cisco_ios", "show interfaces switchport")
        gi1 = result.get("Gi1/0/1", result.get("GigabitEthernet1/0/1", {}))

        assert gi1.get("mode") == "tagged-all"
        assert gi1.get("native_vlan") == "100"

    def test_port_down_uses_admin_mode(self, collector):
        """Порт down использует admin_mode, не operational mode."""
        output = make_switchport_output([{
            "name": "Gi0/2",
            "admin_mode": "static access",
            "oper_mode": "down",  # Порт физически down
            "access_vlan": "41",
        }])

        result = collector._parse_switchport_modes(output, "cisco_ios", "show interfaces switchport")
        gi02 = result.get("Gi0/2", result.get("GigabitEthernet0/2", {}))

        # Должен быть access (по admin_mode), не пустой (по oper_mode=down)
        assert gi02.get("mode") == "access", f"Порт down должен использовать admin_mode, получили {gi02}"
        assert gi02.get("access_vlan") == "41"

    def test_interface_name_variants(self, collector):
        """Создаются альтернативные имена интерфейсов (Gi -> GigabitEthernet)."""
        output = make_switchport_output([{
            "name": "Gi1/0/1",
            "admin_mode": "static access",
        }])

        result = collector._parse_switchport_modes(output, "cisco_ios", "show interfaces switchport")

        # Должны быть оба варианта
        assert "Gi1/0/1" in result
        assert "GigabitEthernet1/0/1" in result

    def test_multiple_interfaces(self, collector):
        """Парсинг нескольких интерфейсов одновременно."""
        output = make_switchport_output([
            {"name": "Gi1/0/1", "admin_mode": "static access", "access_vlan": "10"},
            {"name": "Gi1/0/2", "admin_mode": "trunk", "trunking_vlans": "ALL"},
            {"name": "Gi1/0/3", "admin_mode": "trunk", "trunking_vlans": "20,30,40"},
        ])

        result = collector._parse_switchport_modes(output, "cisco_ios", "show interfaces switchport")

        gi1 = result.get("Gi1/0/1", {})
        gi2 = result.get("Gi1/0/2", {})
        gi3 = result.get("Gi1/0/3", {})

        assert gi1.get("mode") == "access"
        assert gi2.get("mode") == "tagged-all"
        assert gi3.get("mode") == "tagged"


@pytest.mark.unit
class TestNTCParsingIntegration:
    """
    Тесты с реальным NTC парсингом.

    Проверяют что код корректно обрабатывает особенности NTC templates:
    - trunking_vlans как список
    - admin_mode vs mode (operational)
    """

    # Реальный вывод show interfaces switchport (Cisco IOS)
    SWITCHPORT_OUTPUT_IOS = """
Name: Gi1/0/1
Switchport: Enabled
Administrative Mode: static access
Operational Mode: static access
Administrative Trunking Encapsulation: dot1q
Operational Trunking Encapsulation: native
Negotiation of Trunking: Off
Access Mode VLAN: 35 (VLAN0035)
Trunking Native Mode VLAN: 1 (default)
Voice VLAN: none
Trunking VLANs Enabled: ALL
Pruning VLANs Enabled: 2-1001

Name: Te1/1/1
Switchport: Enabled
Administrative Mode: trunk
Operational Mode: trunk
Administrative Trunking Encapsulation: dot1q
Operational Trunking Encapsulation: dot1q
Negotiation of Trunking: On
Access Mode VLAN: 1 (default)
Trunking Native Mode VLAN: 1 (default)
Voice VLAN: none
Trunking VLANs Enabled: ALL
Pruning VLANs Enabled: 2-1001

Name: Gi0/2
Switchport: Enabled
Administrative Mode: static access
Operational Mode: down
Administrative Trunking Encapsulation: dot1q
Negotiation of Trunking: Off
Access Mode VLAN: 41 (VLAN0041)
Trunking Native Mode VLAN: 1 (default)
Voice VLAN: none
Trunking VLANs Enabled: ALL
Pruning VLANs Enabled: 2-1001

Name: Gi0/10
Switchport: Enabled
Administrative Mode: trunk
Operational Mode: trunk
Administrative Trunking Encapsulation: dot1q
Operational Trunking Encapsulation: dot1q
Negotiation of Trunking: On
Access Mode VLAN: 1 (default)
Trunking Native Mode VLAN: 100 (MGMT)
Voice VLAN: none
Trunking VLANs Enabled: 10,20,30,100
Pruning VLANs Enabled: 2-1001
"""

    def test_ntc_returns_list_for_trunking_vlans(self):
        """
        NTC templates возвращает trunking_vlans как список.

        Ключевой тест - раньше код падал из-за .lower() на списке.
        """
        parsed = parse_output(
            platform="cisco_ios",
            command="show interfaces switchport",
            data=self.SWITCHPORT_OUTPUT_IOS
        )

        for row in parsed:
            vlans = row.get("trunking_vlans")
            assert isinstance(vlans, list), (
                f"trunking_vlans должен быть list, получили {type(vlans).__name__}: {vlans}"
            )

    def test_ntc_admin_mode_vs_operational_mode(self):
        """NTC парсит и admin_mode и mode (operational) отдельно."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show interfaces switchport",
            data=self.SWITCHPORT_OUTPUT_IOS
        )

        gi02 = next((r for r in parsed if r["interface"] == "Gi0/2"), None)
        assert gi02 is not None

        assert gi02["mode"] == "down", "Operational mode должен быть 'down'"
        assert gi02["admin_mode"] == "static access", "Admin mode должен быть 'static access'"

    def test_full_integration(self, collector):
        """Полная интеграция: реальный вывод -> NTC -> наш код -> правильный результат."""
        result = collector._parse_switchport_modes(
            self.SWITCHPORT_OUTPUT_IOS,
            "cisco_ios",
            "show interfaces switchport"
        )

        # Access
        gi1 = result.get("Gi1/0/1", result.get("GigabitEthernet1/0/1", {}))
        assert gi1.get("mode") == "access"
        assert gi1.get("access_vlan") == "35"

        # Trunk ALL
        te1 = result.get("Te1/1/1", result.get("TenGigabitEthernet1/1/1", {}))
        assert te1.get("mode") == "tagged-all"

        # Port down (должен использовать admin_mode)
        gi02 = result.get("Gi0/2", result.get("GigabitEthernet0/2", {}))
        assert gi02.get("mode") == "access"
        assert gi02.get("access_vlan") == "41"

        # Trunk с конкретными VLAN
        gi10 = result.get("Gi0/10", result.get("GigabitEthernet0/10", {}))
        assert gi10.get("mode") == "tagged"
        assert gi10.get("native_vlan") == "100"
