"""
Mixin для работы с IP-адресами и кабелями NetBox.
"""

import logging
from typing import List, Any, Optional

logger = logging.getLogger(__name__)


class IPAddressesMixin:
    """Методы для работы с IP-адресами и кабелями."""

    def get_ip_addresses(
        self,
        device_id: Optional[int] = None,
        interface_id: Optional[int] = None,
        **filters,
    ) -> List[Any]:
        """
        Получает IP-адреса.

        Args:
            device_id: Фильтр по устройству
            interface_id: Фильтр по интерфейсу
            **filters: Дополнительные фильтры

        Returns:
            List: Список IP-адресов
        """
        params = {}
        if device_id:
            params["device_id"] = device_id
        if interface_id:
            params["interface_id"] = interface_id
        params.update(filters)

        ips = list(self.api.ipam.ip_addresses.filter(**params))
        logger.debug(f"Получено IP-адресов: {len(ips)}")
        return ips

    def get_cables(
        self,
        device_id: Optional[int] = None,
        **filters,
    ) -> List[Any]:
        """
        Получает кабели.

        Args:
            device_id: Фильтр по устройству
            **filters: Дополнительные фильтры

        Returns:
            List: Список кабелей
        """
        params = {}
        if device_id:
            params["device_id"] = device_id
        params.update(filters)

        cables = list(self.api.dcim.cables.filter(**params))
        logger.debug(f"Получено кабелей: {len(cables)}")
        return cables

    def create_ip_address(
        self,
        address: str,
        interface_id: Optional[int] = None,
        status: str = "active",
        **kwargs,
    ) -> Any:
        """
        Создаёт IP-адрес.

        Args:
            address: IP-адрес с маской (192.168.1.1/24)
            interface_id: ID интерфейса для привязки
            status: Статус (active, reserved, deprecated)
            **kwargs: Дополнительные параметры

        Returns:
            Созданный IP-адрес
        """
        data = {
            "address": address,
            "status": status,
            **kwargs,
        }

        if interface_id:
            data["assigned_object_type"] = "dcim.interface"
            data["assigned_object_id"] = interface_id

        ip = self.api.ipam.ip_addresses.create(data)
        logger.debug(f"Создан IP-адрес: {address}")
        return ip

    # ==================== BULK ОПЕРАЦИИ ====================

    def bulk_create_ip_addresses(self, ip_data: List[dict]) -> List[Any]:
        """
        Создаёт несколько IP-адресов одним API-вызовом.

        Args:
            ip_data: Список словарей с данными IP-адресов

        Returns:
            List: Список созданных IP-адресов
        """
        if not ip_data:
            return []
        result = self.api.ipam.ip_addresses.create(ip_data)
        created = result if isinstance(result, list) else [result]
        logger.debug(f"Bulk create: создано {len(created)} IP-адресов")
        return created

    def bulk_update_ip_addresses(self, updates: List[dict]) -> List[Any]:
        """
        Обновляет несколько IP-адресов одним API-вызовом.

        Каждый dict должен содержать 'id'.

        Args:
            updates: Список словарей с полем 'id' и обновляемыми полями

        Returns:
            List: Список обновлённых IP-адресов
        """
        if not updates:
            return []
        result = self.api.ipam.ip_addresses.update(updates)
        updated = result if isinstance(result, list) else [result]
        logger.debug(f"Bulk update: обновлено {len(updated)} IP-адресов")
        return updated

    def bulk_delete_ip_addresses(self, ids: List[int]) -> bool:
        """
        Удаляет IP-адреса по списку ID одним API-вызовом.

        Args:
            ids: Список ID IP-адресов

        Returns:
            bool: True если удаление успешно
        """
        if not ids:
            return True
        # pynetbox 7.5+ принимает список int ID напрямую
        self.api.ipam.ip_addresses.delete(ids)
        logger.debug(f"Bulk delete: удалено {len(ids)} IP-адресов")
        return True
