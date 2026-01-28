"""
Mixin для работы с устройствами NetBox.
"""

import logging
from typing import List, Any, Optional

logger = logging.getLogger(__name__)


class DevicesMixin:
    """Методы для работы с устройствами."""

    def get_devices(
        self,
        site: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        **filters,
    ) -> List[Any]:
        """
        Получает список устройств из NetBox.

        Args:
            site: Фильтр по сайту (имя или slug)
            role: Фильтр по роли (имя или slug)
            status: Фильтр по статусу (active, planned, etc.)
            **filters: Дополнительные фильтры

        Returns:
            List: Список устройств (pynetbox Record)
        """
        params = {}

        # Site: поддержка имени или slug
        if site:
            site_slug = self._resolve_site_slug(site)
            if site_slug:
                params["site"] = site_slug
            else:
                logger.warning(f"Сайт не найден: {site}")
                return []

        # Role: поддержка имени или slug
        if role:
            role_slug = self._resolve_role_slug(role)
            if role_slug:
                params["role"] = role_slug
            else:
                logger.warning(f"Роль не найдена: {role}")
                return []

        if status:
            params["status"] = status
        params.update(filters)

        devices = list(self.api.dcim.devices.filter(**params))
        logger.debug(f"Получено устройств: {len(devices)}")
        return devices

    def get_device_by_name(self, name: str) -> Optional[Any]:
        """
        Находит устройство по имени.

        Args:
            name: Имя устройства

        Returns:
            Device или None
        """
        return self.api.dcim.devices.get(name=name)

    def get_device_by_ip(self, ip: str) -> Optional[Any]:
        """
        Находит устройство по IP-адресу.

        Args:
            ip: IP-адрес (без маски)

        Returns:
            Device или None
        """
        ip_obj = self.api.ipam.ip_addresses.get(address=ip)
        if ip_obj and ip_obj.assigned_object:
            interface = ip_obj.assigned_object
            if hasattr(interface, "device"):
                return interface.device
        return None

    def get_device_by_mac(self, mac: str) -> Optional[Any]:
        """
        Находит устройство по MAC-адресу.

        Поиск выполняется в таблице dcim.mac_addresses (NetBox 4.x).

        Args:
            mac: MAC-адрес в любом формате

        Returns:
            Device или None
        """
        if not mac:
            return None

        # Нормализуем MAC к формату AA:BB:CC:DD:EE:FF
        mac_normalized = mac.replace(":", "").replace("-", "").replace(".", "").lower()
        if len(mac_normalized) != 12:
            logger.debug(f"Некорректный MAC: {mac}")
            return None

        mac_formatted = ":".join(mac_normalized[i:i+2] for i in range(0, 12, 2))

        try:
            # Ищем в таблице MAC-адресов (NetBox 4.x)
            mac_objs = list(self.api.dcim.mac_addresses.filter(mac_address=mac_formatted))
            if mac_objs:
                for mac_obj in mac_objs:
                    if mac_obj.assigned_object and hasattr(mac_obj.assigned_object, "device"):
                        device = mac_obj.assigned_object.device
                        logger.debug(f"Устройство найдено по MAC {mac_formatted}: {device.name}")
                        return device

            # Fallback: ищем в интерфейсах напрямую
            interfaces = list(self.api.dcim.interfaces.filter(mac_address=mac_formatted))
            if interfaces and interfaces[0].device:
                device = interfaces[0].device
                logger.debug(f"Устройство найдено по MAC интерфейса {mac_formatted}: {device.name}")
                return device

        except Exception as e:
            logger.debug(f"Ошибка поиска по MAC {mac}: {e}")

        return None
