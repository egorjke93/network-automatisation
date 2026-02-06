"""
Mixin для работы с Inventory Items в NetBox.
"""

import logging
import re
from typing import List, Any, Optional

logger = logging.getLogger(__name__)


class InventoryMixin:
    """Методы для работы с inventory items."""

    def get_inventory_items(
        self,
        device_id: Optional[int] = None,
        device_name: Optional[str] = None,
        **filters,
    ) -> List[Any]:
        """
        Получает inventory items устройства.

        Args:
            device_id: ID устройства
            device_name: Имя устройства
            **filters: Дополнительные фильтры

        Returns:
            List: Список inventory items
        """
        params = {}
        if device_id:
            params["device_id"] = device_id
        if device_name:
            params["device"] = device_name
        params.update(filters)

        items = list(self.api.dcim.inventory_items.filter(**params))
        logger.debug(f"Получено inventory items: {len(items)}")
        return items

    def get_inventory_item(
        self,
        device_id: int,
        name: str,
    ) -> Optional[Any]:
        """
        Находит inventory item по имени на устройстве.

        Args:
            device_id: ID устройства
            name: Имя компонента

        Returns:
            InventoryItem или None
        """
        return self.api.dcim.inventory_items.get(device_id=device_id, name=name)

    def create_inventory_item(
        self,
        device_id: int,
        name: str,
        manufacturer: Optional[str] = None,
        part_id: str = "",
        serial: str = "",
        description: str = "",
        **kwargs,
    ) -> Any:
        """
        Создаёт inventory item на устройстве.

        Args:
            device_id: ID устройства
            name: Имя компонента
            manufacturer: Производитель
            part_id: Part ID / Product ID
            serial: Серийный номер
            description: Описание
            **kwargs: Дополнительные параметры

        Returns:
            Созданный inventory item
        """
        data = {
            "device": device_id,
            "name": name,
            "part_id": part_id,
            "serial": serial,
            "description": description,
            "discovered": True,
            **kwargs,
        }

        if manufacturer:
            mfr = self.api.dcim.manufacturers.get(slug=manufacturer.lower())
            if not mfr:
                mfr = self.api.dcim.manufacturers.get(name=manufacturer)
            if mfr:
                data["manufacturer"] = mfr.id

        item = self.api.dcim.inventory_items.create(data)
        logger.debug(f"Создан inventory item: {name} (serial={serial})")
        return item

    def update_inventory_item(
        self,
        item_id: int,
        **updates,
    ) -> Any:
        """
        Обновляет inventory item.

        Args:
            item_id: ID inventory item
            **updates: Поля для обновления

        Returns:
            Обновлённый inventory item
        """
        item = self.api.dcim.inventory_items.get(item_id)
        if item:
            # Обработка manufacturer
            if "manufacturer" in updates:
                mfr_value = updates["manufacturer"]
                if mfr_value is None:
                    updates["manufacturer"] = None
                elif isinstance(mfr_value, str):
                    mfr = self.api.dcim.manufacturers.get(slug=mfr_value.lower())
                    if not mfr:
                        mfr = self.api.dcim.manufacturers.get(name=mfr_value)
                    if mfr:
                        updates["manufacturer"] = mfr.id
                    else:
                        slug = re.sub(r'[^a-z0-9-]', '-', mfr_value.lower()).strip('-')
                        mfr = self.api.dcim.manufacturers.create({"name": mfr_value, "slug": slug})
                        if mfr:
                            updates["manufacturer"] = mfr.id
                        else:
                            del updates["manufacturer"]
            item.update(updates)
            logger.debug(f"Обновлён inventory item: {item.name}")
        return item

    def delete_inventory_item(self, item_id: int) -> bool:
        """
        Удаляет inventory item.

        Args:
            item_id: ID inventory item

        Returns:
            bool: True если удалён
        """
        item = self.api.dcim.inventory_items.get(item_id)
        if item:
            name = item.name
            item.delete()
            logger.debug(f"Удалён inventory item: {name}")
            return True
        return False

    # ==================== BULK ОПЕРАЦИИ ====================

    def bulk_create_inventory_items(self, items_data: List[dict]) -> List[Any]:
        """
        Создаёт несколько inventory items одним API-вызовом.

        Args:
            items_data: Список словарей с данными inventory items

        Returns:
            List: Список созданных inventory items
        """
        if not items_data:
            return []
        result = self.api.dcim.inventory_items.create(items_data)
        created = result if isinstance(result, list) else [result]
        logger.debug(f"Bulk create: создано {len(created)} inventory items")
        return created

    def bulk_update_inventory_items(self, updates: List[dict]) -> List[Any]:
        """
        Обновляет несколько inventory items одним API-вызовом.

        Каждый dict должен содержать 'id'.

        Args:
            updates: Список словарей с полем 'id' и обновляемыми полями

        Returns:
            List: Список обновлённых inventory items
        """
        if not updates:
            return []
        result = self.api.dcim.inventory_items.update(updates)
        updated = result if isinstance(result, list) else [result]
        logger.debug(f"Bulk update: обновлено {len(updated)} inventory items")
        return updated

    def bulk_delete_inventory_items(self, ids: List[int]) -> bool:
        """
        Удаляет inventory items по списку ID одним API-вызовом.

        Args:
            ids: Список ID inventory items

        Returns:
            bool: True если удаление успешно
        """
        if not ids:
            return True
        # pynetbox 7.5+ принимает список int ID напрямую
        self.api.dcim.inventory_items.delete(ids)
        logger.debug(f"Bulk delete: удалено {len(ids)} inventory items")
        return True
