"""
Mixin для работы с DCIM объектами NetBox.

Device Types, Manufacturers, Device Roles, Sites, Platforms, MAC-адреса.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DCIMMixin:
    """Методы для работы с DCIM объектами."""

    # ==================== MAC-АДРЕСА (NetBox 4.x) ====================

    def assign_mac_to_interface(
        self,
        interface_id: int,
        mac_address: str,
    ) -> Any:
        """
        Назначает MAC-адрес интерфейсу (NetBox 4.x).

        Args:
            interface_id: ID интерфейса
            mac_address: MAC-адрес в формате AA:BB:CC:DD:EE:FF

        Returns:
            Созданный MAC-адрес объект или None
        """
        if not mac_address:
            return None

        existing = list(self.api.dcim.mac_addresses.filter(
            assigned_object_type="dcim.interface",
            assigned_object_id=interface_id,
            mac_address=mac_address,
        ))
        if existing:
            logger.debug(f"MAC {mac_address} уже привязан к интерфейсу {interface_id}")
            return existing[0]

        try:
            mac_obj = self.api.dcim.mac_addresses.create({
                "mac_address": mac_address,
                "assigned_object_type": "dcim.interface",
                "assigned_object_id": interface_id,
            })
            logger.debug(f"MAC {mac_address} привязан к интерфейсу {interface_id}")
            return mac_obj
        except Exception as e:
            logger.warning(f"Не удалось создать MAC {mac_address}: {e}")
            return None

    def get_interface_mac(self, interface_id: int) -> Optional[str]:
        """
        Получает MAC-адрес интерфейса.

        Args:
            interface_id: ID интерфейса

        Returns:
            MAC-адрес или None
        """
        macs = list(self.api.dcim.mac_addresses.filter(
            assigned_object_type="dcim.interface",
            assigned_object_id=interface_id,
        ))
        if macs:
            return macs[0].mac_address
        return None

    # ==================== DEVICE TYPES ====================

    def get_device_type(
        self,
        model: str,
        manufacturer: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Находит device type по модели.

        Args:
            model: Модель устройства
            manufacturer: Производитель (опционально)

        Returns:
            DeviceType или None
        """
        params = {"model": model}
        if manufacturer:
            mfr = self.get_or_create_manufacturer(manufacturer)
            if mfr:
                params["manufacturer_id"] = mfr.id

        return self.api.dcim.device_types.get(**params)

    def get_or_create_device_type(
        self,
        model: str,
        manufacturer: str,
        slug: Optional[str] = None,
        u_height: float = 1,
        is_full_depth: bool = True,
        **kwargs,
    ) -> Any:
        """
        Получает или создаёт device type.

        Args:
            model: Модель устройства
            manufacturer: Производитель
            slug: Slug (опционально)
            u_height: Высота в юнитах
            is_full_depth: Полная глубина
            **kwargs: Дополнительные параметры

        Returns:
            DeviceType объект
        """
        mfr = self.get_or_create_manufacturer(manufacturer)

        existing = self.api.dcim.device_types.get(
            model=model,
            manufacturer_id=mfr.id,
        )
        if existing:
            logger.debug(f"Device type '{model}' уже существует")
            return existing

        if not slug:
            slug = model.lower().replace(" ", "-").replace("/", "-")

        data = {
            "manufacturer": mfr.id,
            "model": model,
            "slug": slug,
            "u_height": u_height,
            "is_full_depth": is_full_depth,
            **kwargs,
        }

        device_type = self.api.dcim.device_types.create(data)
        logger.info(f"Создан device type: {manufacturer} {model}")
        return device_type

    # ==================== MANUFACTURERS ====================

    def get_manufacturer(self, name: str) -> Optional[Any]:
        """
        Находит производителя по имени.

        Args:
            name: Имя производителя

        Returns:
            Manufacturer или None
        """
        slug = name.lower().replace(" ", "-")
        mfr = self.api.dcim.manufacturers.get(slug=slug)
        if mfr:
            return mfr
        return self.api.dcim.manufacturers.get(name=name)

    def get_or_create_manufacturer(self, name: str) -> Any:
        """
        Получает или создаёт производителя.

        Args:
            name: Имя производителя

        Returns:
            Manufacturer объект
        """
        existing = self.get_manufacturer(name)
        if existing:
            return existing

        slug = name.lower().replace(" ", "-")
        mfr = self.api.dcim.manufacturers.create({
            "name": name,
            "slug": slug,
        })
        logger.info(f"Создан производитель: {name}")
        return mfr

    # ==================== DEVICE ROLES ====================

    def get_device_role(self, name: str) -> Optional[Any]:
        """
        Находит роль устройства по имени.

        Args:
            name: Имя роли

        Returns:
            DeviceRole или None
        """
        slug = name.lower().replace(" ", "-")
        role = self.api.dcim.device_roles.get(slug=slug)
        if role:
            return role
        return self.api.dcim.device_roles.get(name=name)

    def get_or_create_device_role(
        self,
        name: str,
        color: str = "9e9e9e",
        vm_role: bool = False,
    ) -> Any:
        """
        Получает или создаёт роль устройства.

        Args:
            name: Имя роли
            color: Цвет в hex
            vm_role: Роль для VM

        Returns:
            DeviceRole объект
        """
        existing = self.get_device_role(name)
        if existing:
            return existing

        slug = name.lower().replace(" ", "-")
        role = self.api.dcim.device_roles.create({
            "name": name,
            "slug": slug,
            "color": color,
            "vm_role": vm_role,
        })
        logger.info(f"Создана роль устройства: {name}")
        return role

    # ==================== SITES ====================

    def get_site(self, name: str) -> Optional[Any]:
        """
        Находит сайт по имени.

        Args:
            name: Имя сайта

        Returns:
            Site или None
        """
        slug = name.lower().replace(" ", "-")
        site = self.api.dcim.sites.get(slug=slug)
        if site:
            return site
        return self.api.dcim.sites.get(name=name)

    def get_or_create_site(self, name: str, status: str = "active") -> Any:
        """
        Получает или создаёт сайт.

        Args:
            name: Имя сайта
            status: Статус

        Returns:
            Site объект
        """
        existing = self.get_site(name)
        if existing:
            return existing

        slug = name.lower().replace(" ", "-")
        site = self.api.dcim.sites.create({
            "name": name,
            "slug": slug,
            "status": status,
        })
        logger.info(f"Создан сайт: {name}")
        return site

    # ==================== PLATFORMS ====================

    def get_platform(self, name: str) -> Optional[Any]:
        """
        Находит платформу по имени.

        Args:
            name: Имя платформы (cisco_ios, arista_eos)

        Returns:
            Platform или None
        """
        slug = name.lower().replace(" ", "-").replace("_", "-")
        platform = self.api.dcim.platforms.get(slug=slug)
        if platform:
            return platform
        return self.api.dcim.platforms.get(name=name)

    def get_or_create_platform(
        self,
        name: str,
        manufacturer: Optional[str] = None,
    ) -> Any:
        """
        Получает или создаёт платформу.

        Args:
            name: Имя платформы
            manufacturer: Производитель (опционально)

        Returns:
            Platform объект
        """
        existing = self.get_platform(name)
        if existing:
            return existing

        slug = name.lower().replace(" ", "-").replace("_", "-")
        data = {
            "name": name,
            "slug": slug,
        }

        if manufacturer:
            mfr = self.get_or_create_manufacturer(manufacturer)
            data["manufacturer"] = mfr.id

        platform = self.api.dcim.platforms.create(data)
        logger.info(f"Создана платформа: {name}")
        return platform
