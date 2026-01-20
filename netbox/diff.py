"""
Diff — показ изменений перед применением в NetBox.

Позволяет увидеть что будет создано/обновлено/удалено
ДО реального применения изменений.

Пример использования:
    from network_collector.netbox.diff import DiffCalculator

    diff_calc = DiffCalculator(client)
    diff = diff_calc.diff_interfaces("switch-01", collected_interfaces)

    # Показать изменения
    print(diff.summary())

    # Детали по каждому объекту
    for change in diff.creates:
        print(f"CREATE: {change}")
    for change in diff.updates:
        print(f"UPDATE: {change.name} - {change.changes}")
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from .sync.base import get_sync_config

logger = logging.getLogger(__name__)


class ChangeType(str, Enum):
    """Тип изменения."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"


@dataclass
class FieldChange:
    """Изменение одного поля."""
    field: str
    old_value: Any
    new_value: Any

    def __str__(self) -> str:
        return f"{self.field}: {self.old_value!r} → {self.new_value!r}"


@dataclass
class ObjectChange:
    """Изменение одного объекта."""
    name: str
    change_type: ChangeType
    changes: List[FieldChange] = field(default_factory=list)
    reason: str = ""

    def __str__(self) -> str:
        if self.change_type == ChangeType.CREATE:
            return f"+ {self.name}"
        elif self.change_type == ChangeType.UPDATE:
            changes_str = ", ".join(str(c) for c in self.changes)
            return f"~ {self.name}: {changes_str}"
        elif self.change_type == ChangeType.DELETE:
            return f"- {self.name}"
        else:
            return f"  {self.name} (skip: {self.reason})"

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "name": self.name,
            "change_type": self.change_type.value,
            "changes": [
                {"field": c.field, "old": c.old_value, "new": c.new_value}
                for c in self.changes
            ],
            "reason": self.reason,
        }


@dataclass
class DiffResult:
    """
    Результат сравнения (diff).

    Attributes:
        object_type: Тип объектов (interfaces, ip_addresses, devices)
        target: Целевой объект (имя устройства, site)
        creates: Объекты для создания
        updates: Объекты для обновления
        deletes: Объекты для удаления
        skips: Пропущенные объекты
    """
    object_type: str
    target: str = ""
    creates: List[ObjectChange] = field(default_factory=list)
    updates: List[ObjectChange] = field(default_factory=list)
    deletes: List[ObjectChange] = field(default_factory=list)
    skips: List[ObjectChange] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        """Общее количество изменений."""
        return len(self.creates) + len(self.updates) + len(self.deletes)

    @property
    def has_changes(self) -> bool:
        """Есть ли изменения."""
        return self.total_changes > 0

    def summary(self) -> str:
        """Краткая сводка изменений."""
        parts = []
        if self.creates:
            parts.append(f"+{len(self.creates)} new")
        if self.updates:
            parts.append(f"~{len(self.updates)} update")
        if self.deletes:
            parts.append(f"-{len(self.deletes)} delete")
        if self.skips:
            parts.append(f"={len(self.skips)} skip")

        if not parts:
            return f"{self.object_type}: no changes"

        return f"{self.object_type}: {', '.join(parts)}"

    def format_detailed(self, show_skips: bool = False) -> str:
        """
        Детальный вывод изменений.

        Args:
            show_skips: Показывать пропущенные объекты

        Returns:
            str: Форматированный вывод
        """
        lines = [self.summary(), ""]

        if self.creates:
            lines.append("CREATE:")
            for obj in self.creates:
                lines.append(f"  {obj}")

        if self.updates:
            lines.append("UPDATE:")
            for obj in self.updates:
                lines.append(f"  {obj}")

        if self.deletes:
            lines.append("DELETE:")
            for obj in self.deletes:
                lines.append(f"  {obj}")

        if show_skips and self.skips:
            lines.append("SKIP:")
            for obj in self.skips:
                lines.append(f"  {obj}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "object_type": self.object_type,
            "target": self.target,
            "summary": {
                "creates": len(self.creates),
                "updates": len(self.updates),
                "deletes": len(self.deletes),
                "skips": len(self.skips),
            },
            "creates": [c.to_dict() for c in self.creates],
            "updates": [c.to_dict() for c in self.updates],
            "deletes": [c.to_dict() for c in self.deletes],
        }


class DiffCalculator:
    """
    Калькулятор diff для NetBox.

    Сравнивает собранные данные с текущим состоянием в NetBox
    и показывает что будет изменено.

    Example:
        calc = DiffCalculator(client)
        diff = calc.diff_interfaces("switch-01", interfaces)
        print(diff.format_detailed())
    """

    def __init__(self, client):
        """
        Инициализация.

        Args:
            client: NetBoxClient
        """
        self.client = client

    def diff_interfaces(
        self,
        device_name: str,
        interfaces: List[Dict[str, Any]],
        create_missing: bool = True,
        update_existing: bool = True,
    ) -> DiffResult:
        """
        Сравнивает интерфейсы с NetBox.

        Args:
            device_name: Имя устройства
            interfaces: Собранные интерфейсы
            create_missing: Учитывать создание новых
            update_existing: Учитывать обновление существующих

        Returns:
            DiffResult: Результат сравнения
        """
        result = DiffResult(object_type="interfaces", target=device_name)

        # Загружаем exclude_interfaces из конфига
        sync_cfg = get_sync_config("interfaces")
        exclude_patterns = sync_cfg.get_option("exclude_interfaces", [])

        # Получаем устройство
        device = self.client.get_device_by_name(device_name)
        if not device:
            logger.warning(f"Устройство не найдено: {device_name}")
            return result

        # Получаем существующие интерфейсы
        existing = {
            intf.name: intf
            for intf in self.client.get_interfaces(device_id=device.id)
        }

        for intf_data in interfaces:
            intf_name = intf_data.get("interface", intf_data.get("name", ""))
            if not intf_name:
                continue

            # Проверяем exclude patterns
            if self._is_excluded(intf_name, exclude_patterns):
                result.skips.append(ObjectChange(
                    name=intf_name,
                    change_type=ChangeType.SKIP,
                    reason="excluded by pattern",
                ))
                continue

            if intf_name in existing:
                # Существует — проверяем нужно ли обновление
                if update_existing:
                    changes = self._compare_interface(existing[intf_name], intf_data)
                    if changes:
                        result.updates.append(ObjectChange(
                            name=intf_name,
                            change_type=ChangeType.UPDATE,
                            changes=changes,
                        ))
                    else:
                        result.skips.append(ObjectChange(
                            name=intf_name,
                            change_type=ChangeType.SKIP,
                            reason="no changes",
                        ))
                else:
                    result.skips.append(ObjectChange(
                        name=intf_name,
                        change_type=ChangeType.SKIP,
                        reason="update_existing=False",
                    ))
            else:
                # Новый
                if create_missing:
                    result.creates.append(ObjectChange(
                        name=intf_name,
                        change_type=ChangeType.CREATE,
                    ))
                else:
                    result.skips.append(ObjectChange(
                        name=intf_name,
                        change_type=ChangeType.SKIP,
                        reason="create_missing=False",
                    ))

        return result

    def _is_excluded(self, name: str, patterns: List[str]) -> bool:
        """Проверяет исключён ли интерфейс по паттернам."""
        for pattern in patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return True
        return False

    def _compare_interface(
        self,
        existing,
        new_data: Dict[str, Any],
    ) -> List[FieldChange]:
        """Сравнивает существующий интерфейс с новыми данными."""
        changes = []

        # Читаем enabled_mode из конфига
        sync_cfg = get_sync_config("interfaces")
        enabled_mode = sync_cfg.get_option("enabled_mode", "admin")

        # Description
        new_desc = new_data.get("description", "")
        if new_desc and new_desc != (existing.description or ""):
            changes.append(FieldChange(
                field="description",
                old_value=existing.description or "",
                new_value=new_desc,
            ))

        # Enabled/Status
        # enabled_mode="admin": disabled/error = выключен, up/down = включён
        # enabled_mode="link": только up = включён, остальное = выключен
        new_status = new_data.get("status", "")
        if new_status:
            status_lower = new_status.lower()
            if enabled_mode == "link":
                new_enabled = status_lower == "up"
            else:  # admin mode
                new_enabled = status_lower not in ("disabled", "error")
            if new_enabled != existing.enabled:
                changes.append(FieldChange(
                    field="enabled",
                    old_value=existing.enabled,
                    new_value=new_enabled,
                ))

        # Mode
        new_mode = new_data.get("mode", "")
        current_mode = getattr(existing.mode, 'value', None) if existing.mode else None
        if new_mode and new_mode != current_mode:
            changes.append(FieldChange(
                field="mode",
                old_value=current_mode,
                new_value=new_mode,
            ))

        return changes

    def diff_ip_addresses(
        self,
        device_name: str,
        ip_data: List[Dict[str, Any]],
    ) -> DiffResult:
        """
        Сравнивает IP-адреса с NetBox.

        Args:
            device_name: Имя устройства
            ip_data: Собранные IP-адреса

        Returns:
            DiffResult: Результат сравнения
        """
        result = DiffResult(object_type="ip_addresses", target=device_name)

        # Получаем устройство
        device = self.client.get_device_by_name(device_name)
        if not device:
            return result

        # Получаем существующие IP
        existing_ips = set()
        for ip in self.client.get_ip_addresses(device_id=device.id):
            if ip.address:
                ip_only = str(ip.address).split("/")[0]
                existing_ips.add(ip_only)

        for entry in ip_data:
            ip_address = entry.get("ip_address", "")
            if not ip_address:
                continue

            ip_only = ip_address.split("/")[0]

            if ip_only in existing_ips:
                result.skips.append(ObjectChange(
                    name=ip_only,
                    change_type=ChangeType.SKIP,
                    reason="already exists",
                ))
            else:
                result.creates.append(ObjectChange(
                    name=ip_only,
                    change_type=ChangeType.CREATE,
                ))

        return result

    def diff_devices(
        self,
        inventory_data: List[Dict[str, Any]],
        site: str = "",
        update_existing: bool = True,
    ) -> DiffResult:
        """
        Сравнивает устройства с NetBox.

        Args:
            inventory_data: Данные инвентаризации
            site: Сайт
            update_existing: Учитывать обновление

        Returns:
            DiffResult: Результат сравнения
        """
        result = DiffResult(object_type="devices", target=site)

        for entry in inventory_data:
            name = entry.get("name", entry.get("hostname", ""))
            if not name:
                continue

            existing = self.client.get_device_by_name(name)
            if existing:
                if update_existing:
                    changes = self._compare_device(existing, entry)
                    if changes:
                        result.updates.append(ObjectChange(
                            name=name,
                            change_type=ChangeType.UPDATE,
                            changes=changes,
                        ))
                    else:
                        result.skips.append(ObjectChange(
                            name=name,
                            change_type=ChangeType.SKIP,
                            reason="no changes",
                        ))
                else:
                    result.skips.append(ObjectChange(
                        name=name,
                        change_type=ChangeType.SKIP,
                        reason="already exists",
                    ))
            else:
                result.creates.append(ObjectChange(
                    name=name,
                    change_type=ChangeType.CREATE,
                ))

        return result

    def _compare_device(
        self,
        existing,
        new_data: Dict[str, Any],
    ) -> List[FieldChange]:
        """Сравнивает существующее устройство с новыми данными."""
        changes = []

        # Serial
        new_serial = (new_data.get("serial", "") or "").strip()
        current_serial = (existing.serial or "").strip()
        if new_serial and new_serial != current_serial:
            changes.append(FieldChange(
                field="serial",
                old_value=current_serial,
                new_value=new_serial,
            ))

        # Model
        new_model = (new_data.get("model", "") or "").strip()
        current_model = existing.device_type.model if existing.device_type else ""
        if new_model and new_model != "Unknown" and new_model != current_model:
            changes.append(FieldChange(
                field="model",
                old_value=current_model,
                new_value=new_model,
            ))

        return changes


def format_diff_table(diffs: List[DiffResult]) -> str:
    """
    Форматирует несколько diff результатов в таблицу.

    Args:
        diffs: Список DiffResult

    Returns:
        str: Форматированная таблица
    """
    lines = ["=" * 60]
    lines.append("DIFF SUMMARY")
    lines.append("=" * 60)

    total_creates = 0
    total_updates = 0
    total_deletes = 0

    for diff in diffs:
        lines.append(diff.summary())
        total_creates += len(diff.creates)
        total_updates += len(diff.updates)
        total_deletes += len(diff.deletes)

    lines.append("-" * 60)
    lines.append(f"TOTAL: +{total_creates} new, ~{total_updates} update, -{total_deletes} delete")
    lines.append("=" * 60)

    return "\n".join(lines)
