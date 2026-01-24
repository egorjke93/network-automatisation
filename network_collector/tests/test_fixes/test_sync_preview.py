"""
Тесты для preview/diff вывода синхронизации.

Проверяет что:
- DiffResult.summary() возвращает читаемую сводку
- SyncStats правильно подсчитывают статистику
- DiffEntry содержит все необходимые поля
"""

import pytest


class TestDiffResultSummary:
    """Тесты DiffResult и его методов."""

    def test_summary_format(self):
        """Проверяет формат summary."""
        from network_collector.netbox.diff import DiffResult, ObjectChange, ChangeType

        result = DiffResult(
            object_type="interfaces",
            target="switch-01",
            creates=[
                ObjectChange(name="Gi0/1", change_type=ChangeType.CREATE),
                ObjectChange(name="Gi0/2", change_type=ChangeType.CREATE),
            ],
            updates=[
                ObjectChange(name="Gi0/3", change_type=ChangeType.UPDATE),
            ],
            deletes=[],
            skips=[
                ObjectChange(name="Vlan1", change_type=ChangeType.SKIP, reason="excluded"),
            ],
        )

        summary = result.summary()
        assert "interfaces" in summary
        assert "+2 new" in summary
        assert "~1 update" in summary
        assert "=1 skip" in summary

    def test_summary_no_changes(self):
        """Проверяет summary когда нет изменений."""
        from network_collector.netbox.diff import DiffResult

        result = DiffResult(object_type="interfaces", target="switch-01")
        summary = result.summary()
        assert "no changes" in summary

    def test_total_changes_count(self):
        """Проверяет подсчёт total_changes."""
        from network_collector.netbox.diff import DiffResult, ObjectChange, ChangeType

        result = DiffResult(
            object_type="interfaces",
            creates=[ObjectChange(name="a", change_type=ChangeType.CREATE)] * 3,
            updates=[ObjectChange(name="b", change_type=ChangeType.UPDATE)] * 2,
            deletes=[ObjectChange(name="c", change_type=ChangeType.DELETE)] * 1,
            skips=[ObjectChange(name="d", change_type=ChangeType.SKIP)] * 10,  # skips не считаются
        )

        assert result.total_changes == 6  # 3 + 2 + 1
        assert result.has_changes == True

    def test_has_changes_false(self):
        """Проверяет has_changes когда только skips."""
        from network_collector.netbox.diff import DiffResult, ObjectChange, ChangeType

        result = DiffResult(
            object_type="interfaces",
            skips=[ObjectChange(name="d", change_type=ChangeType.SKIP)] * 10,
        )

        assert result.total_changes == 0
        assert result.has_changes == False


class TestSyncStats:
    """Тесты SyncStats схемы."""

    def test_sync_stats_defaults(self):
        """Проверяет default значения."""
        from network_collector.api.schemas import SyncStats

        stats = SyncStats()
        assert stats.created == 0
        assert stats.updated == 0
        assert stats.deleted == 0
        assert stats.skipped == 0
        assert stats.failed == 0

    def test_sync_stats_values(self):
        """Проверяет установку значений."""
        from network_collector.api.schemas import SyncStats

        stats = SyncStats(
            created=10,
            updated=5,
            deleted=2,
            skipped=100,
            failed=1,
        )

        assert stats.created == 10
        assert stats.updated == 5
        assert stats.deleted == 2
        assert stats.skipped == 100
        assert stats.failed == 1


class TestDiffEntry:
    """Тесты DiffEntry для API."""

    def test_diff_entry_fields(self):
        """Проверяет что DiffEntry имеет все поля."""
        from network_collector.api.schemas import DiffEntry

        entry = DiffEntry(
            entity_type="interface",
            entity_name="GigabitEthernet0/1",
            action="update",
            field="enabled",
            old_value=False,
            new_value=True,
            device="switch-01",
        )

        assert entry.entity_type == "interface"
        assert entry.entity_name == "GigabitEthernet0/1"
        assert entry.action == "update"
        assert entry.field == "enabled"
        assert entry.old_value == False
        assert entry.new_value == True
        assert entry.device == "switch-01"

    def test_diff_entry_optional_fields(self):
        """Проверяет опциональные поля."""
        from network_collector.api.schemas import DiffEntry

        # Минимальный entry (для create/delete)
        entry = DiffEntry(
            entity_type="interface",
            entity_name="Gi0/1",
            action="create",
        )

        assert entry.field is None
        assert entry.old_value is None
        assert entry.new_value is None
        assert entry.device is None


class TestSyncRequest:
    """Тесты SyncRequest схемы."""

    def test_dry_run_default_true(self):
        """Проверяет что dry_run по умолчанию True."""
        from network_collector.api.schemas import SyncRequest

        # По умолчанию dry_run должен быть True для безопасности
        request = SyncRequest()
        assert request.dry_run == True

    def test_dry_run_explicit_false(self):
        """Проверяет что dry_run можно установить в False."""
        from network_collector.api.schemas import SyncRequest

        request = SyncRequest(dry_run=False)
        assert request.dry_run == False


class TestObjectChangeFormatting:
    """Тесты форматирования ObjectChange."""

    def test_create_format(self):
        """Проверяет форматирование CREATE."""
        from network_collector.netbox.diff import ObjectChange, ChangeType

        change = ObjectChange(name="Gi0/1", change_type=ChangeType.CREATE)
        assert str(change) == "+ Gi0/1"

    def test_update_format(self):
        """Проверяет форматирование UPDATE с changes."""
        from network_collector.netbox.diff import ObjectChange, ChangeType, FieldChange

        change = ObjectChange(
            name="Gi0/1",
            change_type=ChangeType.UPDATE,
            changes=[
                FieldChange(field="enabled", old_value=False, new_value=True),
            ],
        )
        formatted = str(change)
        assert "~ Gi0/1" in formatted
        assert "enabled" in formatted

    def test_delete_format(self):
        """Проверяет форматирование DELETE."""
        from network_collector.netbox.diff import ObjectChange, ChangeType

        change = ObjectChange(name="Gi0/99", change_type=ChangeType.DELETE)
        assert str(change) == "- Gi0/99"

    def test_skip_format(self):
        """Проверяет форматирование SKIP с reason."""
        from network_collector.netbox.diff import ObjectChange, ChangeType

        change = ObjectChange(
            name="Vlan1",
            change_type=ChangeType.SKIP,
            reason="excluded by pattern",
        )
        formatted = str(change)
        assert "Vlan1" in formatted
        assert "skip" in formatted.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
