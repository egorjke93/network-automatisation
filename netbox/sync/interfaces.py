"""
Синхронизация интерфейсов с NetBox.

Mixin класс для sync_interfaces и связанных методов.
Использует batch API для оптимизации производительности.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

from .base import (
    SyncBase, SyncComparator, Interface, get_sync_config,
    normalize_mac_netbox, get_netbox_interface_type, logger,
)
from ...core.domain.vlan import parse_vlan_range, VlanSet

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

        Использует batch API для create/update/delete (один вызов на операцию).
        При ошибке batch — fallback на поштучные операции.

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
            # Fallback: если device_name похоже на IP, ищем устройство по IP
            device_ip = None
            if interfaces:
                # Пытаемся получить device_ip из первого интерфейса
                first_intf = interfaces[0] if isinstance(interfaces, list) else None
                if first_intf:
                    device_ip = first_intf.get("device_ip") if isinstance(first_intf, dict) else getattr(first_intf, "device_ip", None)
            # Или если device_name выглядит как IP
            if not device_ip and device_name and device_name.replace(".", "").isdigit():
                device_ip = device_name
            if device_ip:
                device = self.client.get_device_by_ip(device_ip)
                if device:
                    logger.info(f"Устройство найдено по IP {device_ip}: {device.name}")
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            stats["failed"] = 1
            stats["errors"] = [f"Device not found in NetBox: {device_name}"]
            return stats

        # Кэшируем site_name один раз — чтобы не делать GET /api/dcim/devices/{id}/
        # на каждом интерфейсе в _check_untagged_vlan (N+1 проблема)
        site_name = None
        if hasattr(device, 'site') and device.site:
            site_name = getattr(device.site, 'name', None)

        # Предзагружаем кэш VLAN для сайта (один API-запрос)
        if sync_cfg.get_option("sync_vlans", False) and site_name:
            self._get_vlan_by_vid(1, site_name)  # Форсирует загрузку всех VLAN сайта

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
                # Добавляем untagged_vlan для сравнения (access_vlan или native_vlan)
                if sync_cfg.get_option("sync_vlans", False):
                    if intf.mode == "access" and intf.access_vlan:
                        data["untagged_vlan"] = intf.access_vlan
                    elif intf.mode in ("tagged", "tagged-all") and intf.native_vlan:
                        data["untagged_vlan"] = intf.native_vlan
                local_data.append(data)

        enabled_mode = sync_cfg.get_option("enabled_mode", "admin")
        compare_fields = ["description", "enabled", "mode", "mtu", "duplex", "speed"]
        if sync_cfg.get_option("auto_detect_type", True):
            compare_fields.append("type")
        # Добавляем VLAN поля для сравнения если sync_vlans включен
        if sync_cfg.get_option("sync_vlans", False):
            compare_fields.extend(["untagged_vlan", "tagged_vlans"])

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

        # Логируем статистику diff для диагностики
        logger.debug(
            f"Diff для {device_name}: to_create={len(diff.to_create)}, "
            f"to_update={len(diff.to_update)}, to_delete={len(diff.to_delete)}, "
            f"to_skip={len(diff.to_skip)}"
        )

        # === BATCH CREATE ===
        self._batch_create_interfaces(
            device.id, diff.to_create, sorted_interfaces, stats, details,
            site_name=site_name,
        )

        # === BATCH UPDATE ===
        self._batch_update_interfaces(
            diff.to_update, sorted_interfaces, stats, details, site_name=site_name
        )

        # === BATCH DELETE ===
        self._batch_delete_interfaces(diff.to_delete, stats, details)

        stats["skipped"] += len(diff.to_skip)

        # Добавляем статистику по локальным/remote интерфейсам
        stats["local_count"] = len(sorted_interfaces)
        stats["remote_count"] = len(existing)

        logger.info(
            f"Синхронизация интерфейсов {device_name}: "
            f"создано={stats['created']}, обновлено={stats['updated']}, "
            f"удалено={stats['deleted']}, пропущено={stats['skipped']} "
            f"(локальных={stats['local_count']}, в NetBox={stats['remote_count']})"
        )

        stats["details"] = details
        return stats

    # ==================== BATCH ОПЕРАЦИИ ====================

    def _batch_create_interfaces(
        self: SyncBase,
        device_id: int,
        to_create: list,
        sorted_interfaces: List[Interface],
        stats: dict,
        details: dict,
        site_name: Optional[str] = None,
    ) -> None:
        """Batch создание интерфейсов.

        Создание разделено на две фазы:
        1. Сначала LAG интерфейсы (Port-channel/Po)
        2. Затем member интерфейсы (с привязкой к LAG)

        Это необходимо, т.к. при создании member интерфейса с полем lag
        нужно знать ID LAG-интерфейса, который должен уже существовать в NetBox.
        """
        if not to_create:
            return

        # Разделяем на LAG и остальные интерфейсы
        lag_items = []
        member_items = []
        for item in to_create:
            intf = next((i for i in sorted_interfaces if i.name == item.name), None)
            if not intf:
                logger.warning(f"Интерфейс {item.name} не найден в локальных данных")
                continue
            if intf.name.lower().startswith(("port-channel", "po")):
                lag_items.append((item, intf))
            else:
                member_items.append((item, intf))

        # Фаза 1: создаём LAG интерфейсы
        if lag_items:
            self._do_batch_create(device_id, lag_items, stats, details, sorted_interfaces, site_name=site_name)

        # Фаза 2: создаём остальные интерфейсы (теперь LAG существуют в NetBox)
        if member_items:
            self._do_batch_create(device_id, member_items, stats, details, sorted_interfaces, site_name=site_name)

    def _do_batch_create(
        self: SyncBase,
        device_id: int,
        items: List[Tuple],
        stats: dict,
        details: dict,
        sorted_interfaces: List[Interface],
        site_name: Optional[str] = None,
    ) -> None:
        """Выполняет batch create для списка интерфейсов."""
        create_batch = []
        create_mac_queue = []  # (batch_index, mac_address) для post-create
        create_names = []  # Имена для логов

        for item, intf in items:
            data, mac = self._build_create_data(device_id, intf, site_name=site_name)
            if data:
                create_batch.append(data)
                create_names.append(item.name)
                if mac:
                    create_mac_queue.append((len(create_batch) - 1, mac))

        if not create_batch:
            return

        if self.dry_run:
            for name in create_names:
                logger.info(f"[DRY-RUN] Создание интерфейса: {name}")
                stats["created"] += 1
                details["create"].append({"name": name})
            return

        # Batch create
        try:
            created = self.client.bulk_create_interfaces(create_batch)
            for i, name in enumerate(create_names):
                logger.info(f"Создан интерфейс: {name}")
                stats["created"] += 1
                details["create"].append({"name": name})

            # Post-create: назначаем MAC (отдельный endpoint, пока по одному)
            for idx, mac in create_mac_queue:
                if idx < len(created):
                    try:
                        self.client.assign_mac_to_interface(created[idx].id, mac)
                    except Exception as e:
                        logger.warning(f"Ошибка назначения MAC {mac}: {e}")

        except Exception as e:
            logger.warning(f"Batch create не удался ({e}), fallback на поштучное создание")
            # Fallback: создаём по одному
            for _item, intf in items:
                try:
                    self._create_interface(device_id, intf)
                    stats["created"] += 1
                    details["create"].append({"name": intf.name})
                except Exception as exc:
                    logger.error(f"Ошибка создания интерфейса {intf.name}: {exc}")

    def _batch_update_interfaces(
        self: SyncBase,
        to_update: list,
        sorted_interfaces: List[Interface],
        stats: dict,
        details: dict,
        site_name: Optional[str] = None,
    ) -> None:
        """Batch обновление интерфейсов."""
        if not to_update:
            return

        # Собираем данные для batch update
        update_batch = []  # Список (updates_with_id, name, changes)
        update_mac_queue = []  # (interface_id, mac_address, name) для post-update

        for item in to_update:
            intf = next((i for i in sorted_interfaces if i.name == item.name), None)
            if not intf or not item.remote_data:
                continue

            updates, actual_changes, mac = self._build_update_data(
                item.remote_data, intf, site_name=site_name
            )

            if not updates and not mac:
                logger.debug(f"  → нет изменений для интерфейса {item.remote_data.name}")
                stats["skipped"] += 1
                continue

            if self.dry_run:
                if updates:
                    logger.info(f"[DRY-RUN] Обновление интерфейса {item.remote_data.name}: {updates}")
                if mac:
                    logger.info(f"[DRY-RUN] Назначение MAC {mac} на {item.remote_data.name}")
                stats["updated"] += 1
                details["update"].append({"name": item.name, "changes": actual_changes})
                continue

            if updates:
                updates["id"] = item.remote_data.id
                update_batch.append((updates, item.name, actual_changes))

            if mac:
                update_mac_queue.append((item.remote_data.id, mac, item.name))

            # Если нет field updates но есть MAC — считаем updated (MAC обработается ниже)
            if not updates and mac:
                stats["updated"] += 1
                details["update"].append({"name": item.name, "changes": actual_changes})

        if self.dry_run:
            return

        # Batch update field changes
        if update_batch:
            batch_data = [upd for upd, _, _ in update_batch]
            try:
                self.client.bulk_update_interfaces(batch_data)
                for _, name, changes in update_batch:
                    logger.info(f"Обновлён интерфейс: {name}")
                    stats["updated"] += 1
                    details["update"].append({"name": name, "changes": changes})
            except Exception as e:
                logger.warning(f"Batch update не удался ({e}), fallback на поштучное обновление")
                for upd, name, changes in update_batch:
                    intf_id = upd.pop("id")
                    try:
                        self.client.update_interface(intf_id, **upd)
                        logger.info(f"Обновлён интерфейс: {name}")
                        stats["updated"] += 1
                        details["update"].append({"name": name, "changes": changes})
                    except Exception as exc:
                        logger.error(f"Ошибка обновления интерфейса {name}: {exc}")

        # Post-update: назначаем MAC
        for intf_id, mac, name in update_mac_queue:
            try:
                self.client.assign_mac_to_interface(intf_id, mac)
                logger.info(f"Назначен MAC: {mac} на {name}")
            except Exception as e:
                logger.warning(f"Ошибка назначения MAC {mac} на {name}: {e}")

    def _batch_delete_interfaces(
        self: SyncBase,
        to_delete: list,
        stats: dict,
        details: dict,
    ) -> None:
        """Batch удаление интерфейсов."""
        if not to_delete:
            return

        if self.dry_run:
            for item in to_delete:
                logger.info(f"[DRY-RUN] Удаление интерфейса: {item.name}")
                stats["deleted"] += 1
                details["delete"].append({"name": item.name})
            return

        delete_ids = []
        delete_names = []
        for item in to_delete:
            if item.remote_data:
                delete_ids.append(item.remote_data.id)
                delete_names.append(item.name)

        if not delete_ids:
            return

        self._batch_with_fallback(
            batch_data=delete_ids,
            item_names=delete_names,
            bulk_fn=self.client.bulk_delete_interfaces,
            fallback_fn=lambda item_id, name: self.client.api.dcim.interfaces.get(item_id).delete(),
            stats=stats, details=details,
            operation="deleted", entity_name="интерфейс",
        )

    # ==================== BUILD DATA (без API-вызовов) ====================

    def _build_create_data(
        self: SyncBase,
        device_id: int,
        intf: Interface,
        site_name: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Подготавливает данные для создания интерфейса (без API-вызовов).

        Returns:
            Tuple: (data_dict для API, mac_to_assign или None)
        """
        sync_cfg = get_sync_config("interfaces")

        data = {
            "device": device_id,
            "name": intf.name,
            "type": get_netbox_interface_type(interface=intf),
        }

        if sync_cfg.is_field_enabled("description"):
            data["description"] = intf.description
        if sync_cfg.is_field_enabled("enabled"):
            data["enabled"] = intf.status not in ("disabled", "error")

        mac_to_assign = None
        if sync_cfg.is_field_enabled("mac_address") and intf.mac:
            sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
            if not (sync_mac_only_with_ip and not intf.ip_address):
                mac_to_assign = normalize_mac_netbox(intf.mac)

        if sync_cfg.is_field_enabled("mtu") and intf.mtu:
            data["mtu"] = intf.mtu
        if sync_cfg.is_field_enabled("speed") and intf.speed:
            data["speed"] = self._parse_speed(intf.speed)
        if sync_cfg.is_field_enabled("duplex") and intf.duplex:
            data["duplex"] = self._parse_duplex(intf.duplex)

        if sync_cfg.is_field_enabled("mode") and intf.mode:
            data["mode"] = intf.mode

        if intf.lag:
            lag_interface = self.client.get_interface_by_name(device_id, intf.lag)
            if lag_interface:
                data["lag"] = lag_interface.id
                logger.debug(f"Привязка {intf.name} к LAG {intf.lag} (id={lag_interface.id})")
            else:
                logger.warning(f"LAG интерфейс {intf.lag} не найден для {intf.name}")

        # VLAN назначение при создании интерфейса
        if sync_cfg.get_option("sync_vlans", False):
            # Untagged VLAN (access_vlan для access, native_vlan для trunk)
            target_vid = None
            if intf.mode == "access" and intf.access_vlan:
                try:
                    target_vid = int(intf.access_vlan)
                except ValueError:
                    pass
            elif intf.mode in ("tagged", "tagged-all") and intf.native_vlan:
                try:
                    target_vid = int(intf.native_vlan)
                except ValueError:
                    pass

            if target_vid:
                vlan = self._get_vlan_by_vid(target_vid, site_name)
                if vlan:
                    data["untagged_vlan"] = vlan.id
                else:
                    logger.debug(f"VLAN {target_vid} не найден в NetBox при создании {intf.name}")

            # Tagged VLANs (trunk порты)
            if intf.mode == "tagged" and intf.tagged_vlans:
                target_vids = parse_vlan_range(intf.tagged_vlans)
                if target_vids:
                    tagged_ids = []
                    for vid in target_vids:
                        vlan = self._get_vlan_by_vid(vid, site_name)
                        if vlan:
                            tagged_ids.append(vlan.id)
                    if tagged_ids:
                        data["tagged_vlans"] = sorted(tagged_ids)

        return data, mac_to_assign

    # ==================== CHECK-хелперы для _build_update_data ====================

    def _check_type(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет тип интерфейса (auto-detect)."""
        if not sync_cfg.get_option("auto_detect_type", True):
            return
        new_type = get_netbox_interface_type(interface=intf)
        current_type = getattr(nb_interface.type, 'value', None) if nb_interface.type else None
        if new_type and new_type != current_type:
            updates["type"] = new_type
            actual_changes.append(f"type: {current_type} → {new_type}")

    def _check_description(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет описание интерфейса."""
        if sync_cfg.is_field_enabled("description"):
            if intf.description != nb_interface.description:
                updates["description"] = intf.description
                actual_changes.append(f"description: {nb_interface.description!r} → {intf.description!r}")

    def _check_enabled(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет состояние enabled (admin/link mode)."""
        if not sync_cfg.is_field_enabled("enabled"):
            return
        enabled_mode = sync_cfg.get_option("enabled_mode", "admin")
        if enabled_mode == "link":
            enabled = intf.status == "up"
        else:
            enabled = intf.status not in ("disabled", "error")
        if enabled != nb_interface.enabled:
            updates["enabled"] = enabled
            actual_changes.append(f"enabled: {nb_interface.enabled} → {enabled}")

    def _check_mac(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, actual_changes: List[str],
    ) -> Optional[str]:
        """Проверяет MAC-адрес. Возвращает mac_to_assign или None."""
        if not (sync_cfg.is_field_enabled("mac_address") and intf.mac):
            return None
        sync_mac_only_with_ip = sync_cfg.get_option("sync_mac_only_with_ip", False)
        if sync_mac_only_with_ip and not intf.ip_address:
            return None
        new_mac = normalize_mac_netbox(intf.mac)
        current_mac = self.client.get_interface_mac(nb_interface.id) if not self.dry_run else None
        if new_mac and new_mac.upper() != (current_mac or "").upper():
            actual_changes.append(f"mac: {current_mac} → {new_mac}")
            return new_mac
        return None

    def _check_mtu(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет MTU."""
        if sync_cfg.is_field_enabled("mtu") and intf.mtu:
            if intf.mtu != (nb_interface.mtu or 0):
                updates["mtu"] = intf.mtu
                actual_changes.append(f"mtu: {nb_interface.mtu} → {intf.mtu}")

    def _check_speed(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет скорость."""
        if sync_cfg.is_field_enabled("speed") and intf.speed:
            new_speed = self._parse_speed(intf.speed)
            if new_speed and new_speed != (nb_interface.speed or 0):
                updates["speed"] = new_speed
                actual_changes.append(f"speed: {nb_interface.speed} → {new_speed}")

    def _check_duplex(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет duplex."""
        if sync_cfg.is_field_enabled("duplex") and intf.duplex:
            new_duplex = self._parse_duplex(intf.duplex)
            current_duplex = getattr(nb_interface.duplex, 'value', None) if nb_interface.duplex else None
            if new_duplex and new_duplex != current_duplex:
                updates["duplex"] = new_duplex
                actual_changes.append(f"duplex: {current_duplex} → {new_duplex}")

    def _check_mode(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет режим порта (access/tagged)."""
        if not sync_cfg.is_field_enabled("mode"):
            return
        current_mode = getattr(nb_interface.mode, 'value', None) if nb_interface.mode else None
        if intf.mode and intf.mode != current_mode:
            updates["mode"] = intf.mode
            actual_changes.append(f"mode: {current_mode} → {intf.mode}")
        elif not intf.mode and current_mode:
            updates["mode"] = ""
            actual_changes.append(f"mode: {current_mode} → None")

    def _check_untagged_vlan(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
        site_name: Optional[str] = None,
    ) -> None:
        """Проверяет и обновляет untagged VLAN (access_vlan / native_vlan)."""
        if not (sync_cfg.is_field_enabled("untagged_vlan") and sync_cfg.get_option("sync_vlans", False)):
            return

        target_vid = None
        if intf.mode == "access" and intf.access_vlan:
            try:
                target_vid = int(intf.access_vlan)
            except ValueError:
                pass
        elif intf.mode in ("tagged", "tagged-all") and intf.native_vlan:
            try:
                target_vid = int(intf.native_vlan)
            except ValueError:
                pass

        # Получаем текущий VLAN без lazy-load pynetbox
        # .id доступен в brief response (не вызывает GET /api/ipam/vlans/{id}/)
        current_vlan_id = None
        current_vlan_vid = None
        if nb_interface.untagged_vlan:
            current_vlan_id = getattr(nb_interface.untagged_vlan, 'id', None)
            # VID из обратного кэша (без lazy-load), fallback на .vid
            if current_vlan_id:
                current_vlan_vid = self._vlan_id_to_vid.get(current_vlan_id)
            if current_vlan_vid is None:
                current_vlan_vid = getattr(nb_interface.untagged_vlan, 'vid', None)

        if target_vid:
            # site_name передаётся из sync_interfaces() — избегаем N+1 запросов
            # к GET /api/dcim/devices/{id}/ на каждом интерфейсе
            if site_name is None:
                # Fallback для legacy-вызовов (напр. _update_interface)
                device = nb_interface.device
                if device and hasattr(device, 'site') and device.site:
                    site_name = getattr(device.site, 'name', None)

            vlan = self._get_vlan_by_vid(target_vid, site_name)
            if vlan:
                if vlan.id != current_vlan_id:
                    updates["untagged_vlan"] = vlan.id
                    actual_changes.append(f"untagged_vlan: {current_vlan_vid} → {target_vid}")
            else:
                logger.debug(f"VLAN {target_vid} не найден в NetBox (site={site_name})")
        elif current_vlan_id:
            updates["untagged_vlan"] = None
            actual_changes.append(f"untagged_vlan: {current_vlan_vid} → None")

    def _check_tagged_vlans(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
        site_name: Optional[str] = None,
    ) -> None:
        """Проверяет и обновляет tagged VLANs (trunk порты)."""
        if not (sync_cfg.is_field_enabled("tagged_vlans") and sync_cfg.get_option("sync_vlans", False)):
            return

        if intf.mode == "tagged" and intf.tagged_vlans:
            target_vids = parse_vlan_range(intf.tagged_vlans)
            logger.debug(
                f"  {nb_interface.name}: tagged_vlans='{intf.tagged_vlans}' -> parsed={target_vids}"
            )

            if target_vids:
                # site_name передаётся из sync_interfaces() — избегаем N+1 запросов
                if site_name is None:
                    device = nb_interface.device
                    if device and hasattr(device, 'site') and device.site:
                        site_name = getattr(device.site, 'name', None)

                target_vlan_ids = []
                matched_vids = []
                not_found_vids = []
                for vid in target_vids:
                    vlan = self._get_vlan_by_vid(vid, site_name)
                    if vlan:
                        target_vlan_ids.append(vlan.id)
                        matched_vids.append(vid)
                    else:
                        not_found_vids.append(vid)

                if not_found_vids:
                    if len(not_found_vids) > 10:
                        logger.debug(
                            f"  {nb_interface.name}: {len(not_found_vids)} VLANs не найдены в NetBox"
                        )
                    else:
                        logger.debug(
                            f"  {nb_interface.name}: VLANs {not_found_vids} не найдены в NetBox"
                        )

                current = VlanSet.from_vlan_objects(nb_interface.tagged_vlans)
                target = VlanSet.from_ids(matched_vids)

                if current != target:
                    updates["tagged_vlans"] = sorted(target_vlan_ids)
                    added = target.added(current)
                    removed = target.removed(current)
                    parts = []
                    if added:
                        parts.append(f"+{sorted(added)}")
                    if removed:
                        parts.append(f"-{sorted(removed)}")
                    change_detail = ", ".join(parts) if parts else "изменено"
                    actual_changes.append(f"tagged_vlans: {change_detail}")

        elif intf.mode != "tagged":
            current = VlanSet.from_vlan_objects(nb_interface.tagged_vlans)
            if current:
                updates["tagged_vlans"] = []
                actual_changes.append(f"tagged_vlans: -{current.sorted_list}")

    def _check_lag(
        self: SyncBase, nb_interface, intf: Interface,
        sync_cfg, updates: Dict, actual_changes: List[str],
    ) -> None:
        """Проверяет и обновляет привязку к LAG интерфейсу."""
        if not intf.lag:
            return
        device_id = getattr(nb_interface.device, 'id', None) if nb_interface.device else None
        if not device_id:
            return
        lag_interface = self.client.get_interface_by_name(device_id, intf.lag)
        if lag_interface:
            current_lag_id = getattr(nb_interface.lag, 'id', None) if nb_interface.lag else None
            current_lag_name = getattr(nb_interface.lag, 'name', None) if nb_interface.lag else None
            if lag_interface.id != current_lag_id:
                updates["lag"] = lag_interface.id
                actual_changes.append(f"lag: {current_lag_name} → {intf.lag}")
        else:
            logger.debug(f"LAG интерфейс {intf.lag} не найден в NetBox")

    # ==================== ОРКЕСТРАТОР ====================

    def _build_update_data(
        self: SyncBase,
        nb_interface,
        intf: Interface,
        site_name: Optional[str] = None,
    ) -> Tuple[Dict, List[str], Optional[str]]:
        """
        Подготавливает данные для обновления интерфейса.

        Делегирует проверку каждого поля в отдельный _check_* хелпер.

        Args:
            nb_interface: Интерфейс из NetBox
            intf: Локальный интерфейс
            site_name: Имя сайта (кэшированное, чтобы избежать N+1 запросов)

        Returns:
            Tuple: (updates_dict, actual_changes_list, mac_to_assign или None)
        """
        updates = {}
        actual_changes = []
        sync_cfg = get_sync_config("interfaces")

        # Проверка каждого поля через отдельный хелпер
        self._check_type(nb_interface, intf, sync_cfg, updates, actual_changes)
        self._check_description(nb_interface, intf, sync_cfg, updates, actual_changes)
        self._check_enabled(nb_interface, intf, sync_cfg, updates, actual_changes)
        mac_to_assign = self._check_mac(nb_interface, intf, sync_cfg, actual_changes)
        self._check_mtu(nb_interface, intf, sync_cfg, updates, actual_changes)
        self._check_speed(nb_interface, intf, sync_cfg, updates, actual_changes)
        self._check_duplex(nb_interface, intf, sync_cfg, updates, actual_changes)

        # Debug: логируем данные mode/vlan для отладки
        logger.debug(
            f"  {nb_interface.name}: mode={intf.mode!r}, "
            f"access_vlan={intf.access_vlan!r}, native_vlan={intf.native_vlan!r}, "
            f"tagged_vlans={intf.tagged_vlans!r}"
        )

        self._check_mode(nb_interface, intf, sync_cfg, updates, actual_changes)

        sync_vlans_enabled = sync_cfg.get_option("sync_vlans", False)
        logger.debug(f"  {nb_interface.name}: sync_vlans={sync_vlans_enabled}")

        self._check_untagged_vlan(nb_interface, intf, sync_cfg, updates, actual_changes, site_name=site_name)
        self._check_tagged_vlans(nb_interface, intf, sync_cfg, updates, actual_changes, site_name=site_name)
        self._check_lag(nb_interface, intf, sync_cfg, updates, actual_changes)

        return updates, actual_changes, mac_to_assign

    # ==================== LEGACY (для fallback) ====================

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
        """Создаёт интерфейс в NetBox (поштучно, для fallback)."""
        sync_cfg = get_sync_config("interfaces")

        if self.dry_run:
            logger.info(f"[DRY-RUN] Создание интерфейса: {intf.name}")
            return

        kwargs = {}
        if sync_cfg.is_field_enabled("description"):
            kwargs["description"] = intf.description
        if sync_cfg.is_field_enabled("enabled"):
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

        if interface:
            logger.info(f"Создан интерфейс: {intf.name}")

        if mac_to_assign and interface:
            self.client.assign_mac_to_interface(interface.id, mac_to_assign)

    def _update_interface(
        self: SyncBase,
        nb_interface,
        intf: Interface,
    ) -> tuple:
        """
        Обновляет интерфейс в NetBox (поштучно, для fallback).

        Returns:
            tuple: (bool: были изменения, list: список изменений)
        """
        updates, actual_changes, mac_to_assign = self._build_update_data(nb_interface, intf)

        if not updates and not mac_to_assign:
            return False, []

        if self.dry_run:
            if updates:
                logger.info(f"[DRY-RUN] Обновление интерфейса {nb_interface.name}: {updates}")
            if mac_to_assign:
                logger.info(f"[DRY-RUN] Назначение MAC {mac_to_assign} на {nb_interface.name}")
            return True, actual_changes

        if updates:
            self.client.update_interface(nb_interface.id, **updates)
            logger.info(f"Обновлён интерфейс: {nb_interface.name} ({list(updates.keys())})")

        if mac_to_assign:
            self.client.assign_mac_to_interface(nb_interface.id, mac_to_assign)
            logger.info(f"Назначен MAC: {mac_to_assign} на {nb_interface.name}")

        return True, actual_changes
