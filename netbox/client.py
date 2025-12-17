"""
Клиент для работы с NetBox API.

Использует библиотеку pynetbox для взаимодействия с NetBox.
Предоставляет удобные методы для работы с устройствами,
интерфейсами, IP-адресами и MAC-адресами.

Пример использования:
    client = NetBoxClient(
        url="https://netbox.example.com",
        token="your-api-token"
    )

    # Получить все устройства
    devices = client.get_devices()

    # Найти устройство по имени
    device = client.get_device_by_name("switch-01")

    # Получить интерфейсы устройства
    interfaces = client.get_interfaces(device_id=1)
"""

import os
import logging
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)

# Пробуем импортировать pynetbox
try:
    import pynetbox

    PYNETBOX_AVAILABLE = True
except ImportError:
    PYNETBOX_AVAILABLE = False
    logger.warning("pynetbox не установлен. pip install pynetbox")


class NetBoxClient:
    """
    Клиент для работы с NetBox API через pynetbox.

    Предоставляет методы для CRUD операций с объектами NetBox:
    - Устройства (devices)
    - Интерфейсы (interfaces)
    - IP-адреса (ip_addresses)
    - Префиксы (prefixes)
    - VLAN

    Attributes:
        url: URL NetBox сервера
        api: Объект pynetbox.api

    Example:
        client = NetBoxClient(
            url="https://netbox.example.com",
            token="xxx"
        )

        # Получить устройства
        for device in client.get_devices():
            print(device.name)
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        ssl_verify: bool = True,
    ):
        """
        Инициализация клиента NetBox.

        Args:
            url: URL NetBox сервера (или env NETBOX_URL)
            token: API токен (или env NETBOX_TOKEN)
            ssl_verify: Проверять SSL сертификат

        Raises:
            ImportError: pynetbox не установлен
            ValueError: URL или токен не указаны
        """
        if not PYNETBOX_AVAILABLE:
            raise ImportError(
                "pynetbox не установлен. Установите: pip install pynetbox"
            )

        # Получаем URL и токен из параметров или переменных окружения
        self.url = url or os.environ.get("NETBOX_URL")
        self._token = token or os.environ.get("NETBOX_TOKEN")

        if not self.url:
            raise ValueError(
                "NetBox URL не указан. Укажите url или установите NETBOX_URL"
            )
        if not self._token:
            raise ValueError(
                "NetBox токен не указан. Укажите token или установите NETBOX_TOKEN"
            )

        # Инициализируем pynetbox API
        self.api = pynetbox.api(self.url, token=self._token)

        # Настройка SSL
        if not ssl_verify:
            import requests

            session = requests.Session()
            session.verify = False
            self.api.http_session = session

        logger.info(f"NetBox клиент инициализирован: {self.url}")

    # ==================== УСТРОЙСТВА ====================

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
            site: Фильтр по сайту
            role: Фильтр по роли
            status: Фильтр по статусу (active, planned, etc.)
            **filters: Дополнительные фильтры

        Returns:
            List: Список устройств (pynetbox Record)
        """
        params = {}
        if site:
            params["site"] = site
        if role:
            params["role"] = role
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
        # Ищем IP-адрес
        ip_obj = self.api.ipam.ip_addresses.get(address=ip)
        if ip_obj and ip_obj.assigned_object:
            # Получаем интерфейс и его устройство
            interface = ip_obj.assigned_object
            if hasattr(interface, "device"):
                return interface.device
        return None

    # ==================== ИНТЕРФЕЙСЫ ====================

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

        Args:
            device_id: ID устройства
            interface_name: Имя интерфейса

        Returns:
            Интерфейс или None
        """
        interfaces = list(self.api.dcim.interfaces.filter(
            device_id=device_id,
            name=interface_name,
        ))
        if interfaces:
            return interfaces[0]
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
        logger.info(f"Создан интерфейс: {name} на устройстве {device_id}")
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
            logger.info(f"Обновлён интерфейс: {interface.name}")
        return interface

    # ==================== IP-АДРЕСА ====================

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
        logger.info(f"Создан IP-адрес: {address}")
        return ip

    # ==================== VLAN ====================

    def get_vlans(
        self,
        site: Optional[str] = None,
        **filters,
    ) -> List[Any]:
        """
        Получает список VLAN.

        Args:
            site: Фильтр по сайту
            **filters: Дополнительные фильтры

        Returns:
            List: Список VLAN
        """
        params = {}
        if site:
            params["site"] = site
        params.update(filters)

        vlans = list(self.api.ipam.vlans.filter(**params))
        logger.debug(f"Получено VLAN: {len(vlans)}")
        return vlans

    def get_vlan_by_vid(self, vid: int, site: Optional[str] = None) -> Optional[Any]:
        """
        Находит VLAN по номеру.

        Args:
            vid: Номер VLAN
            site: Сайт (name или slug, опционально)

        Returns:
            VLAN или None
        """
        params = {"vid": vid}
        if site:
            # Конвертируем name в slug
            site_slug = site.lower().replace(" ", "-")
            params["site"] = site_slug
        return self.api.ipam.vlans.get(**params)

    def create_vlan(
        self,
        vid: int,
        name: str,
        site: Optional[str] = None,
        status: str = "active",
        description: str = "",
        **kwargs,
    ) -> Any:
        """
        Создаёт VLAN в NetBox.

        Args:
            vid: Номер VLAN (1-4094)
            name: Название VLAN
            site: Сайт (slug или id)
            status: Статус (active, reserved, deprecated)
            description: Описание
            **kwargs: Дополнительные параметры

        Returns:
            Созданный VLAN
        """
        data = {
            "vid": vid,
            "name": name,
            "status": status,
            **kwargs,
        }

        if description:
            data["description"] = description

        if site:
            # Получаем site объект
            site_obj = self.api.dcim.sites.get(slug=site)
            if not site_obj:
                site_obj = self.api.dcim.sites.get(name=site)
            if site_obj:
                data["site"] = site_obj.id

        vlan = self.api.ipam.vlans.create(data)
        logger.info(f"Создан VLAN: {vid} ({name})")
        return vlan

    def update_interface_vlan(
        self,
        interface_id: int,
        mode: str = "access",
        untagged_vlan: Optional[int] = None,
        tagged_vlans: Optional[List[int]] = None,
    ) -> Any:
        """
        Обновляет VLAN привязку интерфейса.

        Args:
            interface_id: ID интерфейса
            mode: Режим порта (access, tagged, tagged-all)
            untagged_vlan: ID VLAN для untagged трафика
            tagged_vlans: Список ID VLAN для tagged трафика

        Returns:
            Обновлённый интерфейс
        """
        interface = self.api.dcim.interfaces.get(interface_id)
        if not interface:
            logger.warning(f"Интерфейс {interface_id} не найден")
            return None

        updates = {"mode": mode}

        if untagged_vlan:
            updates["untagged_vlan"] = untagged_vlan

        if tagged_vlans:
            updates["tagged_vlans"] = tagged_vlans

        interface.update(updates)
        logger.debug(f"Обновлён интерфейс {interface.name}: mode={mode}")
        return interface

    # ==================== INVENTORY ITEMS ====================

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
            name: Имя компонента (например "GigabitEthernet0/1 SFP")
            manufacturer: Производитель
            part_id: Part ID / Product ID (модель)
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
            # Получаем или создаём manufacturer
            mfr = self.api.dcim.manufacturers.get(slug=manufacturer.lower())
            if not mfr:
                mfr = self.api.dcim.manufacturers.get(name=manufacturer)
            if mfr:
                data["manufacturer"] = mfr.id

        item = self.api.dcim.inventory_items.create(data)
        logger.info(f"Создан inventory item: {name} (serial={serial})")
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
            item.update(updates)
            logger.debug(f"Обновлён inventory item: {item.name}")
        return item

    # ==================== MAC-АДРЕСА (NetBox 4.x) ====================

    def assign_mac_to_interface(
        self,
        interface_id: int,
        mac_address: str,
    ) -> Any:
        """
        Назначает MAC-адрес интерфейсу (NetBox 4.x).

        В NetBox 4.x MAC-адреса — отдельная модель dcim.mac-addresses.
        Этот метод создаёт MAC-адрес и привязывает к интерфейсу.

        Args:
            interface_id: ID интерфейса
            mac_address: MAC-адрес в формате AA:BB:CC:DD:EE:FF

        Returns:
            Созданный MAC-адрес объект или None
        """
        if not mac_address:
            return None

        # Проверяем, существует ли уже такой MAC на этом интерфейсе
        existing = list(self.api.dcim.mac_addresses.filter(
            assigned_object_type="dcim.interface",
            assigned_object_id=interface_id,
            mac_address=mac_address,
        ))
        if existing:
            logger.debug(f"MAC {mac_address} уже привязан к интерфейсу {interface_id}")
            return existing[0]

        # Создаём новый MAC-адрес
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
