"""
Синхронизация inventory items с NetBox.

Mixin класс для sync_inventory.
Использует batch API для оптимизации производительности.
"""

import logging
from typing import List, Dict, Any, Optional

from .base import (
    SyncBase, InventoryItem, get_sync_config,
    NetBoxError, NetBoxValidationError, format_error_for_log, logger,
)

logger = logging.getLogger(__name__)


class InventorySyncMixin:
    """Mixin для синхронизации inventory items."""

    def sync_inventory(
        self: SyncBase,
        device_name: str,
        inventory_data: List[InventoryItem],
        cleanup: bool = False,
    ) -> Dict[str, int]:
        """
        Синхронизирует inventory items (модули, SFP, PSU) в NetBox.

        Использует batch API для create/update/delete.
        При ошибке batch — fallback на поштучные операции.

        Args:
            device_name: Имя устройства в NetBox
            inventory_data: Данные (InventoryItem модели)
            cleanup: Удалять лишние inventory items из NetBox

        Returns:
            Dict: Статистика {created, updated, deleted, skipped, failed}
        """
        stats = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0}
        details = {"create": [], "update": [], "delete": []}

        device = self._find_device(device_name)
        if not device:
            logger.error(f"Устройство не найдено в NetBox: {device_name}")
            stats["failed"] = 1
            stats["errors"] = [f"Device not found in NetBox: {device_name}"]
            return stats

        # Если данные пустые и не нужен cleanup - выходим
        if not inventory_data and not cleanup:
            logger.info(f"Нет inventory данных для {device_name}")
            return stats

        items = InventoryItem.ensure_list(inventory_data) if inventory_data else []

        logger.info(f"Синхронизация inventory для {device_name}: {len(items)} компонентов")

        sync_cfg = get_sync_config("inventory")

        # Получаем ВСЕ existing inventory items одним запросом (не только для cleanup).
        # Это избегает N+1 запросов get_inventory_item() на каждый item в цикле.
        existing_items = {}
        for nb_item in self.client.get_inventory_items(device_id=device.id):
            existing_items[nb_item.name] = nb_item

        # Отслеживаем обработанные имена
        processed_names = set()

        # Собираем батчи для create/update
        create_batch = []  # Список (data_dict, name, truncate_note) для bulk create
        update_batch = []  # Список (existing_id, updates_dict, name, changes, truncate_note)

        for item in items:
            name = item.name.strip() if item.name else ""
            pid = item.pid.strip() if item.pid else ""
            serial = item.serial.strip() if item.serial else ""
            description = item.description.strip() if item.description else ""
            manufacturer = item.manufacturer.strip() if item.manufacturer else ""

            if not name:
                continue

            # NetBox ограничивает name до 64 символов
            was_truncated = False
            original_name = name
            if len(name) > 64:
                name = name[:61] + "..."
                was_truncated = True

            processed_names.add(name)

            if not serial:
                if was_truncated:
                    logger.warning(
                        f"Пропущен inventory '{original_name}' - нет серийного номера "
                        f"(имя было бы обрезано до '{name}')"
                    )
                else:
                    logger.warning(f"Пропущен inventory '{name}' - нет серийного номера")
                stats["skipped"] += 1
                continue

            truncate_note = f" [обрезано с '{original_name}']" if was_truncated else ""

            existing = existing_items.get(name)

            if existing:
                # Подготавливаем данные обновления
                needs_update = False
                updates = {}

                if sync_cfg.is_field_enabled("part_id") and pid and existing.part_id != pid:
                    updates["part_id"] = pid
                    needs_update = True
                if sync_cfg.is_field_enabled("serial") and serial and existing.serial != serial:
                    updates["serial"] = serial
                    needs_update = True
                if sync_cfg.is_field_enabled("description") and description and existing.description != description:
                    updates["description"] = description
                    needs_update = True
                if sync_cfg.is_field_enabled("manufacturer"):
                    existing_mfr = ""
                    if existing.manufacturer:
                        existing_mfr = getattr(existing.manufacturer, "name", str(existing.manufacturer))
                    if manufacturer:
                        if existing_mfr.lower() != manufacturer.lower():
                            updates["manufacturer"] = manufacturer
                            needs_update = True
                    elif existing_mfr:
                        updates["manufacturer"] = None
                        needs_update = True

                if needs_update:
                    changes = list(updates.keys())
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Обновление inventory: {name}{truncate_note} ({changes})")
                        stats["updated"] += 1
                        details["update"].append({"name": name, "changes": changes})
                    else:
                        update_batch.append((existing.id, updates, name, changes, truncate_note))
                else:
                    stats["skipped"] += 1
                continue

            # Новый item — подготавливаем данные создания
            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание inventory: {name}{truncate_note} (pid={pid}, serial={serial})")
                stats["created"] += 1
                details["create"].append({"name": name})
                continue

            kwargs = {"device": device.id, "name": name, "discovered": True}
            if sync_cfg.is_field_enabled("part_id") and pid:
                kwargs["part_id"] = pid
            if sync_cfg.is_field_enabled("serial") and serial:
                kwargs["serial"] = serial
            if sync_cfg.is_field_enabled("description") and description:
                kwargs["description"] = description
            # Manufacturer для bulk create: резолвим ID заранее
            if sync_cfg.is_field_enabled("manufacturer") and manufacturer:
                mfr = self.client.api.dcim.manufacturers.get(slug=manufacturer.lower())
                if not mfr:
                    mfr = self.client.api.dcim.manufacturers.get(name=manufacturer)
                if mfr:
                    kwargs["manufacturer"] = mfr.id

            create_batch.append((kwargs, name, truncate_note))

        # === BATCH CREATE ===
        if create_batch and not self.dry_run:
            self._batch_with_fallback(
                batch_data=[data for data, _, _ in create_batch],
                item_names=[f"{name}{tn}" for _, name, tn in create_batch],
                bulk_fn=self.client.bulk_create_inventory_items,
                fallback_fn=lambda data, name: self.client.api.dcim.inventory_items.create(data),
                stats=stats, details=details,
                operation="created", entity_name="inventory",
            )

        # === BATCH UPDATE (специфичная логика — id внутри dict) ===
        if update_batch and not self.dry_run:
            batch_data = []
            for existing_id, updates, name, changes, truncate_note in update_batch:
                upd = dict(updates)
                upd["id"] = existing_id
                batch_data.append(upd)

            try:
                self.client.bulk_update_inventory_items(batch_data)
                for _, _, name, changes, truncate_note in update_batch:
                    logger.info(f"Обновлён inventory: {name}{truncate_note} ({changes})")
                    stats["updated"] += 1
                    details["update"].append({"name": name, "changes": changes})
            except Exception as e:
                logger.warning(f"Batch update inventory не удался ({e}), fallback на поштучное обновление")
                for existing_id, updates, name, changes, truncate_note in update_batch:
                    try:
                        self.client.update_inventory_item(existing_id, **updates)
                        logger.info(f"Обновлён inventory: {name}{truncate_note} ({changes})")
                        stats["updated"] += 1
                        details["update"].append({"name": name, "changes": changes})
                    except Exception as exc:
                        logger.error(f"Ошибка обновления inventory {name}: {exc}")
                        stats["failed"] += 1

        # === BATCH DELETE (cleanup) ===
        if cleanup:
            delete_ids = []
            delete_names = []
            for nb_name, nb_item in existing_items.items():
                if nb_name not in processed_names:
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Удаление inventory: {nb_name}")
                        stats["deleted"] += 1
                        details["delete"].append({"name": nb_name})
                    else:
                        delete_ids.append(nb_item.id)
                        delete_names.append(nb_name)

            if delete_ids and not self.dry_run:
                self._batch_with_fallback(
                    batch_data=delete_ids,
                    item_names=delete_names,
                    bulk_fn=self.client.bulk_delete_inventory_items,
                    fallback_fn=lambda item_id, name: self.client.delete_inventory_item(item_id),
                    stats=stats, details=details,
                    operation="deleted", entity_name="inventory",
                )

        logger.info(
            f"Синхронизация inventory {device_name}: "
            f"создано={stats['created']}, обновлено={stats['updated']}, "
            f"удалено={stats['deleted']}, пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        # Возвращаем stats с details для консистентности с другими sync методами
        result = dict(stats)
        result["details"] = details
        return result
