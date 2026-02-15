"""
Mixin для работы с интерфейсами NetBox.
"""

import logging
from typing import List, Any, Optional

logger = logging.getLogger(__name__)


class InterfacesMixin:
    """Методы для работы с интерфейсами."""

    def get_interfaces(
        self,
        device_id: Optional[int] = None,
        device_name: Optional[str] = None,
        **filters,
    ) -> List[Any]:
        """
        Получает интерфейсы устройства.

        Args:
            device_id: ID устройства
            device_name: Имя устройства
            **filters: Дополнительные фильтры

        Returns:
            List: Список интерфейсов
        """
        params = {}
        if device_id:
            params["device_id"] = device_id
        if device_name:
            params["device"] = device_name
        params.update(filters)

        interfaces = list(self.api.dcim.interfaces.filter(**params))
        logger.debug(f"Получено интерфейсов: {len(interfaces)}")
        return interfaces

    def get_interface_by_name(
        self,
        device_id: int,
        interface_name: str,
    ) -> Optional[Any]:
        """
        Получает интерфейс по имени.

        Поддерживает поиск по точному имени, нормализованному и регистронезависимому.

        Args:
            device_id: ID устройства
            interface_name: Имя интерфейса

        Returns:
            Интерфейс или None
        """
        from ...core.constants import normalize_interface_full

        # Точное совпадение
        interfaces = list(self.api.dcim.interfaces.filter(
            device_id=device_id,
            name=interface_name,
        ))
        if interfaces:
            return interfaces[0]

        # Попробуем нормализованное имя (Po1 → Port-channel1)
        normalized_name = normalize_interface_full(interface_name)
        if normalized_name != interface_name:
            interfaces = list(self.api.dcim.interfaces.filter(
                device_id=device_id,
                name=normalized_name,
            ))
            if interfaces:
                return interfaces[0]

        # Для LAG попробуем регистронезависимый поиск
        if interface_name.lower().startswith(("po", "port-channel", "ag", "aggregateport")):
            all_interfaces = list(self.api.dcim.interfaces.filter(device_id=device_id))
            name_lower = normalized_name.lower()
            for intf in all_interfaces:
                if intf.name.lower() == name_lower:
                    return intf

        return None

    def create_interface(
        self,
        device_id: int,
        name: str,
        interface_type: str = "1000base-t",
        description: str = "",
        enabled: bool = True,
        **kwargs,
    ) -> Any:
        """
        Создаёт интерфейс на устройстве.

        Args:
            device_id: ID устройства
            name: Имя интерфейса
            interface_type: Тип интерфейса
            description: Описание
            enabled: Включен
            **kwargs: Дополнительные параметры

        Returns:
            Созданный интерфейс
        """
        data = {
            "device": device_id,
            "name": name,
            "type": interface_type,
            "description": description,
            "enabled": enabled,
            **kwargs,
        }

        interface = self.api.dcim.interfaces.create(data)
        logger.debug(f"Создан интерфейс: {name} на устройстве {device_id}")
        return interface

    def update_interface(
        self,
        interface_id: int,
        **updates,
    ) -> Any:
        """
        Обновляет интерфейс.

        Args:
            interface_id: ID интерфейса
            **updates: Поля для обновления

        Returns:
            Обновлённый интерфейс
        """
        interface = self.api.dcim.interfaces.get(interface_id)
        if interface:
            interface.update(updates)
            logger.debug(f"Обновлён интерфейс: {interface.name}")
        return interface

    # ==================== BULK ОПЕРАЦИИ ====================

    def bulk_create_interfaces(self, interfaces_data: List[dict]) -> List[Any]:
        """
        Создаёт несколько интерфейсов одним API-вызовом.

        Args:
            interfaces_data: Список словарей с данными интерфейсов

        Returns:
            List: Список созданных интерфейсов
        """
        if not interfaces_data:
            return []
        result = self.api.dcim.interfaces.create(interfaces_data)
        created = result if isinstance(result, list) else [result]
        logger.debug(f"Bulk create: создано {len(created)} интерфейсов")
        return created

    def bulk_update_interfaces(self, updates: List[dict]) -> List[Any]:
        """
        Обновляет несколько интерфейсов одним API-вызовом.

        Каждый dict должен содержать 'id'.

        Args:
            updates: Список словарей с полем 'id' и обновляемыми полями

        Returns:
            List: Список обновлённых интерфейсов
        """
        if not updates:
            return []
        result = self.api.dcim.interfaces.update(updates)
        updated = result if isinstance(result, list) else [result]
        logger.debug(f"Bulk update: обновлено {len(updated)} интерфейсов")
        return updated

    def bulk_delete_interfaces(self, ids: List[int]) -> bool:
        """
        Удаляет интерфейсы по списку ID одним API-вызовом.

        Args:
            ids: Список ID интерфейсов

        Returns:
            bool: True если удаление успешно
        """
        if not ids:
            return True
        # pynetbox 7.5+ принимает список int ID напрямую
        self.api.dcim.interfaces.delete(ids)
        logger.debug(f"Bulk delete: удалено {len(ids)} интерфейсов")
        return True
