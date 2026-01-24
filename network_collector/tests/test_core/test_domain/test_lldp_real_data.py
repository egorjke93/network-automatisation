"""
Тесты LLDP/CDP нормализации с РЕАЛЬНЫМИ данными с устройств.

Эти тесты используют реальный вывод команд, а не мокированные данные.
Ловят edge cases которые не видны в упрощённых тестах:
- Port id: 0 (число, не интерфейс)
- Port id: MAC-адрес
- Port Description: hostname вместо интерфейса
- neighbor_port_id из TextFSM
"""

import pytest
from pathlib import Path

from ntc_templates.parse import parse_output

from network_collector.core.domain.lldp import LLDPNormalizer


FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "real_output"


def load_real_fixture(filename: str) -> str:
    """Загружает реальный вывод команды."""
    filepath = FIXTURES_DIR / filename
    if not filepath.exists():
        pytest.skip(f"Fixture not found: {filepath}")
    content = filepath.read_text(encoding="utf-8")
    # Убираем prompts
    content = content.replace("SU-316-C2960X-48LPD-L-01#", "")
    return content


@pytest.fixture
def lldp_real_output() -> str:
    """Реальный вывод show lldp neighbors detail."""
    return load_real_fixture("lldp_cisco_ios.txt")


@pytest.fixture
def cdp_real_output() -> str:
    """Реальный вывод show cdp neighbors detail."""
    content = load_real_fixture("cdp_cisco_ios.txt")
    # Берём только CDP часть (после Device ID:)
    cdp_start = content.find("Device ID:")
    if cdp_start > 0:
        return content[cdp_start:]
    return content


@pytest.fixture
def normalizer() -> LLDPNormalizer:
    return LLDPNormalizer()


@pytest.mark.unit
class TestLLDPRealDataParsing:
    """Тесты парсинга реальных LLDP данных."""

    def test_textfsm_parses_lldp(self, lldp_real_output):
        """TextFSM парсит реальный LLDP вывод."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        assert len(parsed) >= 7, "Должно быть минимум 7 записей"

    def test_port_id_interface_preserved(self, lldp_real_output, normalizer):
        """Port id: Te1/1/3 должен стать remote_port."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        normalized = normalizer.normalize_dicts(parsed, protocol="lldp")

        # Ищем запись с Te1/0/1 (там Port id: Te1/1/3)
        te_entries = [n for n in normalized if "Te1/0" in n.get("local_interface", "")]
        assert len(te_entries) >= 2, "Должны быть Te1/0/1 и Te1/0/2"

        for entry in te_entries:
            remote_port = entry.get("remote_port", "")
            # remote_port должен быть Te1/1/3 или Te1/1/4, НЕ hostname
            assert remote_port.startswith("Te"), f"remote_port должен быть Te..., got: {remote_port}"
            assert "." not in remote_port, f"remote_port не должен быть hostname: {remote_port}"

    def test_port_id_zero_uses_port_description(self, lldp_real_output, normalizer):
        """Port id: 0 должен использовать Port Description: eth0."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        normalized = normalizer.normalize_dicts(parsed, protocol="lldp")

        # AP записи имеют Port id: 0
        ap_entries = [n for n in normalized if "2802" in n.get("remote_hostname", "")]
        assert len(ap_entries) >= 4, "Должны быть AP записи"

        for entry in ap_entries:
            remote_port = entry.get("remote_port", "")
            # Должен быть eth0, НЕ "0"
            assert remote_port == "eth0", f"AP должен иметь remote_port=eth0, got: {remote_port}"

    def test_port_id_mac_not_in_remote_port(self, lldp_real_output, normalizer):
        """Port id: MAC не должен попадать в remote_port."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        normalized = normalizer.normalize_dicts(parsed, protocol="lldp")

        # Последняя запись имеет Port id: 6c02.e080.2b55 (MAC)
        mac_entries = [n for n in normalized if n.get("remote_hostname", "").startswith("[MAC:")]

        for entry in mac_entries:
            remote_port = entry.get("remote_port")
            # remote_port должен быть None/пустой, НЕ MAC
            assert not remote_port or not normalizer.is_mac_address(remote_port), \
                f"MAC не должен быть в remote_port: {remote_port}"
            # MAC должен быть в remote_mac
            assert entry.get("remote_mac"), "MAC должен быть в remote_mac"

    def test_all_entries_have_local_interface(self, lldp_real_output, normalizer):
        """Все записи должны иметь local_interface."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        normalized = normalizer.normalize_dicts(parsed, protocol="lldp")

        for i, entry in enumerate(normalized):
            assert entry.get("local_interface"), f"Entry {i+1} должен иметь local_interface"


@pytest.mark.unit
class TestCDPRealDataParsing:
    """Тесты парсинга реальных CDP данных."""

    def test_textfsm_parses_cdp(self, cdp_real_output):
        """TextFSM парсит реальный CDP вывод."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show cdp neighbors detail",
            data=cdp_real_output,
        )
        assert len(parsed) >= 8, "Должно быть минимум 8 записей"

    def test_cdp_has_platform(self, cdp_real_output, normalizer):
        """CDP должен давать platform."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show cdp neighbors detail",
            data=cdp_real_output,
        )
        normalized = normalizer.normalize_dicts(parsed, protocol="cdp")

        for entry in normalized:
            assert entry.get("remote_platform"), f"CDP должен давать platform: {entry}"

    def test_cdp_has_full_interface_names(self, cdp_real_output, normalizer):
        """CDP должен давать полные имена интерфейсов."""
        parsed = parse_output(
            platform="cisco_ios",
            command="show cdp neighbors detail",
            data=cdp_real_output,
        )
        normalized = normalizer.normalize_dicts(parsed, protocol="cdp")

        # AP записи
        ap_entries = [n for n in normalized if "AIR-AP" in n.get("remote_platform", "")]
        for entry in ap_entries:
            remote_port = entry.get("remote_port", "")
            # CDP даёт GigabitEthernet0, а не eth0
            assert "Gigabit" in remote_port or "gigabit" in remote_port.lower(), \
                f"CDP AP должен давать GigabitEthernet, got: {remote_port}"


@pytest.mark.unit
class TestMergeRealData:
    """Тесты merge LLDP+CDP с реальными данными."""

    def test_merge_cdp_priority(self, lldp_real_output, cdp_real_output, normalizer):
        """CDP имеет приоритет в merge."""
        lldp_parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        cdp_parsed = parse_output(
            platform="cisco_ios",
            command="show cdp neighbors detail",
            data=cdp_real_output,
        )

        lldp_norm = normalizer.normalize_dicts(lldp_parsed, protocol="lldp")
        cdp_norm = normalizer.normalize_dicts(cdp_parsed, protocol="cdp")

        merged = normalizer.merge_lldp_cdp(lldp_norm, cdp_norm)

        # Проверяем что AP получили GigabitEthernet из CDP
        ap_entries = [m for m in merged if "2802" in m.get("remote_hostname", "")]
        for entry in ap_entries:
            remote_port = entry.get("remote_port", "")
            # CDP приоритет - должен быть GigabitEthernet0
            assert "Gigabit" in remote_port, \
                f"После merge AP должен иметь GigabitEthernet (из CDP), got: {remote_port}"
            # Platform из CDP
            assert entry.get("remote_platform"), "Должен быть platform из CDP"

    def test_merge_has_protocol_both(self, lldp_real_output, cdp_real_output, normalizer):
        """После merge protocol=BOTH."""
        lldp_parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        cdp_parsed = parse_output(
            platform="cisco_ios",
            command="show cdp neighbors detail",
            data=cdp_real_output,
        )

        lldp_norm = normalizer.normalize_dicts(lldp_parsed, protocol="lldp")
        cdp_norm = normalizer.normalize_dicts(cdp_parsed, protocol="cdp")

        merged = normalizer.merge_lldp_cdp(lldp_norm, cdp_norm)

        for entry in merged:
            assert entry.get("protocol") == "BOTH", f"Protocol должен быть BOTH: {entry}"

    def test_merge_all_have_local_interface(self, lldp_real_output, cdp_real_output, normalizer):
        """После merge все записи имеют local_interface."""
        lldp_parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        cdp_parsed = parse_output(
            platform="cisco_ios",
            command="show cdp neighbors detail",
            data=cdp_real_output,
        )

        lldp_norm = normalizer.normalize_dicts(lldp_parsed, protocol="lldp")
        cdp_norm = normalizer.normalize_dicts(cdp_parsed, protocol="cdp")

        merged = normalizer.merge_lldp_cdp(lldp_norm, cdp_norm)

        for i, entry in enumerate(merged):
            assert entry.get("local_interface"), \
                f"Entry {i+1} должен иметь local_interface после merge"

    def test_merge_switch_has_correct_ports(self, lldp_real_output, cdp_real_output, normalizer):
        """Switch-to-switch соединения имеют правильные порты."""
        lldp_parsed = parse_output(
            platform="cisco_ios",
            command="show lldp neighbors detail",
            data=lldp_real_output,
        )
        cdp_parsed = parse_output(
            platform="cisco_ios",
            command="show cdp neighbors detail",
            data=cdp_real_output,
        )

        lldp_norm = normalizer.normalize_dicts(lldp_parsed, protocol="lldp")
        cdp_norm = normalizer.normalize_dicts(cdp_parsed, protocol="cdp")

        merged = normalizer.merge_lldp_cdp(lldp_norm, cdp_norm)

        # Ищем switch (C9200L)
        switch_entries = [m for m in merged if "C9200L" in m.get("remote_hostname", "")]
        assert len(switch_entries) >= 2, "Должны быть записи для C9200L switch"

        for entry in switch_entries:
            remote_port = entry.get("remote_port", "")
            # Должен быть TenGigabitEthernet
            assert "TenGigabit" in remote_port or "Te" in remote_port, \
                f"Switch должен иметь TenGigabitEthernet, got: {remote_port}"
            # НЕ должен быть hostname
            assert "C9200L" not in remote_port, \
                f"remote_port не должен быть hostname: {remote_port}"
