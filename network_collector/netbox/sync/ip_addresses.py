"""
Синхронизация IP-адресов с NetBox.

Mixin класс для sync_ip_addresses и связанных методов.
Использует batch API для оптимизации производительности.
"""

import logging
from typing import List, Dict, Any, Optional

from .base import (
    SyncBase, SyncComparator, IPAddressEntry, get_sync_config,
    NetBoxError, NetBoxValidationError, format_error_for_log, logger,
)

logger = logging.getLogger(__name__)


class IPAddressesSyncMixin:
    """Mixin для синхронизации IP-адресов."""

    def sync_ip_addresses(
        self: SyncBase,
        device_name: str,
        ip_data: List[IPAddressEntry],
        device_ip: Optional[str] = None,
        update_existing: bool = False,
        cleanup: bool = False,
    ) -> Dict[str, int]:
        """
        Синхронизирует IP-адреса устройства с NetBox.

        Использует batch API для create/delete.
        При ошибке batch — fallback на поштучные операции.

        Args:
            device_name: Имя устройства в NetBox
            ip_data: Список IP-адресов (IPAddressEntry модели)
            device_ip: IP-адрес подключения (будет установлен как primary_ip4)
            update_existing: Обновлять существующие IP
            cleanup: Удалять IP-адреса из NetBox которых нет на устройстве

        Returns:
            Dict: Статистика {created, updated, deleted, skipped, failed}
        """
        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0}
        details = {"create": [], "update": [], "delete": [], "skip": []}

        device = self.client.get_device_by_name(device_name)
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            stats["failed"] = 1
            stats["errors"] = [f"Device not found in NetBox: {device_name}"]
            return stats

        interfaces = {
            intf.name: intf for intf in self.client.get_interfaces(device_id=device.id)
        }

        existing_ips = list(self.client.get_ip_addresses(device_id=device.id))
        entries = IPAddressEntry.ensure_list(ip_data)

        comparator = SyncComparator()
        local_data = [entry.to_dict() for entry in entries if entry.ip_address]
        diff = comparator.compare_ip_addresses(
            local=local_data,
            remote=existing_ips,
            create_missing=True,
            update_existing=update_existing,
            cleanup=cleanup,
        )

        # === BATCH CREATE ===
        self._batch_create_ip_addresses(
            device, diff.to_create, entries, interfaces, stats, details
        )

        # Update — поштучно (т.к. может требовать пересоздание IP при смене маски)
        for item in diff.to_update:
            entry = next(
                (e for e in entries if e.ip_address and e.ip_address.split("/")[0] == item.name),
                None
            )
            if entry and item.remote_data:
                intf = self._find_interface(device.id, entry.interface)
                if intf:
                    updated = self._update_ip_address(
                        item.remote_data, device, intf, entry, item.changes
                    )
                    if updated:
                        stats["updated"] += 1
                        changes = [str(c) for c in item.changes]
                        details["update"].append({
                            "address": entry.with_prefix,
                            "interface": entry.interface,
                            "changes": changes,
                        })
                    else:
                        stats["skipped"] += 1

        # === BATCH DELETE ===
        self._batch_delete_ip_addresses(diff.to_delete, stats, details)

        stats["skipped"] += len(diff.to_skip)

        # Установка primary IP (работает и в dry_run)
        if device_ip:
            device = self.client.get_device_by_name(device_name)
            if device:
                primary_set = self._set_primary_ip(device, device_ip)
                if primary_set:
                    details["primary_ip"] = {"address": device_ip, "device": device_name}

        logger.info(
            f"Синхронизация IP {device_name}: создано={stats['created']}, "
            f"обновлено={stats['updated']}, удалено={stats['deleted']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        stats["details"] = details
        return stats

    # ==================== BATCH ОПЕРАЦИИ ====================

    def _batch_create_ip_addresses(
        self: SyncBase,
        device,
        to_create: list,
        entries: list,
        interfaces: dict,
        stats: dict,
        details: dict,
    ) -> None:
        """Batch создание IP-адресов."""
        if not to_create:
            return

        # Собираем данные для batch create
        create_batch = []  # (data_dict, ip_with_mask, interface_name)

        for item in to_create:
            entry = next(
                (e for e in entries if e.ip_address and e.ip_address.split("/")[0] == item.name),
                None
            )
            if not entry:
                continue

            interface_name = entry.interface
            ip_with_mask = entry.with_prefix

            intf = self._find_interface(device.id, interface_name)
            if not intf:
                normalized_name = self._normalize_interface_name(interface_name)
                for name, i in interfaces.items():
                    if self._normalize_interface_name(name) == normalized_name:
                        intf = i
                        break

            if not intf:
                logger.warning(f"Интерфейс не найден: {device.name}:{interface_name}")
                stats["failed"] += 1
                continue

            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание IP: {ip_with_mask} на {interface_name}")
                stats["created"] += 1
                details["create"].append({"address": ip_with_mask, "interface": interface_name})
                continue

            # Подготавливаем данные для создания
            data = {
                "address": ip_with_mask,
                "status": "active",
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": intf.id,
            }
            if hasattr(device, 'tenant') and device.tenant:
                data['tenant'] = device.tenant.id
            if hasattr(intf, 'description') and intf.description:
                data['description'] = intf.description

            create_batch.append((data, ip_with_mask, interface_name))

        if not create_batch or self.dry_run:
            return

        # Batch create
        batch_data = [data for data, _, _ in create_batch]
        try:
            self.client.bulk_create_ip_addresses(batch_data)
            for _, ip_with_mask, interface_name in create_batch:
                logger.info(f"Создан IP: {ip_with_mask} на {device.name}:{interface_name}")
                stats["created"] += 1
                details["create"].append({"address": ip_with_mask, "interface": interface_name})
        except Exception as e:
            logger.warning(f"Batch create IP не удался ({e}), fallback на поштучное создание")
            # Fallback: создаём по одному
            for data, ip_with_mask, interface_name in create_batch:
                try:
                    self.client.api.ipam.ip_addresses.create(data)
                    logger.info(f"Создан IP: {ip_with_mask} на {device.name}:{interface_name}")
                    stats["created"] += 1
                    details["create"].append({"address": ip_with_mask, "interface": interface_name})
                except NetBoxValidationError as exc:
                    logger.error(f"Ошибка валидации IP {ip_with_mask}: {format_error_for_log(exc)}")
                    stats["failed"] += 1
                except NetBoxError as exc:
                    logger.error(f"Ошибка NetBox создания IP {ip_with_mask}: {format_error_for_log(exc)}")
                    stats["failed"] += 1
                except Exception as exc:
                    logger.error(f"Неизвестная ошибка создания IP {ip_with_mask}: {exc}")
                    stats["failed"] += 1

    def _batch_delete_ip_addresses(
        self: SyncBase,
        to_delete: list,
        stats: dict,
        details: dict,
    ) -> None:
        """Batch удаление IP-адресов."""
        if not to_delete:
            return

        if self.dry_run:
            for item in to_delete:
                address = str(item.remote_data.address) if hasattr(item.remote_data, 'address') else str(item.remote_data)
                logger.info(f"[DRY-RUN] Удаление IP: {address}")
                stats["deleted"] += 1
                details["delete"].append({"address": address})
            return

        # Собираем ID и адреса для удаления
        delete_ids = []
        delete_addresses = []
        delete_items = []
        for item in to_delete:
            address = str(item.remote_data.address) if hasattr(item.remote_data, 'address') else str(item.remote_data)
            if hasattr(item.remote_data, 'id'):
                delete_ids.append(item.remote_data.id)
                delete_addresses.append(address)
                delete_items.append(item)

        if not delete_ids:
            return

        try:
            self.client.bulk_delete_ip_addresses(delete_ids)
            for address in delete_addresses:
                logger.info(f"Удалён IP: {address}")
                stats["deleted"] += 1
                details["delete"].append({"address": address})
        except Exception as e:
            logger.warning(f"Batch delete IP не удался ({e}), fallback на поштучное удаление")
            for item in delete_items:
                address = str(item.remote_data.address) if hasattr(item.remote_data, 'address') else str(item.remote_data)
                try:
                    self._delete_ip_address(item.remote_data)
                    stats["deleted"] += 1
                    details["delete"].append({"address": address})
                except Exception as exc:
                    logger.error(f"Ошибка удаления IP {address}: {exc}")

    # ==================== LEGACY (для fallback и update) ====================

    def _delete_ip_address(self: SyncBase, ip_obj) -> None:
        """Удаляет IP-адрес из NetBox."""
        address = str(ip_obj.address) if hasattr(ip_obj, 'address') else str(ip_obj)

        if self.dry_run:
            logger.info(f"[DRY-RUN] Удаление IP: {address}")
            return

        try:
            ip_obj.delete()
            logger.info(f"Удалён IP: {address}")
        except Exception as e:
            logger.error(f"Ошибка удаления IP {address}: {e}")

    def _update_ip_address(
        self: SyncBase, ip_obj, device, interface, entry=None, changes=None
    ) -> bool:
        """
        Обновляет существующий IP-адрес.

        Если изменилась маска (prefix_length) - пересоздаёт IP,
        т.к. NetBox не позволяет изменить маску напрямую.
        """
        changes = changes or []

        # Проверяем изменение маски - требуется пересоздание IP
        prefix_change = next((c for c in changes if c.field == "prefix_length"), None)
        if prefix_change and entry:
            old_address = str(ip_obj.address)
            new_address = entry.with_prefix

            if self.dry_run:
                logger.info(
                    f"[DRY-RUN] Пересоздание IP: {old_address} → {new_address} "
                    f"(маска: /{prefix_change.old_value} → /{prefix_change.new_value})"
                )
                return True

            try:
                new_ip_data = {
                    "address": new_address,
                    "status": "active",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": interface.id,
                }

                if hasattr(device, 'tenant') and device.tenant:
                    new_ip_data['tenant'] = device.tenant.id
                if hasattr(interface, 'description') and interface.description:
                    new_ip_data['description'] = interface.description

                ip_obj.delete()
                logger.debug(f"Удалён старый IP: {old_address}")

                new_ip = self.client.api.ipam.ip_addresses.create(new_ip_data)
                logger.info(
                    f"Пересоздан IP: {old_address} → {new_address} "
                    f"(маска: /{prefix_change.old_value} → /{prefix_change.new_value})"
                )

                return True

            except NetBoxError as e:
                logger.error(f"Ошибка пересоздания IP {old_address}: {format_error_for_log(e)}")
                return False
            except Exception as e:
                logger.error(f"Неизвестная ошибка пересоздания IP {old_address}: {e}")
                return False

        # Обычное обновление (без изменения маски)
        updates = {}

        if hasattr(device, 'tenant') and device.tenant:
            current_tenant = getattr(ip_obj, 'tenant', None)
            current_tenant_id = current_tenant.id if current_tenant else None
            if current_tenant_id != device.tenant.id:
                updates['tenant'] = device.tenant.id

        if hasattr(interface, 'description') and interface.description:
            current_desc = getattr(ip_obj, 'description', '') or ''
            if current_desc != interface.description:
                updates['description'] = interface.description

        if hasattr(interface, 'id'):
            current_intf = getattr(ip_obj, 'assigned_object_id', None)
            if current_intf != interface.id:
                updates['assigned_object_type'] = 'dcim.interface'
                updates['assigned_object_id'] = interface.id

        if not updates:
            return False

        if self.dry_run:
            logger.info(f"[DRY-RUN] Обновление IP {ip_obj.address}: {updates}")
            return True

        try:
            ip_obj.update(updates)
            logger.info(f"Обновлён IP {ip_obj.address}: {list(updates.keys())}")
            return True
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox обновления IP {ip_obj.address}: {format_error_for_log(e)}")
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка обновления IP {ip_obj.address}: {e}")
            return False

    def _set_primary_ip(self: SyncBase, device, ip_address: str) -> bool:
        """
        Устанавливает primary IP для устройства.

        Returns:
            bool: True если primary IP был установлен (или будет в dry_run)
        """
        if not ip_address:
            return False

        ip_only = ip_address.split("/")[0]

        if device.primary_ip4:
            current_ip = str(device.primary_ip4.address).split("/")[0]
            if current_ip == ip_only:
                logger.debug(f"Primary IP уже установлен: {ip_only}")
                return False

        if "/" in ip_address:
            ip_with_mask = ip_address
        else:
            ip_with_mask = f"{ip_only}/32"

        try:
            # Сначала ищем IP на интерфейсах устройства
            ip_obj = None
            device_ips = list(self.client.get_ip_addresses(device_id=device.id))
            for ip in device_ips:
                if str(ip.address).split("/")[0] == ip_only:
                    ip_obj = ip
                    break

            # Если не найден на устройстве, ищем глобально
            if not ip_obj:
                ip_obj = self.client.api.ipam.ip_addresses.get(address=ip_only)

            if not ip_obj:
                if self.dry_run:
                    logger.info(f"[DRY-RUN] Создание IP {ip_with_mask} для {device.name}")
                else:
                    mgmt_interface = self._find_management_interface(device.id, ip_only)

                    ip_data = {"address": ip_with_mask}

                    if mgmt_interface:
                        ip_data["assigned_object_type"] = "dcim.interface"
                        ip_data["assigned_object_id"] = mgmt_interface.id
                        logger.debug(f"Привязка IP {ip_with_mask} к интерфейсу {mgmt_interface.name}")
                    else:
                        logger.debug(f"Management интерфейс не найден, IP {ip_with_mask} без привязки")

                    ip_obj = self.client.api.ipam.ip_addresses.create(ip_data)
                    logger.info(f"Создан IP {ip_with_mask} для устройства {device.name}")

            if ip_obj and not self.dry_run:
                device.primary_ip4 = ip_obj.id
                device.save()
                logger.info(f"Установлен primary IP {ip_only} для {device.name}")
                return True
            elif self.dry_run:
                logger.info(f"[DRY-RUN] Установка primary IP {ip_only} для {device.name}")
                return True

        except NetBoxError as e:
            logger.warning(f"Ошибка NetBox установки primary IP {ip_address}: {format_error_for_log(e)}")
            return False
        except Exception as e:
            logger.warning(f"Неизвестная ошибка установки primary IP {ip_address}: {e}")
            return False

        return False

    def _find_management_interface(self: SyncBase, device_id: int, target_ip: str = "") -> Optional[Any]:
        """Ищет management интерфейс устройства для привязки IP."""
        interfaces = self.client.get_interfaces(device_id=device_id)
        interfaces_by_name = {intf.name.lower(): intf for intf in interfaces}

        if target_ip:
            ip_only = target_ip.split("/")[0]
            for intf in interfaces:
                intf_ips = self.client.get_ip_addresses(interface_id=intf.id)
                for ip in intf_ips:
                    if str(ip.address).split("/")[0] == ip_only:
                        return intf

        mgmt_names = [
            "Management1", "Management0", "Mgmt0", "mgmt0",
        ]

        for name in mgmt_names:
            if name.lower() in interfaces_by_name:
                return interfaces_by_name[name.lower()]

        for intf in interfaces:
            name_lower = intf.name.lower()
            if name_lower.startswith("vlan") and name_lower != "vlan1":
                return intf

        return None
