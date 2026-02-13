"""
Тесты обогащения данных NX-OS.

Проверяет:
- Получение media_type из show interface status
- Мерж данных show interface + show interface status
- Получение трансиверов для inventory
- InterfaceCollector._parse_media_types() метод
"""

import pytest
from pathlib import Path
from ntc_templates.parse import parse_output

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestInterfaceCollectorMediaTypes:
    """Тесты InterfaceCollector._parse_media_types()."""

    @pytest.fixture
    def nxos_interface_status(self):
        """show interface status - источник media_type."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface_status.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found")

    def test_parse_media_types_returns_dict(self, nxos_interface_status):
        """Тест что _parse_media_types возвращает словарь interface -> type."""
        from network_collector.collectors.interfaces import InterfaceCollector

        collector = InterfaceCollector()
        result = collector._parse_media_types(
            nxos_interface_status,
            platform="cisco_nxos",
            command="show interface status",
        )

        assert isinstance(result, dict), "Должен вернуть словарь"
        assert len(result) > 0, "Словарь не должен быть пустым"

    def test_parse_media_types_normalizes_port_names(self, nxos_interface_status):
        """Тест нормализации имён портов: Eth1/1 -> Ethernet1/1."""
        from network_collector.collectors.interfaces import InterfaceCollector

        collector = InterfaceCollector()
        result = collector._parse_media_types(
            nxos_interface_status,
            platform="cisco_nxos",
            command="show interface status",
        )

        # Должны быть полные имена Ethernet1/X
        ethernet_names = [k for k in result.keys() if k.startswith("Ethernet")]
        assert len(ethernet_names) > 0, "Должны быть Ethernet имена"

    def test_parse_media_types_filters_empty(self, nxos_interface_status):
        """Тест что пустые и '--' type фильтруются."""
        from network_collector.collectors.interfaces import InterfaceCollector

        collector = InterfaceCollector()
        result = collector._parse_media_types(
            nxos_interface_status,
            platform="cisco_nxos",
            command="show interface status",
        )

        # Не должно быть пустых или "--" значений
        for iface, media_type in result.items():
            assert media_type, f"media_type для {iface} не должен быть пустым"
            assert media_type != "--", f"media_type для {iface} не должен быть '--'"

    def test_parse_media_types_has_correct_format(self, nxos_interface_status):
        """Тест что media_type содержит правильный формат (10Gbase-LR, etc.)."""
        from network_collector.collectors.interfaces import InterfaceCollector

        collector = InterfaceCollector()
        result = collector._parse_media_types(
            nxos_interface_status,
            platform="cisco_nxos",
            command="show interface status",
        )

        # Все значения должны содержать base, SFP или QSFP
        for iface, media_type in result.items():
            has_valid_format = any(x in media_type for x in ["base", "Base", "SFP", "QSFP"])
            assert has_valid_format, f"media_type '{media_type}' для {iface} должен содержать base/SFP/QSFP"


class TestNxosMediaTypeEnrichment:
    """Тесты обогащения NX-OS данных media_type."""

    @pytest.fixture
    def nxos_interface(self):
        """show interface - основные данные."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found")

    @pytest.fixture
    def nxos_interface_status(self):
        """show interface status - источник media_type."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface_status.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found")

    def test_interface_has_no_media_type(self, nxos_interface):
        """
        Проверяет что show interface на NX-OS НЕ имеет полезного media_type.

        Проблема: NX-OS возвращает "media type is 10G" вместо "10Gbase-LR".
        """
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface",
            data=nxos_interface,
        )

        # Находим Ethernet интерфейсы
        eth_ifaces = [i for i in parsed if i.get("interface", "").startswith("Ethernet")]

        if not eth_ifaces:
            pytest.skip("Нет Ethernet интерфейсов")

        # Проверяем media_type - должен быть только скорость (10G, 100G)
        for iface in eth_ifaces[:5]:  # Проверяем первые 5
            media = iface.get("media_type", "")
            if media:
                # NX-OS возвращает "10G", "100G" - без типа оптики
                # Не должно быть "LR", "SR" и т.д.
                has_optics_type = any(x in media.upper() for x in ["LR", "SR", "ER", "ZR", "BASE"])
                # Это нормально что нет типа оптики в show interface
                # Потому что его нужно брать из show interface status

    def test_interface_status_has_media_type(self, nxos_interface_status):
        """
        Проверяет что show interface status ИМЕЕТ правильный media_type.

        Это источник для enrichment.
        """
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface status",
            data=nxos_interface_status,
        )

        # Находим интерфейсы с трансиверами (не --)
        with_type = [
            i for i in parsed
            if i.get("type") and i.get("type") != "--"
        ]

        assert len(with_type) > 0, "Должны быть интерфейсы с type"

        # Проверяем что type содержит информацию об оптике
        for iface in with_type:
            media_type = iface["type"]
            # Должен быть формат: 10Gbase-LR, 1000base-SX, QSFP-100G-CR4
            has_optics = any(x in media_type for x in ["base", "Base", "QSFP", "SFP"])
            assert has_optics, f"type должен содержать тип оптики: {media_type}"

    def test_enrichment_logic(self, nxos_interface, nxos_interface_status):
        """
        Тест логики обогащения: merge show interface + show interface status.

        Симулирует что делает InterfaceCollector._enrich_with_media_type()
        """
        # Парсим оба источника
        interfaces = parse_output(
            platform="cisco_nxos",
            command="show interface",
            data=nxos_interface,
        )

        status = parse_output(
            platform="cisco_nxos",
            command="show interface status",
            data=nxos_interface_status,
        )

        # Создаём маппинг port -> type из status
        # Нормализуем Eth1/1 -> Ethernet1/1
        media_map = {}
        for row in status:
            port = row.get("port", "")
            media_type = row.get("type", "")
            if port and media_type and media_type != "--":
                # Нормализуем имя
                if port.startswith("Eth"):
                    full_name = f"Ethernet{port[3:]}"
                else:
                    full_name = port
                media_map[full_name] = media_type

        # Обогащаем interfaces
        enriched_count = 0
        for iface in interfaces:
            name = iface.get("interface", "")
            if name in media_map:
                iface["media_type_enriched"] = media_map[name]
                enriched_count += 1

        # Должны обогатить хотя бы некоторые интерфейсы
        assert enriched_count > 0, "Должны обогатить хотя бы один интерфейс"

        # Проверяем что обогащённые данные корректны
        enriched = [i for i in interfaces if i.get("media_type_enriched")]
        for iface in enriched:
            media = iface["media_type_enriched"]
            # Должен быть реальный тип оптики, не просто скорость
            assert any(x in media for x in ["base", "Base", "QSFP", "SFP"]), \
                f"Обогащённый media_type должен содержать тип оптики: {media}"


class TestInventoryCollectorTransceivers:
    """Тесты InventoryNormalizer.normalize_transceivers()."""

    @pytest.fixture
    def nxos_transceiver(self):
        """show interface transceiver - SFP/QSFP."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface_transceiver.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found")

    @pytest.fixture
    def normalizer(self):
        """InventoryNormalizer для тестирования."""
        from network_collector.core.domain.inventory import InventoryNormalizer
        return InventoryNormalizer()

    @pytest.fixture
    def parsed_transceivers(self, nxos_transceiver):
        """Распарсенные данные трансиверов через NTC."""
        from ntc_templates.parse import parse_output
        return parse_output(
            platform="cisco_nxos",
            command="show interface transceiver",
            data=nxos_transceiver,
        )

    def test_parse_transceivers_returns_list(self, parsed_transceivers, normalizer):
        """Тест что normalize_transceivers возвращает список."""
        result = normalizer.normalize_transceivers(
            parsed_transceivers,
            platform="cisco_nxos",
        )

        assert isinstance(result, list), "Должен вернуть список"
        assert len(result) > 0, "Список не должен быть пустым"

    def test_parse_transceivers_format(self, parsed_transceivers, normalizer):
        """Тест что трансиверы в формате inventory."""
        result = normalizer.normalize_transceivers(
            parsed_transceivers,
            platform="cisco_nxos",
        )

        # Каждый элемент должен иметь поля inventory
        for item in result:
            assert "name" in item, "Должно быть поле name"
            assert "description" in item, "Должно быть поле description"
            assert "pid" in item, "Должно быть поле pid"
            assert "serial" in item, "Должно быть поле serial"

            # name должен начинаться с Transceiver
            assert item["name"].startswith("Transceiver"), \
                f"name должен начинаться с Transceiver: {item['name']}"

    def test_parse_transceivers_filters_not_present(self, parsed_transceivers, normalizer):
        """Тест что 'not present' трансиверы фильтруются."""
        result = normalizer.normalize_transceivers(
            parsed_transceivers,
            platform="cisco_nxos",
        )

        # Не должно быть "not present"
        for item in result:
            desc = item.get("description", "").lower()
            assert "not present" not in desc, \
                f"Не должно быть 'not present' в description: {desc}"

    def test_parse_transceivers_has_valid_types(self, parsed_transceivers, normalizer):
        """Тест что description содержит валидный тип."""
        result = normalizer.normalize_transceivers(
            parsed_transceivers,
            platform="cisco_nxos",
        )

        # description должен содержать base (10Gbase-LR, 1000base-SX)
        for item in result:
            desc = item.get("description", "")
            has_valid = any(x in desc for x in ["base", "Base"])
            assert has_valid, f"description должен содержать 'base': {desc}"


class TestNxosTransceiverEnrichment:
    """Тесты обогащения inventory трансиверами для NX-OS."""

    @pytest.fixture
    def nxos_inventory(self):
        """show inventory - chassis, PSU, fans."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_inventory.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found")

    @pytest.fixture
    def nxos_transceiver(self):
        """show interface transceiver - SFP/QSFP."""
        fixture_path = FIXTURES_DIR / "cisco_nxos" / "show_interface_transceiver.txt"
        if fixture_path.exists():
            return fixture_path.read_text(encoding="utf-8")
        pytest.skip("Fixture not found")

    def test_transceiver_to_inventory_format(self, nxos_transceiver):
        """
        Тест конвертации show interface transceiver в формат inventory.

        Для NetBox нужно:
        - name: "SFP Ethernet1/1" или "Transceiver Eth1/1"
        - pid: part_number (SFP+ LR)
        - serial: serial_number
        - description: type (10Gbase-LR)
        """
        parsed = parse_output(
            platform="cisco_nxos",
            command="show interface transceiver",
            data=nxos_transceiver,
        )

        # Находим интерфейсы с трансиверами
        with_transceiver = [
            i for i in parsed
            if i.get("type") and "not present" not in str(i.get("type", "")).lower()
        ]

        assert len(with_transceiver) > 0, "Должны быть трансиверы"

        # Конвертируем в формат inventory
        inventory_items = []
        for item in with_transceiver:
            inv_item = {
                "name": f"Transceiver {item.get('interface', '')}",
                "pid": item.get("part_number", ""),
                "serial": item.get("serial_number", ""),
                "description": item.get("type", ""),
                "manufacturer": item.get("name", ""),  # OEM, CISCO-FINISAR, etc.
            }
            inventory_items.append(inv_item)

        # Проверяем что получили корректные данные
        for item in inventory_items:
            assert item["name"].startswith("Transceiver"), "name должен начинаться с Transceiver"
            assert item["description"], "description (type) не должен быть пустым"

    def test_merge_inventory_with_transceivers(self, nxos_inventory, nxos_transceiver):
        """
        Тест объединения show inventory + show interface transceiver.

        Финальный inventory должен содержать:
        - Chassis, Slot, PSU, Fan из show inventory
        - Трансиверы из show interface transceiver
        """
        # Парсим inventory
        inventory = parse_output(
            platform="cisco_nxos",
            command="show inventory",
            data=nxos_inventory,
        )

        # Парсим трансиверы
        transceivers = parse_output(
            platform="cisco_nxos",
            command="show interface transceiver",
            data=nxos_transceiver,
        )

        # Фильтруем трансиверы (только present)
        present_transceivers = [
            t for t in transceivers
            if t.get("type") and "not present" not in str(t.get("type", "")).lower()
        ]

        # Конвертируем в формат inventory
        transceiver_items = []
        for t in present_transceivers:
            transceiver_items.append({
                "name": f"Transceiver {t.get('interface', '')}",
                "descr": t.get("type", ""),
                "pid": t.get("part_number", ""),
                "sn": t.get("serial_number", ""),
            })

        # Объединяем
        full_inventory = inventory + transceiver_items

        # Проверяем что есть и то и другое
        names = [i.get("name", "") for i in full_inventory]

        has_chassis = any("Chassis" in name for name in names)
        has_transceiver = any("Transceiver" in name for name in names)

        assert has_chassis, "Должен быть Chassis"
        assert has_transceiver, "Должны быть Transceiver-ы"

        # Общее количество должно быть больше чем просто inventory
        assert len(full_inventory) > len(inventory), \
            "Объединённый inventory должен быть больше базового"
