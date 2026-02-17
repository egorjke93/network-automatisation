# 16. NetBox Client Deep Dive -- полный разбор клиента NetBox API

> **Предварительное чтение:** [05_SYNC_NETBOX.md](05_SYNC_NETBOX.md) (обзор sync), [09_MIXINS_PATTERNS.md](09_MIXINS_PATTERNS.md) (паттерн mixin)
>
> Этот документ разбирает **клиентский слой** -- все методы для работы с NetBox API.
> Doc 11 покрывает **sync layer** (сравнение и синхронизация). Здесь мы разбираем **client layer** -- как именно мы общаемся с NetBox REST API через pynetbox.

---

## Содержание

1. [Архитектура клиента](#1-архитектура-клиента)
2. [NetBoxClientBase -- инициализация](#2-netboxclientbase----инициализация)
3. [DevicesMixin -- устройства](#3-devicesmixin----устройства)
4. [InterfacesMixin -- интерфейсы](#4-interfacesmixin----интерфейсы)
5. [IPAddressesMixin -- IP-адреса и кабели](#5-ipaddressesmixin----ip-адреса-и-кабели)
6. [VLANsMixin -- VLAN](#6-vlansmixin----vlan)
7. [InventoryMixin -- компоненты оборудования](#7-inventorymixin----компоненты-оборудования)
8. [DCIMMixin -- справочники и MAC](#8-dcimmixin----справочники-и-mac)
9. [Как sync использует client](#9-как-sync-использует-client)
10. [pynetbox -- что это и как работает](#10-pynetbox----что-это-и-как-работает)
11. [Паттерны и соглашения](#11-паттерны-и-соглашения)

---

## 1. Архитектура клиента

### Mixin-структура

```python
# Файл: netbox/client/main.py
class NetBoxClient(
    DevicesMixin,       # устройства: get, search by name/IP/MAC
    InterfacesMixin,    # интерфейсы: CRUD + bulk
    IPAddressesMixin,   # IP-адреса, кабели: CRUD + bulk
    VLANsMixin,         # VLAN: get, create, update interface VLAN
    InventoryMixin,     # inventory items: CRUD + bulk
    DCIMMixin,          # справочники + MAC: device types, manufacturers, roles, sites, platforms
    NetBoxClientBase,   # инициализация: pynetbox.api(url, token)
):
    pass
```

Клиент -- **зеркальная копия** паттерна `NetBoxSync`: пустой класс, собранный из mixins. Каждый mixin отвечает за свою предметную область.

### Связь с NetBox REST API

```
NetBoxClient
    |
    +-- self.api (pynetbox.Api)
         |
         +-- self.api.dcim          -- DCIM приложение
         |    +-- .devices          -- /api/dcim/devices/
         |    +-- .interfaces       -- /api/dcim/interfaces/
         |    +-- .device_types     -- /api/dcim/device-types/
         |    +-- .manufacturers    -- /api/dcim/manufacturers/
         |    +-- .device_roles     -- /api/dcim/device-roles/
         |    +-- .sites            -- /api/dcim/sites/
         |    +-- .platforms        -- /api/dcim/platforms/
         |    +-- .cables           -- /api/dcim/cables/
         |    +-- .inventory_items  -- /api/dcim/inventory-items/
         |    +-- .mac_addresses    -- /api/dcim/mac-addresses/ (NetBox 4.x)
         |
         +-- self.api.ipam          -- IPAM приложение
              +-- .ip_addresses     -- /api/ipam/ip-addresses/
              +-- .vlans            -- /api/ipam/vlans/
```

### Файловая структура

```
netbox/client/
├── __init__.py        # Экспорт: NetBoxClient, NetBoxClientBase
├── base.py            # NetBoxClientBase: pynetbox init, resolve helpers
├── main.py            # NetBoxClient: пустой класс = все mixins
├── devices.py         # DevicesMixin: поиск устройств
├── interfaces.py      # InterfacesMixin: CRUD + bulk интерфейсов
├── ip_addresses.py    # IPAddressesMixin: IP + кабели
├── vlans.py           # VLANsMixin: VLAN + VLAN на интерфейсах
├── inventory.py       # InventoryMixin: inventory items CRUD + bulk
└── dcim.py            # DCIMMixin: справочники + MAC
```

---

## 2. NetBoxClientBase -- инициализация

```python
# Файл: netbox/client/base.py
class NetBoxClientBase:
    def __init__(self, url=None, token=None, ssl_verify=True):
        # 1. URL: из параметра или env NETBOX_URL
        self.url = url or os.environ.get("NETBOX_URL")

        # 2. Токен: из параметра → env NETBOX_TOKEN → Credential Manager → config.yaml
        self._token = get_netbox_token(config_token=token)

        # 3. Инициализация pynetbox
        self.api = pynetbox.api(self.url, token=self._token)

        # 4. Отключение SSL если нужно
        if not ssl_verify:
            session = requests.Session()
            session.verify = False
            self.api.http_session = session
```

### Что здесь происходит

`pynetbox.api()` создаёт объект, который "знает" все эндпоинты NetBox. Через `self.api.dcim.devices` мы обращаемся к `/api/dcim/devices/` -- pynetbox сам формирует HTTP-запросы, парсит JSON и возвращает объекты `Record`.

### Helper-методы

```python
def _resolve_site_slug(self, site_name_or_slug: str) -> Optional[str]:
    """Находит slug сайта по имени или slug."""
    # 1. Пробуем как slug
    site_obj = self.api.dcim.sites.get(slug=site_name_or_slug.lower())
    # 2. Пробуем как имя
    site_obj = self.api.dcim.sites.get(name=site_name_or_slug)
    # 3. Частичное совпадение
    sites = list(self.api.dcim.sites.filter(name__ic=site_name_or_slug))

def _resolve_role_slug(self, role_name_or_slug: str) -> Optional[str]:
    """Находит slug роли по имени или slug."""
    # Та же логика: slug → имя → частичное совпадение
```

Эти хелперы позволяют передавать в методы клиента как slug (`"main"`), так и имя (`"Main Office"`). Используются в `DevicesMixin.get_devices()`.

---

## 3. DevicesMixin -- устройства

**Файл:** `netbox/client/devices.py` (134 строки)

### 3.1 `get_devices()` -- получение списка

```python
def get_devices(self, site=None, role=None, status=None, **filters) -> List[Any]:
    params = {}
    if site:
        site_slug = self._resolve_site_slug(site)   # "Main" → "main"
        if site_slug:
            params["site"] = site_slug
        else:
            return []  # Сайт не найден — пустой результат, не ошибка
    if role:
        role_slug = self._resolve_role_slug(role)
        params["role"] = role_slug
    if status:
        params["status"] = status
    params.update(filters)

    return list(self.api.dcim.devices.filter(**params))
    # GET /api/dcim/devices/?site=main&role=switch&status=active
```

### Что здесь происходит

`self.api.dcim.devices.filter(**params)` возвращает **генератор** pynetbox. `list()` выполняет все запросы (с пагинацией) и возвращает список `Record`. Без `list()` данные загружаются лениво.

### 3.2 `get_device_by_name()` -- поиск по имени

```python
def get_device_by_name(self, name: str) -> Optional[Any]:
    return self.api.dcim.devices.get(name=name)
    # GET /api/dcim/devices/?name=switch-01&limit=1
```

`.get()` vs `.filter()`:
- `.get()` -- возвращает **один объект** или `None`. Если нашлось несколько -- `ValueError`
- `.filter()` -- возвращает **генератор** (может быть 0, 1, N объектов)

### 3.3 `get_device_by_ip()` -- поиск по IP

```python
def get_device_by_ip(self, ip: str) -> Optional[Any]:
    # 1. Ищем IP-адрес в IPAM
    ip_obj = self.api.ipam.ip_addresses.get(address=ip)
    # GET /api/ipam/ip-addresses/?address=10.0.0.1

    # 2. IP привязан к интерфейсу → интерфейс принадлежит устройству
    if ip_obj and ip_obj.assigned_object:
        interface = ip_obj.assigned_object
        if hasattr(interface, "device"):
            return interface.device
    return None
```

### Что здесь происходит

Цепочка: IP → assigned_object (интерфейс) → device. Pynetbox автоматически "подгружает" связанные объекты через lazy loading (дополнительные GET-запросы при обращении к атрибутам).

### 3.4 `get_device_by_mac()` -- поиск по MAC

```python
def get_device_by_mac(self, mac: str) -> Optional[Any]:
    # Нормализация: "aa:bb:cc:dd:ee:ff" / "aabb.ccdd.eeff" / "AA-BB-CC-DD-EE-FF"
    mac_normalized = mac.replace(":", "").replace("-", "").replace(".", "").lower()
    mac_formatted = ":".join(mac_normalized[i:i+2] for i in range(0, 12, 2))
    # → "aa:bb:cc:dd:ee:ff"

    # Стратегия 1: Таблица MAC (NetBox 4.x)
    mac_objs = list(self.api.dcim.mac_addresses.filter(mac_address=mac_formatted))
    if mac_objs:
        for mac_obj in mac_objs:
            if mac_obj.assigned_object and hasattr(mac_obj.assigned_object, "device"):
                return mac_obj.assigned_object.device

    # Стратегия 2: Fallback на поле mac_address в интерфейсах
    interfaces = list(self.api.dcim.interfaces.filter(mac_address=mac_formatted))
    if interfaces and interfaces[0].device:
        return interfaces[0].device

    return None
```

### Что здесь происходит

NetBox 4.x вынес MAC-адреса в отдельную таблицу `dcim.mac_addresses`. Но для совместимости со старыми версиями также ищем в поле `mac_address` интерфейса.

---

## 4. InterfacesMixin -- интерфейсы

**Файл:** `netbox/client/interfaces.py` (180 строк)

### 4.1 `get_interfaces()` -- получение списка

```python
def get_interfaces(self, device_id=None, device_name=None, **filters) -> List[Any]:
    params = {}
    if device_id:
        params["device_id"] = device_id
    if device_name:
        params["device"] = device_name
    params.update(filters)
    return list(self.api.dcim.interfaces.filter(**params))
    # GET /api/dcim/interfaces/?device_id=42
```

### 4.2 `get_interface_by_name()` -- поиск с нормализацией

```python
def get_interface_by_name(self, device_id: int, interface_name: str) -> Optional[Any]:
    from ...core.constants import normalize_interface_full

    # 1. Точное совпадение
    interfaces = list(self.api.dcim.interfaces.filter(
        device_id=device_id, name=interface_name,
    ))
    if interfaces:
        return interfaces[0]

    # 2. Нормализованное имя: Po1 → Port-channel1
    normalized_name = normalize_interface_full(interface_name)
    if normalized_name != interface_name:
        interfaces = list(self.api.dcim.interfaces.filter(
            device_id=device_id, name=normalized_name,
        ))
        if interfaces:
            return interfaces[0]

    # 3. Для LAG — регистронезависимый поиск по всем интерфейсам
    if interface_name.lower().startswith(("po", "port-channel", "ag", "aggregateport")):
        all_interfaces = list(self.api.dcim.interfaces.filter(device_id=device_id))
        name_lower = normalized_name.lower()
        for intf in all_interfaces:
            if intf.name.lower() == name_lower:
                return intf

    return None
```

### Что здесь происходит

Три стратегии поиска:
1. **Точное** -- `GigabitEthernet0/1` == `GigabitEthernet0/1`
2. **Нормализованное** -- `Po1` → `Port-channel1` через маппинг `INTERFACE_FULL_MAP`
3. **Case-insensitive** -- только для LAG, т.к. разные платформы пишут по-разному (`Port-Channel1` vs `port-channel1`)

### 4.3 CRUD-методы

```python
def create_interface(self, device_id, name, interface_type="1000base-t",
                     description="", enabled=True, **kwargs) -> Any:
    data = {
        "device": device_id,
        "name": name,
        "type": interface_type,     # "1000base-t", "10gbase-x-sfpp", "lag"
        "description": description,
        "enabled": enabled,
        **kwargs,
    }
    return self.api.dcim.interfaces.create(data)
    # POST /api/dcim/interfaces/

def update_interface(self, interface_id, **updates) -> Any:
    interface = self.api.dcim.interfaces.get(interface_id)
    interface.update(updates)       # PATCH /api/dcim/interfaces/{id}/
    return interface
```

### 4.4 Bulk-операции

```python
# Создание N интерфейсов одним POST
def bulk_create_interfaces(self, interfaces_data: List[dict]) -> List[Any]:
    if not interfaces_data:
        return []
    result = self.api.dcim.interfaces.create(interfaces_data)
    # POST /api/dcim/interfaces/ с телом [{...}, {...}, ...]
    created = result if isinstance(result, list) else [result]
    return created

# Обновление N интерфейсов одним PATCH
def bulk_update_interfaces(self, updates: List[dict]) -> List[Any]:
    # Каждый dict должен содержать 'id'!
    result = self.api.dcim.interfaces.update(updates)
    # PATCH /api/dcim/interfaces/ с телом [{"id": 1, "description": "..."}, ...]
    return result if isinstance(result, list) else [result]

# Удаление N интерфейсов одним DELETE
def bulk_delete_interfaces(self, ids: List[int]) -> bool:
    self.api.dcim.interfaces.delete(ids)
    # DELETE /api/dcim/interfaces/ с телом [{"id": 1}, {"id": 2}, ...]
    return True
```

### Зачем `result if isinstance(result, list) else [result]`?

Pynetbox при создании **одного** объекта возвращает сам объект, а при **нескольких** -- список. Мы нормализуем результат в список для единообразия:

```python
# Один объект:
client.api.dcim.interfaces.create({"name": "Gi0/1", ...})
# → Record(name="Gi0/1")

# Несколько объектов:
client.api.dcim.interfaces.create([{"name": "Gi0/1"}, {"name": "Gi0/2"}])
# → [Record(name="Gi0/1"), Record(name="Gi0/2")]
```

---

## 5. IPAddressesMixin -- IP-адреса и кабели

**Файл:** `netbox/client/ip_addresses.py` (182 строки)

### 5.1 Получение

```python
def get_ip_addresses(self, device_id=None, interface_id=None, **filters) -> List[Any]:
    params = {}
    if device_id:
        params["device_id"] = device_id
    return list(self.api.ipam.ip_addresses.filter(**params))
    # GET /api/ipam/ip-addresses/?device_id=42

def get_ip_by_address(self, address: str) -> Optional[Any]:
    ip_only = address.split("/")[0]     # "10.0.0.1/24" → "10.0.0.1"
    ip_obj = self.api.ipam.ip_addresses.get(address=ip_only)
    if ip_obj:
        return ip_obj
    # Fallback: filter вместо get (для множественных результатов)
    ips = list(self.api.ipam.ip_addresses.filter(address=ip_only))
    return ips[0] if ips else None

def get_cables(self, device_id=None, **filters) -> List[Any]:
    params = {}
    if device_id:
        params["device_id"] = device_id
    return list(self.api.dcim.cables.filter(**params))
    # GET /api/dcim/cables/?device_id=42
```

### 5.2 Создание IP

```python
def create_ip_address(self, address, interface_id=None, status="active", **kwargs) -> Any:
    data = {
        "address": address,             # "10.0.0.1/24" -- с маской!
        "status": status,
        **kwargs,
    }
    if interface_id:
        data["assigned_object_type"] = "dcim.interface"
        data["assigned_object_id"] = interface_id
    return self.api.ipam.ip_addresses.create(data)
```

### Что здесь важно

IP-адрес в NetBox **всегда хранится с маской** (`10.0.0.1/24`). При привязке к интерфейсу используются generic foreign key:
- `assigned_object_type` = `"dcim.interface"` (тип объекта)
- `assigned_object_id` = ID интерфейса (ID объекта)

### 5.3 Bulk-операции

Аналогичны интерфейсам:
- `bulk_create_ip_addresses(ip_data)` → POST список
- `bulk_update_ip_addresses(updates)` → PATCH список (каждый с `id`)
- `bulk_delete_ip_addresses(ids)` → DELETE список ID

---

## 6. VLANsMixin -- VLAN

**Файл:** `netbox/client/vlans.py` (137 строк)

### 6.1 Получение

```python
def get_vlans(self, site=None, **filters) -> List[Any]:
    params = {}
    if site:
        site_slug = site.lower().replace(" ", "-")  # "Main Office" → "main-office"
        params["site"] = site_slug
    return list(self.api.ipam.vlans.filter(**params))

def get_vlan_by_vid(self, vid: int, site=None) -> Optional[Any]:
    params = {"vid": vid}
    if site:
        site_slug = site.lower().replace(" ", "-")
        params["site"] = site_slug
    vlans = list(self.api.ipam.vlans.filter(**params))
    return vlans[0] if vlans else None
```

### Почему `filter()` а не `get()` для VLAN?

VLAN **не уникален глобально** -- на разных сайтах может быть VLAN 100 с разными именами. `.get(vid=100)` выбросит `ValueError` если VLAN 100 есть на нескольких сайтах. Поэтому используем `.filter()` + `[0]`.

### 6.2 Создание и назначение

```python
def create_vlan(self, vid, name, site=None, status="active", description="", **kwargs):
    data = {"vid": vid, "name": name, "status": status, **kwargs}
    if site:
        # Находим site object, чтобы получить его ID
        site_obj = self.api.dcim.sites.get(slug=site)
        if not site_obj:
            site_obj = self.api.dcim.sites.get(name=site)
        if site_obj:
            data["site"] = site_obj.id
    return self.api.ipam.vlans.create(data)

def update_interface_vlan(self, interface_id, mode="access",
                          untagged_vlan=None, tagged_vlans=None):
    """Обновляет VLAN-привязку интерфейса."""
    interface = self.api.dcim.interfaces.get(interface_id)
    updates = {"mode": mode}            # "access", "tagged", "tagged-all"
    if untagged_vlan:
        updates["untagged_vlan"] = untagged_vlan    # ID VLAN объекта
    if tagged_vlans:
        updates["tagged_vlans"] = tagged_vlans      # Список ID VLAN
    interface.update(updates)
    return interface
```

### Что здесь важно

VLAN назначаются через **интерфейс**, не через отдельный endpoint. Поле `mode` определяет тип порта:
- `"access"` -- один VLAN (untagged)
- `"tagged"` -- несколько VLAN (tagged list + один untagged)
- `"tagged-all"` -- все VLAN

---

## 7. InventoryMixin -- компоненты оборудования

**Файл:** `netbox/client/inventory.py` (217 строк)

### 7.1 Получение

```python
def get_inventory_items(self, device_id=None, device_name=None, **filters):
    params = {}
    if device_id:
        params["device_id"] = device_id
    if device_name:
        params["device"] = device_name
    return list(self.api.dcim.inventory_items.filter(**params))

def get_inventory_item(self, device_id, name):
    return self.api.dcim.inventory_items.get(device_id=device_id, name=name)
```

### 7.2 CRUD

```python
def create_inventory_item(self, device_id, name, manufacturer=None,
                          part_id="", serial="", description="", **kwargs):
    data = {
        "device": device_id,
        "name": name,
        "part_id": part_id,
        "serial": serial,
        "description": description,
        "discovered": True,        # Маркер: создано автоматически
        **kwargs,
    }
    # Manufacturer: ищем по slug → по имени
    if manufacturer:
        mfr = self.api.dcim.manufacturers.get(slug=manufacturer.lower())
        if not mfr:
            mfr = self.api.dcim.manufacturers.get(name=manufacturer)
        if mfr:
            data["manufacturer"] = mfr.id
    return self.api.dcim.inventory_items.create(data)
```

### 7.3 Update с автоматическим resolve manufacturer

```python
def update_inventory_item(self, item_id, **updates):
    item = self.api.dcim.inventory_items.get(item_id)
    if "manufacturer" in updates:
        mfr_value = updates["manufacturer"]
        if isinstance(mfr_value, str):
            # Строка → ищем ID
            mfr = self.api.dcim.manufacturers.get(slug=mfr_value.lower())
            if not mfr:
                mfr = self.api.dcim.manufacturers.get(name=mfr_value)
            if mfr:
                updates["manufacturer"] = mfr.id
            else:
                # Автосоздание manufacturer
                slug = re.sub(r'[^a-z0-9-]', '-', mfr_value.lower()).strip('-')
                mfr = self.api.dcim.manufacturers.create({"name": mfr_value, "slug": slug})
                updates["manufacturer"] = mfr.id
    item.update(updates)
    return item
```

### Что здесь интересно

`update_inventory_item()` -- единственный метод, где manufacturer **автоматически создаётся** если его нет. В остальных методах (create_device и др.) за это отвечает sync layer через `_get_or_create_manufacturer()`.

### 7.4 Bulk-операции

```python
bulk_create_inventory_items(items_data)     # POST список
bulk_update_inventory_items(updates)        # PATCH список (с id)
bulk_delete_inventory_items(ids)            # DELETE список ID

# delete единичного item:
def delete_inventory_item(self, item_id):
    item = self.api.dcim.inventory_items.get(item_id)
    if item:
        item.delete()
        return True
    return False
```

---

## 8. DCIMMixin -- справочники и MAC

**Файл:** `netbox/client/dcim.py` (377 строк)

DCIMMixin -- самый большой клиентский mixin. Отвечает за **справочные данные** и **MAC-адреса**.

### 8.1 MAC-адреса (NetBox 4.x)

NetBox 4.x вынес MAC в отдельную таблицу `dcim.mac_addresses`. MAC привязывается к интерфейсу через generic foreign key.

```python
def assign_mac_to_interface(self, interface_id: int, mac_address: str):
    # 1. Проверяем: уже привязан?
    existing = list(self.api.dcim.mac_addresses.filter(
        assigned_object_type="dcim.interface",
        assigned_object_id=interface_id,
        mac_address=mac_address,
    ))
    if existing:
        return existing[0]      # Идемпотентность!

    # 2. Создаём привязку
    return self.api.dcim.mac_addresses.create({
        "mac_address": mac_address,
        "assigned_object_type": "dcim.interface",
        "assigned_object_id": interface_id,
    })
```

### 8.2 Bulk MAC с fallback

```python
def bulk_assign_macs(self, mac_assignments: list) -> int:
    """mac_assignments = [(interface_id, mac_address), ...]"""
    batch = [
        {
            "mac_address": mac,
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": intf_id,
        }
        for intf_id, mac in mac_assignments if mac
    ]
    try:
        result = self.api.dcim.mac_addresses.create(batch)
        return len(result if isinstance(result, list) else [result])
    except Exception:
        # Fallback: поштучно
        assigned = 0
        for intf_id, mac in mac_assignments:
            try:
                self.assign_mac_to_interface(intf_id, mac)
                assigned += 1
            except Exception:
                pass
        return assigned
```

### Почему fallback?

Bulk MAC может упасть если один из MAC уже существует. NetBox не делает partial success для bulk -- падает весь batch. Fallback обрабатывает каждый MAC отдельно, пропуская ошибки.

### 8.3 Паттерн get-or-create для справочников

Все справочники (manufacturer, device_type, role, site, platform) используют единый паттерн:

```python
# Поиск: по slug → по имени
def get_manufacturer(self, name: str):
    slug = name.lower().replace(" ", "-")
    mfr = self.api.dcim.manufacturers.get(slug=slug)
    if mfr:
        return mfr
    return self.api.dcim.manufacturers.get(name=name)

# Получить или создать
def get_or_create_manufacturer(self, name: str):
    existing = self.get_manufacturer(name)
    if existing:
        return existing
    slug = name.lower().replace(" ", "-")
    return self.api.dcim.manufacturers.create({
        "name": name,
        "slug": slug,
    })
```

### 8.4 Все справочники -- одинаковый паттерн

| Метод | Endpoint | Slug |
|-------|----------|------|
| `get/create_manufacturer(name)` | `dcim.manufacturers` | `name.lower().replace(" ", "-")` |
| `get/create_device_type(model, mfr)` | `dcim.device_types` | `model.lower().replace(" ", "-").replace("/", "-")` |
| `get/create_device_role(name, color)` | `dcim.device_roles` | `name.lower().replace(" ", "-")` |
| `get/create_site(name, status)` | `dcim.sites` | `name.lower().replace(" ", "-")` |
| `get/create_platform(name, mfr)` | `dcim.platforms` | `name.lower().replace(" ", "-").replace("_", "-")` |

### Что здесь важно

- **Slug** -- уникальный URL-friendly идентификатор в NetBox. Всегда lowercase, дефисы вместо пробелов
- **Platform slug** дополнительно заменяет `_` на `-`: `cisco_ios` → `cisco-ios`
- **Device Type** требует `manufacturer_id` при создании
- **Device Role** имеет `color` (hex без #) и `vm_role` (можно ли использовать для VM)
- **Site** создаётся со статусом `"active"` по умолчанию

---

## 9. Как sync использует client

### Полная цепочка вызова

```
CLI: sync-netbox --interfaces
  |
  +-- cmd_sync_netbox()                              # cli/commands/sync.py
       |
       +-- NetBoxSync(client, dry_run=True)          # sync/main.py
       |    |
       |    +-- self.client = NetBoxClient(...)       # client/main.py
       |
       +-- sync.sync_interfaces("switch-01", intfs)  # sync/interfaces.py
            |
            +-- self.client.get_device_by_name("switch-01")
            |    # → DevicesMixin.get_device_by_name()
            |    # → self.api.dcim.devices.get(name="switch-01")
            |    # → GET /api/dcim/devices/?name=switch-01
            |
            +-- self.client.get_interfaces(device_id=42)
            |    # → InterfacesMixin.get_interfaces()
            |    # → self.api.dcim.interfaces.filter(device_id=42)
            |    # → GET /api/dcim/interfaces/?device_id=42
            |
            +-- SyncComparator().compare_interfaces(local, remote)
            |    # Чистое сравнение без API (domain layer)
            |    # → SyncDiff(to_create=3, to_update=2, to_delete=1)
            |
            +-- self.client.bulk_create_interfaces([...])
            |    # → InterfacesMixin.bulk_create_interfaces()
            |    # → self.api.dcim.interfaces.create([{...}, {...}])
            |    # → POST /api/dcim/interfaces/
            |
            +-- self.client.bulk_update_interfaces([...])
            |    # → InterfacesMixin.bulk_update_interfaces()
            |    # → self.api.dcim.interfaces.update([{id:1,...}, ...])
            |    # → PATCH /api/dcim/interfaces/
            |
            +-- self.client.bulk_delete_interfaces([1, 2, 3])
                 # → InterfacesMixin.bulk_delete_interfaces()
                 # → self.api.dcim.interfaces.delete([1, 2, 3])
                 # → DELETE /api/dcim/interfaces/
```

### Разделение ответственности

```
┌──────────────────────────────────────────────┐
│ Sync Layer (netbox/sync/)                    │
│  - Сравнение данных (SyncComparator)         │
│  - Логика: что создать/обновить/удалить      │
│  - Подготовка данных (_build_create_data)     │
│  - Кэширование устройств и VLAN              │
│  - Batch с fallback (_batch_with_fallback)    │
│  - dry_run проверка                          │
└──────────────────┬───────────────────────────┘
                   │ вызывает self.client.xxx()
                   ▼
┌──────────────────────────────────────────────┐
│ Client Layer (netbox/client/)                │
│  - HTTP-запросы к NetBox API через pynetbox  │
│  - CRUD операции (get, create, update, delete)│
│  - Bulk операции                             │
│  - Нормализация имён (slug resolution)       │
│  - Поиск объектов (by name, IP, MAC)         │
│  - НЕ содержит бизнес-логику                 │
└──────────────────┬───────────────────────────┘
                   │ HTTP через pynetbox
                   ▼
┌──────────────────────────────────────────────┐
│ NetBox REST API                              │
│  - /api/dcim/devices/                        │
│  - /api/dcim/interfaces/                     │
│  - /api/ipam/ip-addresses/                   │
│  - /api/ipam/vlans/                          │
└──────────────────────────────────────────────┘
```

---

## 10. pynetbox -- что это и как работает

### Record -- объект pynetbox

Каждый объект из NetBox API оборачивается в `Record`:

```python
device = client.get_device_by_name("switch-01")

# Атрибуты — поля из JSON ответа API
device.id           # 42
device.name         # "switch-01"
device.status       # Record(value="active", label="Active")
device.site         # Record(id=1, name="Main", slug="main")
device.device_type  # Record(id=5, model="C2960X-48", ...)
device.primary_ip4  # Record(id=10, address="10.0.0.1/24") или None

# Вложенные объекты -- lazy loading
device.site.name    # "Main" — может вызвать дополнительный GET!
```

### Lazy loading -- осторожно!

```python
# Плохо: N+1 запросов
for intf in client.get_interfaces(device_id=42):
    # Каждое обращение к intf.device.name — это GET запрос!
    print(intf.device.name)

# Хорошо: один запрос, потом работаем с кэшем
device = client.get_device_by_name("switch-01")
for intf in client.get_interfaces(device_id=device.id):
    print(device.name)  # Уже загружен
```

### Основные методы pynetbox endpoint

```python
endpoint = self.api.dcim.interfaces

# GET один объект (возвращает Record или None)
endpoint.get(name="Gi0/1", device_id=42)

# GET список объектов (возвращает генератор RecordSet)
endpoint.filter(device_id=42, enabled=True)

# GET все объекты
endpoint.all()

# POST создание (один dict → Record, список → List[Record])
endpoint.create({"name": "Gi0/1", "device": 42, "type": "1000base-t"})
endpoint.create([{...}, {...}])     # Bulk create

# PATCH обновление (список dict с id)
endpoint.update([{"id": 1, "description": "new"}, ...])

# DELETE удаление (список int ID)
endpoint.delete([1, 2, 3])

# Обновление конкретного объекта
obj = endpoint.get(42)
obj.update({"description": "new"})  # PATCH /api/dcim/interfaces/42/
obj.save()                          # Альтернатива: obj.description = "new"; obj.save()
obj.delete()                        # DELETE /api/dcim/interfaces/42/
```

---

## 11. Паттерны и соглашения

### 11.1 Все mixins используют `self.api`

Mixins не имеют `__init__`. Они полагаются на `NetBoxClientBase.__init__()` который создаёт `self.api`. Это работает благодаря MRO (Method Resolution Order):

```python
class NetBoxClient(DevicesMixin, InterfacesMixin, ..., NetBoxClientBase):
    pass

# MRO: NetBoxClient → DevicesMixin → ... → NetBoxClientBase → object
# __init__ вызывается у NetBoxClientBase (первый класс с __init__)
# После этого self.api доступен во всех mixins
```

### 11.2 Slug generation

Почти все справочные объекты в NetBox требуют `slug`:

```python
# Стандартная генерация:
slug = name.lower().replace(" ", "-")
# "Main Office" → "main-office"

# Platform с underscore:
slug = name.lower().replace(" ", "-").replace("_", "-")
# "cisco_ios" → "cisco-ios"

# Device Type с slash:
slug = model.lower().replace(" ", "-").replace("/", "-")
# "C9200L-24P-4X" → "c9200l-24p-4x"
```

### 11.3 Паттерн None-safe

Все методы клиента проверяют пустые входные данные:

```python
def bulk_create_interfaces(self, interfaces_data):
    if not interfaces_data:     # Пустой список → не делаем запрос
        return []
    ...

def get_device_by_mac(self, mac):
    if not mac:                 # None или "" → сразу None
        return None
    ...
```

### 11.4 Логирование

```python
logger.debug(...)       # Рутинные операции (получение, обновление)
logger.info(...)        # Создание новых объектов
logger.warning(...)     # Ошибки, не найдены объекты
```

### 11.5 Сводная таблица всех методов клиента

| Mixin | Метод | Тип | API Endpoint |
|-------|-------|-----|-------------|
| **DevicesMixin** | `get_devices(site, role, status)` | GET | `dcim.devices` |
| | `get_device_by_name(name)` | GET | `dcim.devices` |
| | `get_device_by_ip(ip)` | GET | `ipam.ip_addresses` → `device` |
| | `get_device_by_mac(mac)` | GET | `dcim.mac_addresses` / `dcim.interfaces` |
| **InterfacesMixin** | `get_interfaces(device_id)` | GET | `dcim.interfaces` |
| | `get_interface_by_name(device_id, name)` | GET | `dcim.interfaces` |
| | `create_interface(device_id, name, type)` | POST | `dcim.interfaces` |
| | `update_interface(interface_id, **updates)` | PATCH | `dcim.interfaces` |
| | `bulk_create_interfaces(data)` | POST | `dcim.interfaces` |
| | `bulk_update_interfaces(updates)` | PATCH | `dcim.interfaces` |
| | `bulk_delete_interfaces(ids)` | DELETE | `dcim.interfaces` |
| **IPAddressesMixin** | `get_ip_addresses(device_id)` | GET | `ipam.ip_addresses` |
| | `get_ip_by_address(address)` | GET | `ipam.ip_addresses` |
| | `get_cables(device_id)` | GET | `dcim.cables` |
| | `create_ip_address(address, intf_id)` | POST | `ipam.ip_addresses` |
| | `bulk_create_ip_addresses(data)` | POST | `ipam.ip_addresses` |
| | `bulk_update_ip_addresses(updates)` | PATCH | `ipam.ip_addresses` |
| | `bulk_delete_ip_addresses(ids)` | DELETE | `ipam.ip_addresses` |
| **VLANsMixin** | `get_vlans(site)` | GET | `ipam.vlans` |
| | `get_vlan_by_vid(vid, site)` | GET | `ipam.vlans` |
| | `create_vlan(vid, name, site)` | POST | `ipam.vlans` |
| | `update_interface_vlan(intf_id, mode)` | PATCH | `dcim.interfaces` |
| **InventoryMixin** | `get_inventory_items(device_id)` | GET | `dcim.inventory_items` |
| | `get_inventory_item(device_id, name)` | GET | `dcim.inventory_items` |
| | `create_inventory_item(device_id, name)` | POST | `dcim.inventory_items` |
| | `update_inventory_item(item_id)` | PATCH | `dcim.inventory_items` |
| | `delete_inventory_item(item_id)` | DELETE | `dcim.inventory_items` |
| | `bulk_create_inventory_items(data)` | POST | `dcim.inventory_items` |
| | `bulk_update_inventory_items(updates)` | PATCH | `dcim.inventory_items` |
| | `bulk_delete_inventory_items(ids)` | DELETE | `dcim.inventory_items` |
| **DCIMMixin** | `assign_mac_to_interface(intf_id, mac)` | POST | `dcim.mac_addresses` |
| | `bulk_assign_macs(assignments)` | POST | `dcim.mac_addresses` |
| | `get_interface_mac(intf_id)` | GET | `dcim.mac_addresses` |
| | `get/create_manufacturer(name)` | GET/POST | `dcim.manufacturers` |
| | `get/create_device_type(model, mfr)` | GET/POST | `dcim.device_types` |
| | `get/create_device_role(name)` | GET/POST | `dcim.device_roles` |
| | `get/create_site(name)` | GET/POST | `dcim.sites` |
| | `get/create_platform(name)` | GET/POST | `dcim.platforms` |

---

> **Дальнейшее чтение:**
> - [05_SYNC_NETBOX.md](05_SYNC_NETBOX.md) -- обзор sync (начальный уровень)
> - [11_SYNC_DEEP_DIVE.md](11_SYNC_DEEP_DIVE.md) -- полный разбор sync layer
> - [09_MIXINS_PATTERNS.md](09_MIXINS_PATTERNS.md) -- паттерн mixin и MRO
