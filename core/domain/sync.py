"""
Domain Layer для Sync операций.

Чистые функции сравнения данных - не зависят от внешних систем.
Используются для определения что нужно создать/обновить/удалить.

Пример использования:
    from network_collector.core.domain.sync import SyncComparator

    comparator = SyncComparator()
    diff = comparator.compare_interfaces(local_interfaces, remote_interfaces)

    print(f"To create: {len(diff.to_create)}")
    print(f"To update: {len(diff.to_update)}")
    print(f"To delete: {len(diff.to_delete)}")
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Callable, Tuple
from enum import Enum
import re


def get_cable_endpoints(cable: Any) -> Optional[Tuple[str, str]]:
    """
    Извлекает endpoints кабеля в нормализованном виде.

    Standalone функция для использования в domain и infrastructure слоях.

    Args:
        cable: NetBox cable object

    Returns:
        Tuple of sorted endpoints ("device:interface", "device:interface") or None
    """
    try:
        a_terms = cable.a_terminations if hasattr(cable, "a_terminations") else []
        b_terms = cable.b_terminations if hasattr(cable, "b_terminations") else []

        if not a_terms or not b_terms:
            return None

        a_term = a_terms[0] if isinstance(a_terms, list) else a_terms
        b_term = b_terms[0] if isinstance(b_terms, list) else b_terms

        a_device = getattr(a_term.device, "name", "") if hasattr(a_term, "device") else ""
        a_intf = getattr(a_term, "name", "")
        b_device = getattr(b_term.device, "name", "") if hasattr(b_term, "device") else ""
        b_intf = getattr(b_term, "name", "")

        if a_device and a_intf and b_device and b_intf:
            return tuple(sorted([f"{a_device}:{a_intf}", f"{b_device}:{b_intf}"]))
    except Exception:
        pass

    return None


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
class SyncItem:
    """
    Элемент для синхронизации.

    Attributes:
        name: Идентификатор (имя интерфейса, IP-адрес, и т.д.)
        change_type: Тип изменения (create/update/delete/skip)
        local_data: Данные с устройства (для create/update)
        remote_data: Данные из внешней системы (для update/delete)
        changes: Список изменённых полей (для update)
        reason: Причина пропуска (для skip)
    """
    name: str
    change_type: ChangeType
    local_data: Optional[Dict[str, Any]] = None
    remote_data: Optional[Any] = None
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
class SyncDiff:
    """
    Результат сравнения для синхронизации.

    Attributes:
        object_type: Тип объектов (interfaces, ip_addresses, cables)
        target: Целевой объект (имя устройства)
        to_create: Объекты для создания
        to_update: Объекты для обновления
        to_delete: Объекты для удаления
        to_skip: Пропущенные объекты
    """
    object_type: str
    target: str = ""
    to_create: List[SyncItem] = field(default_factory=list)
    to_update: List[SyncItem] = field(default_factory=list)
    to_delete: List[SyncItem] = field(default_factory=list)
    to_skip: List[SyncItem] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        """Общее количество изменений."""
        return len(self.to_create) + len(self.to_update) + len(self.to_delete)

    @property
    def has_changes(self) -> bool:
        """Есть ли изменения."""
        return self.total_changes > 0

    def summary(self) -> str:
        """Краткая сводка изменений."""
        parts = []
        if self.to_create:
            parts.append(f"+{len(self.to_create)} create")
        if self.to_update:
            parts.append(f"~{len(self.to_update)} update")
        if self.to_delete:
            parts.append(f"-{len(self.to_delete)} delete")
        if self.to_skip:
            parts.append(f"={len(self.to_skip)} skip")

        if not parts:
            return f"{self.object_type}: no changes"

        return f"{self.object_type}: {', '.join(parts)}"

    def format_detailed(self, show_skips: bool = False) -> str:
        """Детальный вывод изменений."""
        lines = [self.summary(), ""]

        if self.to_create:
            lines.append("CREATE:")
            for item in self.to_create:
                lines.append(f"  {item}")

        if self.to_update:
            lines.append("UPDATE:")
            for item in self.to_update:
                lines.append(f"  {item}")

        if self.to_delete:
            lines.append("DELETE:")
            for item in self.to_delete:
                lines.append(f"  {item}")

        if show_skips and self.to_skip:
            lines.append("SKIP:")
            for item in self.to_skip:
                lines.append(f"  {item}")

        return "\n".join(lines)


class SyncComparator:
    """
    Компаратор для синхронизации.

    Чистые функции сравнения - не зависят от внешних систем.
    Принимают локальные и удалённые данные, возвращают SyncDiff.

    Example:
        comparator = SyncComparator()

        # Сравнение интерфейсов
        diff = comparator.compare_interfaces(
            local=collected_interfaces,
            remote=netbox_interfaces,
            exclude_patterns=["Vlan1", "Null.*"],
        )

        # Использование результата
        for item in diff.to_delete:
            netbox_client.delete_interface(item.remote_data)
    """

    def compare_interfaces(
        self,
        local: List[Dict[str, Any]],
        remote: List[Any],
        exclude_patterns: Optional[List[str]] = None,
        create_missing: bool = True,
        update_existing: bool = True,
        cleanup: bool = False,
        compare_fields: Optional[List[str]] = None,
        enabled_mode: str = "admin",
    ) -> SyncDiff:
        """
        Сравнивает локальные интерфейсы с удалёнными.

        Args:
            local: Интерфейсы с устройства (list of dicts или Interface models)
            remote: Интерфейсы из внешней системы (NetBox objects)
            exclude_patterns: Паттерны для исключения интерфейсов
            create_missing: Включать в to_create отсутствующие
            update_existing: Включать в to_update изменённые
            cleanup: Включать в to_delete лишние в remote
            compare_fields: Поля для сравнения (default: description, enabled, mode)
            enabled_mode: Режим определения enabled ("admin" или "link")

        Returns:
            SyncDiff: Результат сравнения
        """
        diff = SyncDiff(object_type="interfaces")
        exclude_patterns = exclude_patterns or []
        compare_fields = compare_fields or ["description", "enabled", "mode"]

        # Нормализуем local в dict
        local_dict = {}
        for item in local:
            if hasattr(item, "to_dict"):
                item = item.to_dict()
            name = item.get("name") or item.get("interface", "")
            if name:
                local_dict[name] = item

        # Нормализуем remote в dict
        remote_dict = {}
        for item in remote:
            name = item.name if hasattr(item, "name") else item.get("name", "")
            if name:
                remote_dict[name] = item

        # Множество обработанных имён
        processed = set()

        # Проходим по локальным интерфейсам
        for name, local_data in local_dict.items():
            # Проверяем exclude patterns
            if self._is_excluded(name, exclude_patterns):
                diff.to_skip.append(SyncItem(
                    name=name,
                    change_type=ChangeType.SKIP,
                    local_data=local_data,
                    reason=f"excluded by pattern",
                ))
                processed.add(name)
                continue

            processed.add(name)

            if name in remote_dict:
                # Существует - проверяем обновление
                if update_existing:
                    changes = self._compare_interface_fields(
                        local_data, remote_dict[name], compare_fields, enabled_mode
                    )
                    if changes:
                        diff.to_update.append(SyncItem(
                            name=name,
                            change_type=ChangeType.UPDATE,
                            local_data=local_data,
                            remote_data=remote_dict[name],
                            changes=changes,
                        ))
                    else:
                        diff.to_skip.append(SyncItem(
                            name=name,
                            change_type=ChangeType.SKIP,
                            local_data=local_data,
                            remote_data=remote_dict[name],
                            reason="no changes",
                        ))
                else:
                    diff.to_skip.append(SyncItem(
                        name=name,
                        change_type=ChangeType.SKIP,
                        local_data=local_data,
                        remote_data=remote_dict[name],
                        reason="update_existing=False",
                    ))
            else:
                # Новый интерфейс
                if create_missing:
                    diff.to_create.append(SyncItem(
                        name=name,
                        change_type=ChangeType.CREATE,
                        local_data=local_data,
                    ))
                else:
                    diff.to_skip.append(SyncItem(
                        name=name,
                        change_type=ChangeType.SKIP,
                        local_data=local_data,
                        reason="create_missing=False",
                    ))

        # Проверяем что нужно удалить (есть в remote, нет в local)
        if cleanup:
            for name, remote_data in remote_dict.items():
                if name not in processed:
                    # Проверяем exclude patterns для удаления тоже
                    if self._is_excluded(name, exclude_patterns):
                        diff.to_skip.append(SyncItem(
                            name=name,
                            change_type=ChangeType.SKIP,
                            remote_data=remote_data,
                            reason="excluded by pattern",
                        ))
                    else:
                        diff.to_delete.append(SyncItem(
                            name=name,
                            change_type=ChangeType.DELETE,
                            remote_data=remote_data,
                        ))

        return diff

    def compare_ip_addresses(
        self,
        local: List[Dict[str, Any]],
        remote: List[Any],
        create_missing: bool = True,
        update_existing: bool = False,
        cleanup: bool = False,
    ) -> SyncDiff:
        """
        Сравнивает локальные IP-адреса с удалёнными.

        Args:
            local: IP-адреса с устройства
            remote: IP-адреса из внешней системы
            create_missing: Создавать отсутствующие
            update_existing: Обновлять существующие
            cleanup: Удалять лишние

        Returns:
            SyncDiff: Результат сравнения
        """
        diff = SyncDiff(object_type="ip_addresses")

        # Нормализуем local: извлекаем IP без маски как ключ
        local_dict = {}
        for item in local:
            if hasattr(item, "to_dict"):
                item = item.to_dict()
            ip = item.get("ip_address", "")
            if ip:
                ip_only = ip.split("/")[0]
                local_dict[ip_only] = item

        # Нормализуем remote
        remote_dict = {}
        for item in remote:
            addr = item.address if hasattr(item, "address") else item.get("address", "")
            if addr:
                ip_only = str(addr).split("/")[0]
                remote_dict[ip_only] = item

        processed = set()

        # Проходим по локальным IP
        for ip, local_data in local_dict.items():
            processed.add(ip)

            if ip in remote_dict:
                if update_existing:
                    changes = self._compare_ip_fields(local_data, remote_dict[ip])
                    if changes:
                        diff.to_update.append(SyncItem(
                            name=ip,
                            change_type=ChangeType.UPDATE,
                            local_data=local_data,
                            remote_data=remote_dict[ip],
                            changes=changes,
                        ))
                    else:
                        diff.to_skip.append(SyncItem(
                            name=ip,
                            change_type=ChangeType.SKIP,
                            local_data=local_data,
                            remote_data=remote_dict[ip],
                            reason="no changes",
                        ))
                else:
                    diff.to_skip.append(SyncItem(
                        name=ip,
                        change_type=ChangeType.SKIP,
                        local_data=local_data,
                        remote_data=remote_dict[ip],
                        reason="update_existing=False",
                    ))
            else:
                if create_missing:
                    diff.to_create.append(SyncItem(
                        name=ip,
                        change_type=ChangeType.CREATE,
                        local_data=local_data,
                    ))
                else:
                    diff.to_skip.append(SyncItem(
                        name=ip,
                        change_type=ChangeType.SKIP,
                        local_data=local_data,
                        reason="create_missing=False",
                    ))

        # Удаление лишних IP
        if cleanup:
            for ip, remote_data in remote_dict.items():
                if ip not in processed:
                    diff.to_delete.append(SyncItem(
                        name=ip,
                        change_type=ChangeType.DELETE,
                        remote_data=remote_data,
                    ))

        return diff

    def compare_cables(
        self,
        local: List[Dict[str, Any]],
        remote: List[Any],
        cleanup: bool = False,
    ) -> SyncDiff:
        """
        Сравнивает локальные кабели (из LLDP/CDP) с удалёнными.

        Args:
            local: Кабели из LLDP/CDP данных
            remote: Кабели из внешней системы
            cleanup: Удалять лишние

        Returns:
            SyncDiff: Результат сравнения
        """
        diff = SyncDiff(object_type="cables")

        # Нормализуем local: создаём ключ из endpoints
        local_set = set()
        local_dict = {}
        for item in local:
            if hasattr(item, "to_dict"):
                item = item.to_dict()
            # Ключ: (local_device:local_port, remote_device:remote_port) - sorted
            local_dev = item.get("hostname", "")
            local_port = item.get("local_interface", "")
            remote_dev = item.get("remote_hostname", "")
            remote_port = item.get("remote_port", "")

            if local_dev and local_port and remote_dev and remote_port:
                # Сортируем endpoints для уникальности (A-B = B-A)
                endpoints = tuple(sorted([
                    f"{local_dev}:{local_port}",
                    f"{remote_dev}:{remote_port}",
                ]))
                local_set.add(endpoints)
                local_dict[endpoints] = item

        # Нормализуем remote кабели
        remote_set = set()
        remote_dict = {}
        for cable in remote:
            endpoints = get_cable_endpoints(cable)
            if endpoints:
                remote_set.add(endpoints)
                remote_dict[endpoints] = cable

        # Новые кабели (в local, но не в remote)
        for endpoints in local_set - remote_set:
            diff.to_create.append(SyncItem(
                name=" <-> ".join(endpoints),
                change_type=ChangeType.CREATE,
                local_data=local_dict[endpoints],
            ))

        # Существующие (в обоих)
        for endpoints in local_set & remote_set:
            diff.to_skip.append(SyncItem(
                name=" <-> ".join(endpoints),
                change_type=ChangeType.SKIP,
                local_data=local_dict.get(endpoints),
                remote_data=remote_dict.get(endpoints),
                reason="already exists",
            ))

        # Удаление лишних (в remote, но не в local)
        if cleanup:
            for endpoints in remote_set - local_set:
                diff.to_delete.append(SyncItem(
                    name=" <-> ".join(endpoints),
                    change_type=ChangeType.DELETE,
                    remote_data=remote_dict[endpoints],
                ))

        return diff

    def _is_excluded(self, name: str, patterns: List[str]) -> bool:
        """Проверяет исключён ли интерфейс по паттернам."""
        for pattern in patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return True
        return False

    def _compare_interface_fields(
        self,
        local: Dict[str, Any],
        remote: Any,
        fields: List[str],
        enabled_mode: str = "admin",
    ) -> List[FieldChange]:
        """Сравнивает поля интерфейса."""
        changes = []

        for field_name in fields:
            local_val = self._get_local_field(local, field_name, enabled_mode)
            remote_val = self._get_remote_field(remote, field_name)

            if local_val is not None and local_val != remote_val:
                changes.append(FieldChange(
                    field=field_name,
                    old_value=remote_val,
                    new_value=local_val,
                ))

        return changes

    def _get_local_field(
        self, data: Dict[str, Any], field_name: str, enabled_mode: str = "admin"
    ) -> Any:
        """Получает значение поля из локальных данных."""
        if field_name == "enabled":
            # Режим определения enabled:
            # "admin" - по административному статусу (up/down = enabled)
            # "link" - по состоянию линка (только up = enabled)
            status = data.get("status", "")
            if status:
                if enabled_mode == "link":
                    # Только up = enabled, всё остальное = disabled
                    return status.lower() == "up"
                else:
                    # admin: disabled/error = порт выключен, up/down = порт включён
                    return status.lower() not in ("disabled", "error")
            return None
        elif field_name == "description":
            return data.get("description") or None
        elif field_name == "mode":
            return data.get("mode") or None
        elif field_name == "mtu":
            mtu = data.get("mtu")
            return int(mtu) if mtu else None
        elif field_name == "duplex":
            duplex = data.get("duplex", "")
            # Нормализация: "full" -> "full", "Full" -> "full", "auto" -> "auto"
            if duplex:
                return duplex.lower()
            return None
        else:
            return data.get(field_name)

    def _get_remote_field(self, remote: Any, field_name: str) -> Any:
        """Получает значение поля из удалённых данных."""
        if hasattr(remote, field_name):
            val = getattr(remote, field_name)
            # Для enum-like объектов извлекаем value
            if hasattr(val, "value"):
                return val.value
            return val
        elif isinstance(remote, dict):
            return remote.get(field_name)
        return None

    def _compare_ip_fields(
        self,
        local: Dict[str, Any],
        remote: Any,
    ) -> List[FieldChange]:
        """Сравнивает поля IP-адреса."""
        changes = []

        # Prefix length (маска)
        local_ip = local.get("ip_address", "")
        if "/" in local_ip:
            local_prefix = int(local_ip.split("/")[1])
        else:
            local_prefix = local.get("prefix_length", 24)

        remote_addr = getattr(remote, "address", "") if hasattr(remote, "address") else ""
        if "/" in str(remote_addr):
            remote_prefix = int(str(remote_addr).split("/")[1])
        else:
            remote_prefix = 32  # NetBox default

        if local_prefix != remote_prefix:
            changes.append(FieldChange(
                field="prefix_length",
                old_value=remote_prefix,
                new_value=local_prefix,
            ))

        # Description
        local_desc = local.get("description", "")
        remote_desc = getattr(remote, "description", "") if hasattr(remote, "description") else ""
        if local_desc and local_desc != (remote_desc or ""):
            changes.append(FieldChange(
                field="description",
                old_value=remote_desc or "",
                new_value=local_desc,
            ))

        return changes
