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

from ..core.credentials import get_netbox_token

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

        Токен ищется в следующем порядке:
        1. Параметр token
        2. get_netbox_token() - проверяет env NETBOX_TOKEN, Credential Manager, config.yaml

        Args:
            url: URL NetBox сервера (или env NETBOX_URL)
            token: API токен (опционально, если не указан - использует get_netbox_token())
            ssl_verify: Проверять SSL сертификат

        Raises:
            ImportError: pynetbox не установлен
            ValueError: URL или токен не указаны
        """
        if not PYNETBOX_AVAILABLE:
            raise ImportError(
                "pynetbox не установлен. Установите: pip install pynetbox"
            )

        # Получаем URL из параметров или переменных окружения
        self.url = url or os.environ.get("NETBOX_URL")

        # Получаем токен через безопасное хранилище
        # Приоритет: параметр → env var → Credential Manager → config.yaml
        self._token = get_netbox_token(config_token=token)

        if not self.url:
            raise ValueError(
                "NetBox URL не указан. Укажите url или установите NETBOX_URL"
            )
        if not self._token:
            raise ValueError(
                "NetBox токен не указан. Добавьте токен в Windows Credential Manager "
                "или установите NETBOX_TOKEN. См. документацию SECURITY.md"
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
                return []  # Сайт не найден - возвращаем пустой список

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

    def _resolve_site_slug(self, site_name_or_slug: str) -> Optional[str]:
        """Находит slug сайта по имени или slug."""
        # Сначала пробуем как slug
        site_obj = self.api.dcim.sites.get(slug=site_name_or_slug.lower())
        if site_obj:
            return site_obj.slug

        # Пробуем как имя
        site_obj = self.api.dcim.sites.get(name=site_name_or_slug)
        if site_obj:
            return site_obj.slug

        # Ищем частичное совпадение
        sites = list(self.api.dcim.sites.filter(name__ic=site_name_or_slug))
        if len(sites) == 1:
            return sites[0].slug

        return None

    def _resolve_role_slug(self, role_name_or_slug: str) -> Optional[str]:
        """Находит slug роли по имени или slug."""
        # Сначала пробуем как slug
        role_obj = self.api.dcim.device_roles.get(slug=role_name_or_slug.lower())
        if role_obj:
            return role_obj.slug

        # Пробуем как имя
        role_obj = self.api.dcim.device_roles.get(name=role_name_or_slug)
        if role_obj:
            return role_obj.slug

        # Ищем частичное совпадение
        roles = list(self.api.dcim.device_roles.filter(name__ic=role_name_or_slug))
        if len(roles) == 1:
            return roles[0].slug

        return None

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

    def get_device_by_mac(self, mac: str) -> Optional[Any]:
        """
        Находит устройство по MAC-адресу.

        Поиск выполняется в таблице dcim.mac_addresses (NetBox 4.x).
        Если MAC привязан к интерфейсу, возвращает устройство этого интерфейса.

        Args:
            mac: MAC-адрес в любом формате (будет нормализован)

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

            # Fallback: ищем в интерфейсах напрямую (старый метод)
            interfaces = list(self.api.dcim.interfaces.filter(mac_address=mac_formatted))
            if interfaces and interfaces[0].device:
                device = interfaces[0].device
                logger.debug(f"Устройство найдено по MAC интерфейса {mac_formatted}: {device.name}")
                return device

        except Exception as e:
            logger.debug(f"Ошибка поиска по MAC {mac}: {e}")

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

        Поддерживает поиск по точному имени, нормализованному и регистронезависимому
        (например, Po1 → Port-channel1, port-channel1).

        Args:
            device_id: ID устройства
            interface_name: Имя интерфейса

        Returns:
            Интерфейс или None
        """
        from ..core.constants import normalize_interface_full

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
        # NX-OS: port-channel4 vs Port-channel4
        if interface_name.lower().startswith(("po", "port-channel")):
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

    def get_ip_by_address(self, address: str) -> Optional[Any]:
        """
        Находит IP-адрес по его значению.

        Args:
            address: IP-адрес (с маской или без)

        Returns:
            IPAddress объект или None
        """
        if not address:
            return None

        # Убираем маску если есть, pynetbox сам найдёт
        ip_only = address.split("/")[0]

        try:
            # Ищем по точному адресу
            ip_obj = self.api.ipam.ip_addresses.get(address=ip_only)
            if ip_obj:
                return ip_obj

            # Пробуем с фильтром (может вернуть несколько)
            ips = list(self.api.ipam.ip_addresses.filter(address=ip_only))
            if ips:
                return ips[0]

        except Exception as e:
            logger.debug(f"Ошибка поиска IP {address}: {e}")

        return None

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
            VLAN или None (первый найденный если несколько)
        """
        params = {"vid": vid}
        if site:
            # Конвертируем name в slug
            site_slug = site.lower().replace(" ", "-")
            params["site"] = site_slug
        # Используем filter вместо get чтобы избежать ошибки при дубликатах VID
        vlans = list(self.api.ipam.vlans.filter(**params))
        return vlans[0] if vlans else None

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
            **updates: Поля для обновления (manufacturer может быть строкой)

        Returns:
            Обновлённый inventory item
        """
        item = self.api.dcim.inventory_items.get(item_id)
        if item:
            # Обработка manufacturer
            if "manufacturer" in updates:
                mfr_value = updates["manufacturer"]
                if mfr_value is None:
                    # Очистка manufacturer
                    updates["manufacturer"] = None
                elif isinstance(mfr_value, str):
                    # Конвертируем имя в ID
                    mfr = self.api.dcim.manufacturers.get(slug=mfr_value.lower())
                    if not mfr:
                        mfr = self.api.dcim.manufacturers.get(name=mfr_value)
                    if mfr:
                        updates["manufacturer"] = mfr.id
                    else:
                        # Создаём manufacturer если не найден
                        import re
                        slug = re.sub(r'[^a-z0-9-]', '-', mfr_value.lower()).strip('-')
                        mfr = self.api.dcim.manufacturers.create({"name": mfr_value, "slug": slug})
                        if mfr:
                            updates["manufacturer"] = mfr.id
                        else:
                            del updates["manufacturer"]  # Не удалось создать
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
            logger.info(f"Удалён inventory item: {name}")
            return True
        return False

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

    # ==================== DEVICE TYPES ====================

    def get_device_type(
        self,
        model: str,
        manufacturer: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Находит device type по модели.

        Args:
            model: Модель устройства (C9200L-24P-4X, WS-C2960X-48FPS-L)
            manufacturer: Производитель (опционально, для уточнения)

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
        Получает или создаёт device type в NetBox.

        Args:
            model: Модель устройства (C9200L-24P-4X)
            manufacturer: Производитель (Cisco, Arista)
            slug: Slug (опционально, генерируется из model)
            u_height: Высота в юнитах (по умолчанию 1)
            is_full_depth: Полная глубина (по умолчанию True)
            **kwargs: Дополнительные параметры

        Returns:
            DeviceType объект
        """
        # Получаем или создаём manufacturer
        mfr = self.get_or_create_manufacturer(manufacturer)

        # Ищем существующий device type
        existing = self.api.dcim.device_types.get(
            model=model,
            manufacturer_id=mfr.id,
        )
        if existing:
            logger.debug(f"Device type '{model}' уже существует")
            return existing

        # Генерируем slug если не указан
        if not slug:
            slug = model.lower().replace(" ", "-").replace("/", "-")

        # Создаём новый device type
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
            name: Имя производителя (Cisco, Arista, Juniper)

        Returns:
            Manufacturer или None
        """
        # Сначала по slug
        slug = name.lower().replace(" ", "-")
        mfr = self.api.dcim.manufacturers.get(slug=slug)
        if mfr:
            return mfr

        # Затем по имени
        return self.api.dcim.manufacturers.get(name=name)

    def get_or_create_manufacturer(self, name: str) -> Any:
        """
        Получает или создаёт производителя.

        Args:
            name: Имя производителя (Cisco, Arista, Juniper)

        Returns:
            Manufacturer объект
        """
        existing = self.get_manufacturer(name)
        if existing:
            return existing

        # Создаём нового производителя
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
            name: Имя роли (Switch, Router, Firewall)

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
            name: Имя роли (Switch, Router, Firewall)
            color: Цвет в hex (по умолчанию серый)
            vm_role: Роль для виртуальных машин

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
            status: Статус (active, planned, retired)

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

        Платформа в NetBox — это NAPALM/Netmiko driver type (cisco_ios, arista_eos).

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
            name: Имя платформы (cisco_ios, cisco_iosxe, arista_eos)
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
