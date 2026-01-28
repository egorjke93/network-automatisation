"""
Тесты для Diff — показ изменений перед применением.
"""

import pytest
from unittest.mock import Mock, MagicMock

from network_collector.netbox.diff import (
    ChangeType,
    FieldChange,
    ObjectChange,
    DiffResult,
    DiffCalculator,
    format_diff_table,
)


class TestFieldChange:
    """Тесты FieldChange."""

    def test_str_format(self):
        """Проверка строкового представления."""
        change = FieldChange(
            field="description",
            old_value="Old",
            new_value="New",
        )
        assert str(change) == "description: 'Old' → 'New'"

    def test_empty_old_value(self):
        """Пустое старое значение."""
        change = FieldChange(field="mode", old_value="", new_value="access")
        assert "'' → 'access'" in str(change)


class TestObjectChange:
    """Тесты ObjectChange."""

    def test_create_str(self):
        """Строка для CREATE."""
        obj = ObjectChange(name="Gi0/1", change_type=ChangeType.CREATE)
        assert str(obj) == "+ Gi0/1"

    def test_update_str(self):
        """Строка для UPDATE."""
        obj = ObjectChange(
            name="Gi0/1",
            change_type=ChangeType.UPDATE,
            changes=[FieldChange("description", "Old", "New")],
        )
        result = str(obj)
        assert "~ Gi0/1" in result
        assert "description" in result

    def test_delete_str(self):
        """Строка для DELETE."""
        obj = ObjectChange(name="Gi0/1", change_type=ChangeType.DELETE)
        assert str(obj) == "- Gi0/1"

    def test_skip_str(self):
        """Строка для SKIP."""
        obj = ObjectChange(
            name="Gi0/1",
            change_type=ChangeType.SKIP,
            reason="no changes",
        )
        assert "skip" in str(obj)
        assert "no changes" in str(obj)

    def test_to_dict(self):
        """Сериализация в dict."""
        obj = ObjectChange(
            name="Gi0/1",
            change_type=ChangeType.UPDATE,
            changes=[FieldChange("description", "Old", "New")],
        )
        data = obj.to_dict()

        assert data["name"] == "Gi0/1"
        assert data["change_type"] == "update"
        assert len(data["changes"]) == 1
        assert data["changes"][0]["field"] == "description"


class TestDiffResult:
    """Тесты DiffResult."""

    def test_empty_result(self):
        """Пустой результат."""
        result = DiffResult(object_type="interfaces")

        assert result.total_changes == 0
        assert result.has_changes is False
        assert "no changes" in result.summary()

    def test_with_creates(self):
        """Результат с созданиями."""
        result = DiffResult(
            object_type="interfaces",
            target="switch-01",
            creates=[
                ObjectChange("Gi0/1", ChangeType.CREATE),
                ObjectChange("Gi0/2", ChangeType.CREATE),
            ],
        )

        assert result.total_changes == 2
        assert result.has_changes is True
        assert "+2 new" in result.summary()

    def test_with_all_types(self):
        """Результат со всеми типами изменений."""
        result = DiffResult(
            object_type="interfaces",
            creates=[ObjectChange("Gi0/1", ChangeType.CREATE)],
            updates=[ObjectChange("Gi0/2", ChangeType.UPDATE)],
            deletes=[ObjectChange("Gi0/3", ChangeType.DELETE)],
            skips=[ObjectChange("Gi0/4", ChangeType.SKIP, reason="excluded")],
        )

        assert result.total_changes == 3
        summary = result.summary()
        assert "+1 new" in summary
        assert "~1 update" in summary
        assert "-1 delete" in summary

    def test_format_detailed(self):
        """Детальный формат."""
        result = DiffResult(
            object_type="interfaces",
            creates=[ObjectChange("Gi0/1", ChangeType.CREATE)],
            updates=[ObjectChange("Gi0/2", ChangeType.UPDATE, changes=[
                FieldChange("description", "", "Server"),
            ])],
        )

        output = result.format_detailed()
        assert "CREATE:" in output
        assert "Gi0/1" in output
        assert "UPDATE:" in output
        assert "Gi0/2" in output
        assert "description" in output

    def test_format_detailed_with_skips(self):
        """Детальный формат с показом пропущенных."""
        result = DiffResult(
            object_type="interfaces",
            skips=[ObjectChange("Gi0/1", ChangeType.SKIP, reason="no changes")],
        )

        # Без skips
        output = result.format_detailed(show_skips=False)
        assert "SKIP:" not in output

        # С skips
        output = result.format_detailed(show_skips=True)
        assert "SKIP:" in output
        assert "Gi0/1" in output

    def test_to_dict(self):
        """Сериализация."""
        result = DiffResult(
            object_type="interfaces",
            target="switch-01",
            creates=[ObjectChange("Gi0/1", ChangeType.CREATE)],
        )

        data = result.to_dict()
        assert data["object_type"] == "interfaces"
        assert data["target"] == "switch-01"
        assert data["summary"]["creates"] == 1
        assert len(data["creates"]) == 1


class TestDiffCalculator:
    """Тесты DiffCalculator."""

    def _create_mock_client(self):
        """Создаёт мок клиента."""
        client = Mock()
        return client

    def _create_mock_device(self, device_id=1, name="switch-01"):
        """Создаёт мок устройства."""
        device = Mock()
        device.id = device_id
        device.name = name
        return device

    def _create_mock_interface(
        self,
        name: str,
        description: str = "",
        enabled: bool = True,
        mode=None,
    ):
        """Создаёт мок интерфейса."""
        intf = Mock()
        intf.name = name
        intf.description = description
        intf.enabled = enabled
        intf.mode = mode
        return intf

    def test_diff_interfaces_new(self):
        """Diff для новых интерфейсов."""
        client = self._create_mock_client()
        device = self._create_mock_device()
        client.get_device_by_name.return_value = device
        client.get_interfaces.return_value = []  # Нет существующих

        calc = DiffCalculator(client)
        result = calc.diff_interfaces("switch-01", [
            {"interface": "Gi0/1", "status": "up"},
            {"interface": "Gi0/2", "status": "down"},
        ])

        assert len(result.creates) == 2
        assert len(result.updates) == 0
        assert result.creates[0].name == "Gi0/1"

    def test_diff_interfaces_existing_no_changes(self):
        """Diff для существующих интерфейсов без изменений."""
        client = self._create_mock_client()
        device = self._create_mock_device()
        client.get_device_by_name.return_value = device
        client.get_interfaces.return_value = [
            self._create_mock_interface("Gi0/1", description="Server", enabled=True),
        ]

        calc = DiffCalculator(client)
        result = calc.diff_interfaces("switch-01", [
            {"interface": "Gi0/1", "description": "Server", "status": "up"},
        ])

        assert len(result.creates) == 0
        assert len(result.updates) == 0
        assert len(result.skips) == 1

    def test_diff_interfaces_with_changes(self):
        """Diff с изменениями."""
        client = self._create_mock_client()
        device = self._create_mock_device()
        client.get_device_by_name.return_value = device
        client.get_interfaces.return_value = [
            self._create_mock_interface("Gi0/1", description="Old", enabled=True),
        ]

        calc = DiffCalculator(client)
        result = calc.diff_interfaces("switch-01", [
            {"interface": "Gi0/1", "description": "New", "status": "up"},
        ])

        assert len(result.updates) == 1
        assert result.updates[0].name == "Gi0/1"
        assert len(result.updates[0].changes) == 1
        assert result.updates[0].changes[0].field == "description"

    def test_diff_interfaces_device_not_found(self):
        """Diff когда устройство не найдено."""
        client = self._create_mock_client()
        client.get_device_by_name.return_value = None

        calc = DiffCalculator(client)
        result = calc.diff_interfaces("unknown", [{"interface": "Gi0/1"}])

        assert len(result.creates) == 0
        assert len(result.updates) == 0

    def test_diff_interfaces_create_disabled(self):
        """Diff с отключённым созданием."""
        client = self._create_mock_client()
        device = self._create_mock_device()
        client.get_device_by_name.return_value = device
        client.get_interfaces.return_value = []

        calc = DiffCalculator(client)
        result = calc.diff_interfaces(
            "switch-01",
            [{"interface": "Gi0/1"}],
            create_missing=False,
        )

        assert len(result.creates) == 0
        assert len(result.skips) == 1
        assert "create_missing=False" in result.skips[0].reason

    def test_diff_ip_addresses(self):
        """Diff для IP-адресов."""
        client = self._create_mock_client()
        device = self._create_mock_device()
        client.get_device_by_name.return_value = device

        existing_ip = Mock()
        existing_ip.address = "10.0.0.1/24"
        client.get_ip_addresses.return_value = [existing_ip]

        calc = DiffCalculator(client)
        result = calc.diff_ip_addresses("switch-01", [
            {"ip_address": "10.0.0.1", "interface": "Vlan100"},  # существует
            {"ip_address": "10.0.0.2", "interface": "Vlan200"},  # новый
        ])

        assert len(result.creates) == 1
        assert result.creates[0].name == "10.0.0.2"
        assert len(result.skips) == 1

    def test_diff_devices(self):
        """Diff для устройств."""
        client = self._create_mock_client()

        existing = Mock()
        existing.serial = "OLD123"
        existing.device_type = Mock()
        existing.device_type.model = "C2960"
        client.get_device_by_name.side_effect = lambda name: \
            existing if name == "switch-01" else None

        calc = DiffCalculator(client)
        result = calc.diff_devices([
            {"name": "switch-01", "serial": "NEW123", "model": "C2960"},  # update serial
            {"name": "switch-02", "serial": "ABC", "model": "C3750"},  # new
        ])

        assert len(result.creates) == 1
        assert result.creates[0].name == "switch-02"
        assert len(result.updates) == 1
        assert result.updates[0].name == "switch-01"


class TestFormatDiffTable:
    """Тесты форматирования таблицы."""

    def test_format_multiple_diffs(self):
        """Форматирование нескольких diff."""
        diffs = [
            DiffResult(
                object_type="interfaces",
                creates=[ObjectChange("Gi0/1", ChangeType.CREATE)],
            ),
            DiffResult(
                object_type="ip_addresses",
                creates=[
                    ObjectChange("10.0.0.1", ChangeType.CREATE),
                    ObjectChange("10.0.0.2", ChangeType.CREATE),
                ],
            ),
        ]

        output = format_diff_table(diffs)

        assert "DIFF SUMMARY" in output
        assert "interfaces" in output
        assert "ip_addresses" in output
        assert "TOTAL:" in output
        assert "+3 new" in output


class TestDiffCompareInterfaceDescription:
    """
    Тесты для очистки description в DiffCalculator._compare_interface.

    Bug fix: пустой description должен детектироваться как изменение.
    """

    def _create_mock_client(self):
        """Создаёт мок NetBox клиента."""
        client = Mock()
        return client

    def test_empty_description_detected_as_change(self):
        """Пустой description должен детектироваться как изменение."""
        client = self._create_mock_client()
        calc = DiffCalculator(client)

        existing = Mock()
        existing.enabled = True
        existing.description = "SU-820-C9200L-48P-4X"
        existing.mode = None

        new_data = {"status": "up", "description": ""}

        changes = calc._compare_interface(existing, new_data)
        desc_changes = [c for c in changes if c.field == "description"]

        assert len(desc_changes) == 1, "Empty description should be detected as change"
        assert desc_changes[0].old_value == "SU-820-C9200L-48P-4X"
        assert desc_changes[0].new_value == ""

    def test_description_missing_in_data_no_change(self):
        """Если description отсутствует в данных, изменения нет."""
        client = self._create_mock_client()
        calc = DiffCalculator(client)

        existing = Mock()
        existing.enabled = True
        existing.description = "Keep this"
        existing.mode = None

        new_data = {"status": "up"}  # Нет description

        changes = calc._compare_interface(existing, new_data)
        desc_changes = [c for c in changes if c.field == "description"]

        assert len(desc_changes) == 0, "No change if description not in data"

    def test_same_description_no_change(self):
        """Одинаковый description не вызывает изменения."""
        client = self._create_mock_client()
        calc = DiffCalculator(client)

        existing = Mock()
        existing.enabled = True
        existing.description = "Same text"
        existing.mode = None

        new_data = {"status": "up", "description": "Same text"}

        changes = calc._compare_interface(existing, new_data)
        desc_changes = [c for c in changes if c.field == "description"]

        assert len(desc_changes) == 0, "Same description should not create change"
