"""
Синхронизация inventory items с NetBox.

Mixin класс для sync_inventory.
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

        # Получаем все existing inventory items для cleanup
        existing_items = {}
        if cleanup:
            for nb_item in self.client.get_inventory_items(device_id=device.id):
                existing_items[nb_item.name] = nb_item

        # Отслеживаем обработанные имена
        processed_names = set()

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

            existing = self.client.get_inventory_item(device.id, name)

            if existing:
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
                    # existing.manufacturer может быть объект с name или None
                    existing_mfr = ""
                    if existing.manufacturer:
                        existing_mfr = getattr(existing.manufacturer, "name", str(existing.manufacturer))
                    # Если manufacturer пустой - очищаем поле (убираем неверный дефолтный Cisco)
                    # Если разный - обновляем
                    if manufacturer:
                        if existing_mfr.lower() != manufacturer.lower():
                            updates["manufacturer"] = manufacturer
                            needs_update = True
                    elif existing_mfr:
                        # Очищаем manufacturer (был задан, но в данных пустой)
                        updates["manufacturer"] = None
                        needs_update = True

                if needs_update:
                    changes = list(updates.keys())
                    truncate_note = f" [обрезано с '{original_name}']" if was_truncated else ""
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Обновление inventory: {name}{truncate_note} ({changes})")
                        stats["updated"] += 1
                        details["update"].append({"name": name, "changes": changes})
                    else:
                        try:
                            self.client.update_inventory_item(existing.id, **updates)
                            logger.info(f"Обновлён inventory: {name}{truncate_note} ({changes})")
                            stats["updated"] += 1
                            details["update"].append({"name": name, "changes": changes})
                        except NetBoxError as e:
                            logger.error(f"Ошибка NetBox обновления {name}: {format_error_for_log(e)}")
                            stats["failed"] += 1
                        except Exception as e:
                            logger.error(f"Неизвестная ошибка обновления {name}: {e}")
                            stats["failed"] += 1
                else:
                    stats["skipped"] += 1
                continue

            truncate_note = f" [обрезано с '{original_name}']" if was_truncated else ""

            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание inventory: {name}{truncate_note} (pid={pid}, serial={serial})")
                stats["created"] += 1
                details["create"].append({"name": name})
                continue

            try:
                kwargs = {}
                if sync_cfg.is_field_enabled("part_id") and pid:
                    kwargs["part_id"] = pid
                if sync_cfg.is_field_enabled("serial") and serial:
                    kwargs["serial"] = serial
                if sync_cfg.is_field_enabled("description") and description:
                    kwargs["description"] = description
                if sync_cfg.is_field_enabled("manufacturer") and manufacturer:
                    kwargs["manufacturer"] = manufacturer

                self.client.create_inventory_item(
                    device_id=device.id,
                    name=name,
                    **kwargs,
                )
                logger.info(f"Создан inventory: {name}{truncate_note}")
                stats["created"] += 1
                details["create"].append({"name": name})
            except NetBoxValidationError as e:
                logger.error(f"Ошибка валидации inventory {name}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except NetBoxError as e:
                logger.error(f"Ошибка NetBox создания inventory {name}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except Exception as e:
                logger.error(f"Неизвестная ошибка создания inventory {name}: {e}")
                stats["failed"] += 1

        # Cleanup: удаляем лишние inventory items
        if cleanup:
            for nb_name, nb_item in existing_items.items():
                if nb_name not in processed_names:
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Удаление inventory: {nb_name}")
                        stats["deleted"] += 1
                        details["delete"].append({"name": nb_name})
                    else:
                        try:
                            self.client.delete_inventory_item(nb_item.id)
                            logger.info(f"Удалён inventory: {nb_name}")
                            stats["deleted"] += 1
                            details["delete"].append({"name": nb_name})
                        except Exception as e:
                            logger.error(f"Ошибка удаления inventory {nb_name}: {e}")
                            stats["failed"] += 1

        logger.info(
            f"Синхронизация inventory {device_name}: "
            f"создано={stats['created']}, обновлено={stats['updated']}, "
            f"удалено={stats['deleted']}, пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        # Возвращаем stats с details для консистентности с другими sync методами
        result = dict(stats)
        result["details"] = details
        return result
