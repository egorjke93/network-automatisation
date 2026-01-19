"""
Синхронизация интерфейсов с NetBox.

Mixin класс для sync_interfaces и связанных методов.
"""

import logging
from typing import List, Dict, Any, Optional

from .base import (
    SyncBase, SyncComparator, Interface, get_sync_config,
    normalize_mac_netbox, get_netbox_interface_type, logger,
)

logger = logging.getLogger(__name__)


class InterfacesSyncMixin:
    """Mixin для синхронизации интерфейсов."""

    def sync_interfaces(
        self: SyncBase,
        device_name: str,
        interfaces: List[Interface],
        create_missing: Optional[bool] = None,
        update_existing: Optional[bool] = None,
        cleanup: bool = False,
    ) -> Dict[str, Any]:
        """
        Синхронизирует интерфейсы устройства.

        Args:
            device_name: Имя устройства в NetBox
            interfaces: Список интерфейсов (Interface модели)
            create_missing: Создавать отсутствующие (None = из config)
            update_existing: Обновлять существующие (None = из config)
            cleanup: Удалять интерфейсы из NetBox которых нет на устройстве

        Returns:
            Dict: Статистика {created, updated, deleted, skipped, details}
        """
        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
        details = {"create": [], "update": [], "delete": [], "skip": []}
        sync_cfg = get_sync_config("interfaces")

        if create_missing is None:
            create_missing = sync_cfg.get_option("create_missing", True)
        if update_existing is None:
            update_existing = sync_cfg.get_option("update_existing", True)

        device = self.client.get_device_by_name(device_name)
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            stats["failed"] = 1
            stats["errors"] = [f"Device not found in NetBox: {device_name}"]
            return stats

        existing = list(self.client.get_interfaces(device_id=device.id))
        exclude_patterns = sync_cfg.get_option("exclude_interfaces", [])
        interface_models = Interface.ensure_list(interfaces)

        def is_lag(intf: Interface) -> int:
            return 0 if intf.name.lower().startswith(("port-channel", "po")) else 1

        sorted_interfaces = sorted(interface_models, key=is_lag)

        comparator = SyncComparator()
        # Добавляем вычисленные поля в данные для сравнения
        local_data = []
        for intf in sorted_interfaces:
            if intf.name:
                data = intf.to_dict()
                if sync_cfg.get_option("auto_detect_type", True):
                    data["type"] = get_netbox_interface_type(interface=intf)
                # Парсим speed и duplex для сравнения
                if intf.speed:
                    data["speed"] = self._parse_speed(intf.speed)
                if intf.duplex:
                    data["duplex"] = self._parse_duplex(intf.duplex)
                local_data.append(data)

        enabled_mode = sync_cfg.get_option("enabled_mode", "admin")
        compare_fields = ["description", "enabled", "mode", "mtu", "duplex", "speed"]
        if sync_cfg.get_option("auto_detect_type", True):
            compare_fields.append("type")

        diff = comparator.compare_interfaces(
            local=local_data,
            remote=existing,
            exclude_patterns=exclude_patterns,
            create_missing=create_missing,
            update_existing=update_existing,
            cleanup=cleanup,
            enabled_mode=enabled_mode,
            compare_fields=compare_fields,
        )

        for item in diff.to_create:
            intf = next((i for i in sorted_interfaces if i.name == item.name), None)
            if intf:
                self._create_interface(device.id, intf)
                stats["created"] += 1
                details["create"].append({"name": item.name})

        for item in diff.to_update:
            intf = next((i for i in sorted_interfaces if i.name == item.name), None)
            if intf and item.remote_data:
                updated = self._update_interface(item.remote_data, intf)
                if updated:
                    stats["updated"] += 1
                    changes = [str(c) for c in item.changes]
                    details["update"].append({"name": item.name, "changes": changes})
                else:
                    stats["skipped"] += 1

        for item in diff.to_delete:
            self._delete_interface(item.remote_data)
            stats["deleted"] += 1
            details["delete"].append({"name": item.name})

        stats["skipped"] = len(diff.to_skip)

        logger.info(
            f"Синхронизация интерфейсов {device_name}: "
            f"создано={stats['created']}, обновлено={stats['updated']}, "
            f"удалено={stats['deleted']}, пропущено={stats['skipped']}"
        )

        stats["details"] = details
        return stats

    def _delete_interface(self: SyncBase, interface) -> None:
        """Удаляет интерфейс из NetBox."""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Удаление интерфейса: {interface.name}")
            return

        try:
            interface.delete()
            logger.info(f"Удалён интерфейс: {interface.name}")
        except Exception as e:
            logger.error(f"Ошибка удаления интерфейса {interface.name}: {e}")

    def _create_interface(
        self: SyncBase,
        device_id: int,
        intf: Interface,
    ) -> None:
        """Создаёт интерфейс в NetBox."""
        sync_cfg = get_sync_config("interfaces")

        if self.dry_run:
            logger.info(f"[DRY-RUN] Создание интерфейса: {intf.name}")
            return

        kwargs = {}
        if sync_cfg.is_field_enabled("description"):
            kwargs["description"] = intf.description
        if sync_cfg.is_field_enabled("enabled"):
            # disabled = administratively down, error = err-disabled
            # up/down = порт включён (down = нет линка, но порт активен)
            kwargs["enabled"] = intf.status not in ("disabled", "error")

        mac_to_assign = None
        if sync_cfg.is_field_enabled("mac_address") and intf.mac:
            sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
            if not (sync_mac_only_with_ip and not intf.ip_address):
                mac_to_assign = normalize_mac_netbox(intf.mac)

        if sync_cfg.is_field_enabled("mtu") and intf.mtu:
            kwargs["mtu"] = intf.mtu
        if sync_cfg.is_field_enabled("speed") and intf.speed:
            kwargs["speed"] = self._parse_speed(intf.speed)
        if sync_cfg.is_field_enabled("duplex") and intf.duplex:
            kwargs["duplex"] = self._parse_duplex(intf.duplex)

        if sync_cfg.is_field_enabled("mode") and intf.mode:
            kwargs["mode"] = intf.mode

        if intf.lag:
            lag_interface = self.client.get_interface_by_name(device_id, intf.lag)
            if lag_interface:
                kwargs["lag"] = lag_interface.id
                logger.debug(f"Привязка {intf.name} к LAG {intf.lag} (id={lag_interface.id})")
            else:
                logger.warning(f"LAG интерфейс {intf.lag} не найден для {intf.name}")

        interface = self.client.create_interface(
            device_id=device_id,
            name=intf.name,
            interface_type=get_netbox_interface_type(interface=intf),
            **kwargs,
        )

        if mac_to_assign and interface:
            self.client.assign_mac_to_interface(interface.id, mac_to_assign)

    def _update_interface(
        self: SyncBase,
        nb_interface,
        intf: Interface,
    ) -> bool:
        """
        Обновляет интерфейс в NetBox.

        Returns:
            bool: True если были реальные изменения
        """
        updates = {}
        sync_cfg = get_sync_config("interfaces")

        if sync_cfg.get_option("auto_detect_type", True):
            new_type = get_netbox_interface_type(interface=intf)
            current_type = getattr(nb_interface.type, 'value', None) if nb_interface.type else None
            if new_type and new_type != current_type:
                updates["type"] = new_type

        if sync_cfg.is_field_enabled("description"):
            if intf.description != nb_interface.description:
                updates["description"] = intf.description

        if sync_cfg.is_field_enabled("enabled"):
            # Режим определения enabled:
            # "admin" - по административному статусу (up/down = enabled)
            # "link" - по состоянию линка (только up = enabled)
            enabled_mode = sync_cfg.get_option("enabled_mode", "admin")
            if enabled_mode == "link":
                # Только up = enabled, всё остальное = disabled
                enabled = intf.status == "up"
            else:
                # admin: disabled/error = порт выключен, up/down = порт включён
                enabled = intf.status not in ("disabled", "error")
            if enabled != nb_interface.enabled:
                updates["enabled"] = enabled

        mac_to_assign = None
        if sync_cfg.is_field_enabled("mac_address") and intf.mac:
            sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
            if not (sync_mac_only_with_ip and not intf.ip_address):
                new_mac = normalize_mac_netbox(intf.mac)
                current_mac = self.client.get_interface_mac(nb_interface.id) if not self.dry_run else None
                if new_mac and new_mac.upper() != (current_mac or "").upper():
                    mac_to_assign = new_mac

        if sync_cfg.is_field_enabled("mtu") and intf.mtu:
            if intf.mtu != (nb_interface.mtu or 0):
                updates["mtu"] = intf.mtu

        if sync_cfg.is_field_enabled("speed") and intf.speed:
            new_speed = self._parse_speed(intf.speed)
            if new_speed and new_speed != (nb_interface.speed or 0):
                updates["speed"] = new_speed

        if sync_cfg.is_field_enabled("duplex") and intf.duplex:
            new_duplex = self._parse_duplex(intf.duplex)
            current_duplex = getattr(nb_interface.duplex, 'value', None) if nb_interface.duplex else None
            if new_duplex and new_duplex != current_duplex:
                updates["duplex"] = new_duplex

        if sync_cfg.is_field_enabled("mode") and intf.mode:
            current_mode = getattr(nb_interface.mode, 'value', None) if nb_interface.mode else None
            if intf.mode != current_mode:
                updates["mode"] = intf.mode

        if intf.lag:
            device_id = getattr(nb_interface.device, 'id', None) if nb_interface.device else None
            if device_id:
                lag_interface = self.client.get_interface_by_name(device_id, intf.lag)
                if lag_interface:
                    current_lag_id = getattr(nb_interface.lag, 'id', None) if nb_interface.lag else None
                    if lag_interface.id != current_lag_id:
                        updates["lag"] = lag_interface.id
                else:
                    logger.debug(f"LAG интерфейс {intf.lag} не найден в NetBox")

        if not updates and not mac_to_assign:
            logger.debug(f"  → нет изменений для интерфейса {nb_interface.name}")
            return False

        if self.dry_run:
            if updates:
                logger.info(f"[DRY-RUN] Обновление интерфейса {nb_interface.name}: {updates}")
            if mac_to_assign:
                logger.info(f"[DRY-RUN] Назначение MAC {mac_to_assign} на {nb_interface.name}")
            return True

        if updates:
            self.client.update_interface(nb_interface.id, **updates)

        if mac_to_assign:
            self.client.assign_mac_to_interface(nb_interface.id, mac_to_assign)

        return True
