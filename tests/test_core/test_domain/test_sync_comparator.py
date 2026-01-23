"""
Тесты для SyncComparator.

Чистые unit-тесты без моков внешних систем.
"""

import pytest
from unittest.mock import Mock

from network_collector.core.domain.sync import (
    SyncComparator,
    SyncDiff,
    SyncItem,
    ChangeType,
    FieldChange,
)


class TestSyncDiff:
    """Тесты для SyncDiff."""

    def test_empty_diff_has_no_changes(self):
        """Пустой diff не имеет изменений."""
        diff = SyncDiff(object_type="interfaces")
        assert not diff.has_changes
        assert diff.total_changes == 0

    def test_diff_with_creates_has_changes(self):
        """Diff с creates имеет изменения."""
        diff = SyncDiff(
            object_type="interfaces",
            to_create=[SyncItem(name="Gi0/1", change_type=ChangeType.CREATE)],
        )
        assert diff.has_changes
        assert diff.total_changes == 1

    def test_diff_with_updates_has_changes(self):
        """Diff с updates имеет изменения."""
        diff = SyncDiff(
            object_type="interfaces",
            to_update=[SyncItem(name="Gi0/1", change_type=ChangeType.UPDATE)],
        )
        assert diff.has_changes
        assert diff.total_changes == 1

    def test_diff_with_deletes_has_changes(self):
        """Diff с deletes имеет изменения."""
        diff = SyncDiff(
            object_type="interfaces",
            to_delete=[SyncItem(name="Gi0/1", change_type=ChangeType.DELETE)],
        )
        assert diff.has_changes
        assert diff.total_changes == 1

    def test_diff_skips_dont_count_as_changes(self):
        """Skips не считаются изменениями."""
        diff = SyncDiff(
            object_type="interfaces",
            to_skip=[SyncItem(name="Gi0/1", change_type=ChangeType.SKIP)],
        )
        assert not diff.has_changes
        assert diff.total_changes == 0

    def test_summary_format(self):
        """Тест формата summary."""
        diff = SyncDiff(
            object_type="interfaces",
            to_create=[SyncItem(name="Gi0/1", change_type=ChangeType.CREATE)],
            to_update=[SyncItem(name="Gi0/2", change_type=ChangeType.UPDATE)],
            to_delete=[SyncItem(name="Gi0/3", change_type=ChangeType.DELETE)],
        )
        summary = diff.summary()
        assert "+1 create" in summary
        assert "~1 update" in summary
        assert "-1 delete" in summary


class TestSyncItem:
    """Тесты для SyncItem."""

    def test_create_item_str(self):
        """Строковое представление CREATE."""
        item = SyncItem(name="Gi0/1", change_type=ChangeType.CREATE)
        assert str(item) == "+ Gi0/1"

    def test_update_item_str(self):
        """Строковое представление UPDATE."""
        item = SyncItem(
            name="Gi0/1",
            change_type=ChangeType.UPDATE,
            changes=[FieldChange(field="description", old_value="", new_value="Uplink")],
        )
        assert "~ Gi0/1" in str(item)
        assert "description" in str(item)

    def test_delete_item_str(self):
        """Строковое представление DELETE."""
        item = SyncItem(name="Gi0/1", change_type=ChangeType.DELETE)
        assert str(item) == "- Gi0/1"

    def test_skip_item_str(self):
        """Строковое представление SKIP."""
        item = SyncItem(name="Gi0/1", change_type=ChangeType.SKIP, reason="no changes")
        assert "Gi0/1" in str(item)
        assert "skip" in str(item)

    def test_to_dict(self):
        """Сериализация в dict."""
        item = SyncItem(
            name="Gi0/1",
            change_type=ChangeType.UPDATE,
            changes=[FieldChange(field="description", old_value="", new_value="Uplink")],
        )
        d = item.to_dict()
        assert d["name"] == "Gi0/1"
        assert d["change_type"] == "update"
        assert len(d["changes"]) == 1


class TestSyncComparatorInterfaces:
    """Тесты сравнения интерфейсов."""

    @pytest.fixture
    def comparator(self):
        return SyncComparator()

    def test_empty_local_no_changes(self, comparator):
        """Пустой local - нет изменений."""
        diff = comparator.compare_interfaces(local=[], remote=[])
        assert not diff.has_changes

    def test_new_interface_creates(self, comparator):
        """Новый интерфейс добавляется в to_create."""
        local = [{"name": "Gi0/1", "description": "Uplink"}]
        remote = []

        diff = comparator.compare_interfaces(local=local, remote=remote)

        assert len(diff.to_create) == 1
        assert diff.to_create[0].name == "Gi0/1"
        assert diff.to_create[0].local_data["description"] == "Uplink"

    def test_existing_interface_no_changes_skips(self, comparator):
        """Существующий интерфейс без изменений - skip."""
        local = [{"name": "Gi0/1", "description": "Uplink"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = "Uplink"
        remote_intf.enabled = True
        remote_intf.mode = None

        diff = comparator.compare_interfaces(local=local, remote=[remote_intf])

        assert len(diff.to_skip) == 1
        assert diff.to_skip[0].name == "Gi0/1"
        assert diff.to_skip[0].reason == "no changes"

    def test_existing_interface_with_changes_updates(self, comparator):
        """Существующий интерфейс с изменениями - update."""
        local = [{"name": "Gi0/1", "description": "New Description"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = "Old Description"
        remote_intf.enabled = True
        remote_intf.mode = None

        diff = comparator.compare_interfaces(local=local, remote=[remote_intf])

        assert len(diff.to_update) == 1
        assert diff.to_update[0].name == "Gi0/1"
        assert len(diff.to_update[0].changes) == 1
        assert diff.to_update[0].changes[0].field == "description"
        assert diff.to_update[0].changes[0].old_value == "Old Description"
        assert diff.to_update[0].changes[0].new_value == "New Description"

    def test_cleanup_deletes_extra_interfaces(self, comparator):
        """cleanup=True удаляет лишние интерфейсы."""
        local = [{"name": "Gi0/1"}]
        remote_intf1 = Mock()
        remote_intf1.name = "Gi0/1"
        remote_intf1.description = ""
        remote_intf1.enabled = True
        remote_intf1.mode = None

        remote_intf2 = Mock()
        remote_intf2.name = "Gi0/2"  # Нет в local

        diff = comparator.compare_interfaces(
            local=local,
            remote=[remote_intf1, remote_intf2],
            cleanup=True,
        )

        assert len(diff.to_delete) == 1
        assert diff.to_delete[0].name == "Gi0/2"
        assert diff.to_delete[0].remote_data == remote_intf2

    def test_cleanup_false_no_deletes(self, comparator):
        """cleanup=False не удаляет лишние интерфейсы."""
        local = [{"name": "Gi0/1"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/2"  # Нет в local

        diff = comparator.compare_interfaces(
            local=local,
            remote=[remote_intf],
            cleanup=False,
        )

        assert len(diff.to_delete) == 0

    def test_exclude_patterns_skip_matching(self, comparator):
        """exclude_patterns пропускает matching интерфейсы."""
        local = [
            {"name": "Gi0/1"},
            {"name": "Vlan1"},
            {"name": "Null0"},
        ]

        diff = comparator.compare_interfaces(
            local=local,
            remote=[],
            exclude_patterns=["Vlan.*", "Null.*"],
        )

        assert len(diff.to_create) == 1
        assert diff.to_create[0].name == "Gi0/1"
        assert len(diff.to_skip) == 2

    def test_exclude_patterns_also_skip_delete(self, comparator):
        """exclude_patterns пропускает удаление matching интерфейсов."""
        local = []
        remote_intf = Mock()
        remote_intf.name = "Vlan1"

        diff = comparator.compare_interfaces(
            local=local,
            remote=[remote_intf],
            exclude_patterns=["Vlan.*"],
            cleanup=True,
        )

        assert len(diff.to_delete) == 0
        assert len(diff.to_skip) == 1

    def test_create_missing_false_skips_new(self, comparator):
        """create_missing=False пропускает новые интерфейсы."""
        local = [{"name": "Gi0/1"}]

        diff = comparator.compare_interfaces(
            local=local,
            remote=[],
            create_missing=False,
        )

        assert len(diff.to_create) == 0
        assert len(diff.to_skip) == 1
        assert diff.to_skip[0].reason == "create_missing=False"

    def test_update_existing_false_skips_updates(self, comparator):
        """update_existing=False пропускает обновления."""
        local = [{"name": "Gi0/1", "description": "New"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = "Old"
        remote_intf.enabled = True
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local,
            remote=[remote_intf],
            update_existing=False,
        )

        assert len(diff.to_update) == 0
        assert len(diff.to_skip) == 1
        assert diff.to_skip[0].reason == "update_existing=False"

    def test_interface_model_to_dict_conversion(self, comparator):
        """Interface модели конвертируются через to_dict()."""
        # Mock Interface model
        local_intf = Mock()
        local_intf.to_dict.return_value = {"name": "Gi0/1", "description": "Test"}

        diff = comparator.compare_interfaces(local=[local_intf], remote=[])

        assert len(diff.to_create) == 1
        assert diff.to_create[0].name == "Gi0/1"


class TestSyncComparatorIPAddresses:
    """Тесты сравнения IP-адресов."""

    @pytest.fixture
    def comparator(self):
        return SyncComparator()

    def test_new_ip_creates(self, comparator):
        """Новый IP добавляется в to_create."""
        local = [{"ip_address": "10.0.0.1/24", "interface": "Gi0/1"}]

        diff = comparator.compare_ip_addresses(local=local, remote=[])

        assert len(diff.to_create) == 1
        assert diff.to_create[0].name == "10.0.0.1"

    def test_existing_ip_skips(self, comparator):
        """Существующий IP без update_existing - skip."""
        local = [{"ip_address": "10.0.0.1/24"}]
        remote_ip = Mock()
        remote_ip.address = "10.0.0.1/24"

        diff = comparator.compare_ip_addresses(local=local, remote=[remote_ip])

        assert len(diff.to_skip) == 1
        assert diff.to_skip[0].name == "10.0.0.1"

    def test_cleanup_deletes_extra_ips(self, comparator):
        """cleanup=True удаляет лишние IP."""
        local = [{"ip_address": "10.0.0.1/24"}]
        remote_ip1 = Mock()
        remote_ip1.address = "10.0.0.1/24"
        remote_ip2 = Mock()
        remote_ip2.address = "10.0.0.2/24"  # Нет в local

        diff = comparator.compare_ip_addresses(
            local=local,
            remote=[remote_ip1, remote_ip2],
            cleanup=True,
        )

        assert len(diff.to_delete) == 1
        assert diff.to_delete[0].name == "10.0.0.2"

    def test_update_existing_with_changes(self, comparator):
        """update_existing=True обновляет изменённые поля."""
        local = [{"ip_address": "10.0.0.1/24", "description": "New Desc"}]
        remote_ip = Mock()
        remote_ip.address = "10.0.0.1/24"
        remote_ip.description = "Old Desc"

        diff = comparator.compare_ip_addresses(
            local=local,
            remote=[remote_ip],
            update_existing=True,
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "description"

    def test_update_existing_detects_prefix_change(self, comparator):
        """update_existing=True обнаруживает изменение маски."""
        # На устройстве /24, в NetBox было ошибочно /32
        local = [{"ip_address": "10.177.30.222/24"}]
        remote_ip = Mock()
        remote_ip.address = "10.177.30.222/32"
        remote_ip.description = ""

        diff = comparator.compare_ip_addresses(
            local=local,
            remote=[remote_ip],
            update_existing=True,
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].name == "10.177.30.222"
        # Проверяем что обнаружено изменение маски
        prefix_change = next(
            (c for c in diff.to_update[0].changes if c.field == "prefix_length"),
            None
        )
        assert prefix_change is not None
        assert prefix_change.old_value == 32
        assert prefix_change.new_value == 24


class TestSyncComparatorCables:
    """Тесты сравнения кабелей."""

    @pytest.fixture
    def comparator(self):
        return SyncComparator()

    def test_new_cable_creates(self, comparator):
        """Новый кабель добавляется в to_create."""
        local = [{
            "hostname": "switch1",
            "local_interface": "Gi0/1",
            "remote_hostname": "switch2",
            "remote_port": "Gi0/1",
        }]

        diff = comparator.compare_cables(local=local, remote=[])

        assert len(diff.to_create) == 1
        assert "switch1:Gi0/1" in diff.to_create[0].name

    def test_existing_cable_skips(self, comparator):
        """Существующий кабель - skip."""
        local = [{
            "hostname": "switch1",
            "local_interface": "Gi0/1",
            "remote_hostname": "switch2",
            "remote_port": "Gi0/2",
        }]

        # Mock NetBox cable
        remote_cable = Mock()
        a_term = Mock()
        a_term.device = Mock()
        a_term.device.name = "switch1"
        a_term.name = "Gi0/1"

        b_term = Mock()
        b_term.device = Mock()
        b_term.device.name = "switch2"
        b_term.name = "Gi0/2"

        remote_cable.a_terminations = [a_term]
        remote_cable.b_terminations = [b_term]

        diff = comparator.compare_cables(local=local, remote=[remote_cable])

        assert len(diff.to_skip) == 1
        assert diff.to_skip[0].reason == "already exists"

    def test_cleanup_deletes_extra_cables(self, comparator):
        """cleanup=True удаляет лишние кабели."""
        local = []  # Нет кабелей в LLDP

        # Mock NetBox cable
        remote_cable = Mock()
        a_term = Mock()
        a_term.device = Mock()
        a_term.device.name = "switch1"
        a_term.name = "Gi0/1"

        b_term = Mock()
        b_term.device = Mock()
        b_term.device.name = "switch2"
        b_term.name = "Gi0/2"

        remote_cable.a_terminations = [a_term]
        remote_cable.b_terminations = [b_term]

        diff = comparator.compare_cables(local=local, remote=[remote_cable], cleanup=True)

        assert len(diff.to_delete) == 1

    def test_cable_endpoints_normalized(self, comparator):
        """Endpoints нормализуются (A-B = B-A)."""
        # Local: switch1:Gi0/1 -> switch2:Gi0/2
        local = [{
            "hostname": "switch1",
            "local_interface": "Gi0/1",
            "remote_hostname": "switch2",
            "remote_port": "Gi0/2",
        }]

        # Remote: switch2:Gi0/2 -> switch1:Gi0/1 (reversed)
        remote_cable = Mock()
        a_term = Mock()
        a_term.device = Mock()
        a_term.device.name = "switch2"
        a_term.name = "Gi0/2"

        b_term = Mock()
        b_term.device = Mock()
        b_term.device.name = "switch1"
        b_term.name = "Gi0/1"

        remote_cable.a_terminations = [a_term]
        remote_cable.b_terminations = [b_term]

        diff = comparator.compare_cables(local=local, remote=[remote_cable])

        # Должен быть skip, не create (потому что endpoints одинаковые)
        assert len(diff.to_create) == 0
        assert len(diff.to_skip) == 1


class TestFieldChange:
    """Тесты для FieldChange."""

    def test_str_representation(self):
        """Строковое представление."""
        fc = FieldChange(field="description", old_value="old", new_value="new")
        assert str(fc) == "description: 'old' → 'new'"


class TestEnabledModeOption:
    """Тесты для опции enabled_mode."""

    @pytest.fixture
    def comparator(self):
        return SyncComparator()

    def test_enabled_mode_admin_up_is_enabled(self, comparator):
        """admin mode: status=up → enabled=True."""
        local = [{"name": "Gi0/1", "status": "up"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = False  # В NetBox выключен
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="admin"
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "enabled"
        assert diff.to_update[0].changes[0].new_value is True

    def test_enabled_mode_admin_down_is_enabled(self, comparator):
        """admin mode: status=down (no link, but admin up) → enabled=True."""
        local = [{"name": "Gi0/1", "status": "down"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = False  # В NetBox выключен
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="admin"
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "enabled"
        assert diff.to_update[0].changes[0].new_value is True

    def test_enabled_mode_admin_disabled_is_disabled(self, comparator):
        """admin mode: status=disabled → enabled=False."""
        local = [{"name": "Gi0/1", "status": "disabled"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = True  # В NetBox включён
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="admin"
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "enabled"
        assert diff.to_update[0].changes[0].new_value is False

    def test_enabled_mode_admin_error_is_disabled(self, comparator):
        """admin mode: status=error (err-disabled) → enabled=False."""
        local = [{"name": "Gi0/1", "status": "error"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = True  # В NetBox включён
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="admin"
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "enabled"
        assert diff.to_update[0].changes[0].new_value is False

    def test_enabled_mode_link_up_is_enabled(self, comparator):
        """link mode: status=up → enabled=True."""
        local = [{"name": "Gi0/1", "status": "up"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = False  # В NetBox выключен
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="link"
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "enabled"
        assert diff.to_update[0].changes[0].new_value is True

    def test_enabled_mode_link_down_is_disabled(self, comparator):
        """link mode: status=down (no link) → enabled=False."""
        local = [{"name": "Gi0/1", "status": "down"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = True  # В NetBox включён
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="link"
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "enabled"
        assert diff.to_update[0].changes[0].new_value is False

    def test_enabled_mode_link_disabled_is_disabled(self, comparator):
        """link mode: status=disabled → enabled=False."""
        local = [{"name": "Gi0/1", "status": "disabled"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = True  # В NetBox включён
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="link"
        )

        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].field == "enabled"
        assert diff.to_update[0].changes[0].new_value is False

    def test_enabled_mode_default_is_admin(self, comparator):
        """По умолчанию enabled_mode=admin."""
        local = [{"name": "Gi0/1", "status": "down"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = False
        remote_intf.mode = None

        # Не передаём enabled_mode, должен использоваться "admin"
        diff = comparator.compare_interfaces(local=local, remote=[remote_intf])

        # В admin mode, down = enabled
        assert len(diff.to_update) == 1
        assert diff.to_update[0].changes[0].new_value is True

    def test_enabled_mode_no_changes_when_match(self, comparator):
        """Нет изменений когда статус совпадает."""
        local = [{"name": "Gi0/1", "status": "up"}]
        remote_intf = Mock()
        remote_intf.name = "Gi0/1"
        remote_intf.description = ""
        remote_intf.enabled = True  # Совпадает
        remote_intf.mode = None

        diff = comparator.compare_interfaces(
            local=local, remote=[remote_intf], enabled_mode="admin"
        )

        assert len(diff.to_skip) == 1
        assert diff.to_skip[0].reason == "no changes"


class TestIPAddressPrefixComparison:
    """Тесты для сравнения prefix_length IP-адресов (Bug #2 fix)."""

    @pytest.fixture
    def comparator(self):
        return SyncComparator()

    def test_ip_with_mask_field_detected(self, comparator):
        """IP с полем mask корректно определяет prefix."""
        local = [{"ip_address": "10.1.1.1", "mask": "30"}]
        remote_ip = Mock()
        remote_ip.address = "10.1.1.1/30"

        diff = comparator.compare_ip_addresses(
            local=local, remote=[remote_ip], update_existing=True
        )

        # Маски совпадают - не должно быть изменений
        assert len(diff.to_update) == 0
        assert len(diff.to_skip) == 1

    def test_ip_with_prefix_length_field_detected(self, comparator):
        """IP с полем prefix_length корректно определяет prefix."""
        local = [{"ip_address": "10.1.1.1", "prefix_length": "32"}]
        remote_ip = Mock()
        remote_ip.address = "10.1.1.1/32"

        diff = comparator.compare_ip_addresses(
            local=local, remote=[remote_ip], update_existing=True
        )

        # Маски совпадают - не должно быть изменений
        assert len(diff.to_update) == 0
        assert len(diff.to_skip) == 1

    def test_ip_with_slash_in_address(self, comparator):
        """IP с маской в самом адресе (10.1.1.1/24) корректно парсится."""
        local = [{"ip_address": "10.1.1.1/24"}]
        remote_ip = Mock()
        remote_ip.address = "10.1.1.1/24"

        diff = comparator.compare_ip_addresses(
            local=local, remote=[remote_ip], update_existing=True
        )

        # Маски совпадают
        assert len(diff.to_update) == 0
        assert len(diff.to_skip) == 1

    def test_ip_without_mask_no_prefix_change_reported(self, comparator):
        """IP без маски не должен вызывать изменение prefix."""
        local = [{"ip_address": "10.1.1.1"}]  # Нет mask и нет /
        remote_ip = Mock()
        remote_ip.address = "10.1.1.1/30"

        diff = comparator.compare_ip_addresses(
            local=local, remote=[remote_ip], update_existing=True
        )

        # Нет маски в local - не должно быть изменения prefix
        if diff.to_update:
            changes = diff.to_update[0].changes
            prefix_changes = [c for c in changes if c.field == "prefix_length"]
            assert len(prefix_changes) == 0, "Не должно быть изменения prefix если маска не указана"

    def test_ip_different_prefix_detected(self, comparator):
        """Разные маски корректно определяются как изменение."""
        local = [{"ip_address": "10.1.1.1", "mask": "24"}]
        remote_ip = Mock()
        remote_ip.address = "10.1.1.1/30"

        diff = comparator.compare_ip_addresses(
            local=local, remote=[remote_ip], update_existing=True
        )

        assert len(diff.to_update) == 1
        changes = diff.to_update[0].changes
        prefix_change = next((c for c in changes if c.field == "prefix_length"), None)
        assert prefix_change is not None
        assert prefix_change.old_value == 30
        assert prefix_change.new_value == 24

    def test_ip_with_dotted_mask_converted(self, comparator):
        """Маска в формате 255.255.255.0 конвертируется в prefix."""
        local = [{"ip_address": "10.1.1.1", "mask": "255.255.255.0"}]
        remote_ip = Mock()
        remote_ip.address = "10.1.1.1/24"

        diff = comparator.compare_ip_addresses(
            local=local, remote=[remote_ip], update_existing=True
        )

        # 255.255.255.0 = /24, совпадает с remote /24
        assert len(diff.to_update) == 0
        assert len(diff.to_skip) == 1
