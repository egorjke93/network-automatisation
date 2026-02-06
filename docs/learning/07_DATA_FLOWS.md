# 07. Потоки данных -- от команды до результата

Полный разбор того, как данные проходят через все слои приложения:
от ввода CLI-команды до записи результата в файл или NetBox.

**Время чтения:** ~25 минут

**Предыдущий документ:** [06. Pipeline -- автоматизация](06_PIPELINE.md)

**Связанная документация:**
- [DATA_FLOW_LLDP.md](../DATA_FLOW_LLDP.md) -- детальный поток LLDP/CDP
- [DATA_FLOW_MATCH_MAC.md](../DATA_FLOW_MATCH_MAC.md) -- детальный поток match-mac
- [DATA_FLOW_DETAILED.md](../DATA_FLOW_DETAILED.md) -- полный путь данных (MAC)

---

## 1. Что такое поток данных

Поток данных (data flow) -- это путь, который проходит информация
от момента ввода команды до получения результата. В Network Collector
этот путь всегда состоит из одних и тех же слоёв:

```
CLI команда
    |
    v
SSH подключение к устройству
    |
    v
Текстовый вывод команды (сырой текст)
    |
    v
Парсинг (TextFSM / Regex) --> список словарей
    |
    v
Нормализация (Domain Layer) --> единый формат
    |
    v
Модель (dataclass) --> типизированный объект
    |
    v
Результат: экспорт в файл ИЛИ синхронизация с NetBox
```

Каждый слой отвечает за своё:

| Слой | Что делает | Пример файла |
|------|-----------|--------------|
| CLI | Разбирает аргументы, запускает нужный обработчик | `cli/commands/collect.py` |
| Collector | Подключается по SSH, выполняет команды | `collectors/lldp.py` |
| Parser | Превращает текст в словари | `parsers/textfsm_parser.py` |
| Normalizer | Приводит к единому формату | `core/domain/lldp.py` |
| Model | Типизированный объект | `core/models.py` |
| Exporter / Sync | Записывает результат | `exporters/`, `netbox/sync/` |

Зачем столько слоёв? Потому что каждый вендор (Cisco, Arista, Juniper)
возвращает данные в своём формате. Normalizer приводит их к единому виду,
а Model гарантирует что все поля на месте.

---

## 2. Полный пример: LLDP-сбор и создание кабелей

Это самый интересный и сложный поток. Данные проходят через все слои,
а в конце создаются кабели в NetBox.

### 2.1 Команда

```bash
python -m network_collector lldp --protocol both --format excel
```

Или для синхронизации кабелей:

```bash
python -m network_collector sync-netbox --cables --site "Office"
```

### 2.2 Диаграмма полного потока

```
CLI: cmd_lldp(args)
 |
 |   protocol = "both"
 v
LLDPCollector(protocol="both")
 |
 |   Для каждого устройства из devices.json:
 v
_collect_from_device(device)
 |
 +---> SSH подключение (Scrapli)
 |         conn.send_command("show lldp neighbors detail")
 |         conn.send_command("show cdp neighbors detail")
 |
 +---> Парсинг (TextFSM или Regex)
 |         _parse_output(raw_text, device)
 |             |
 |             +-- TextFSM (приоритет) --> [{neighbor_port_id, chassis_id, ...}]
 |             +-- Regex (fallback)    --> [{port_id, remote_hostname, ...}]
 |
 +---> Нормализация (Domain Layer)
 |         LLDPNormalizer.normalize_dicts(raw_data)
 |             |
 |             +-- _normalize_row()    --> маппинг ключей
 |             +-- merge_lldp_cdp()    --> объединение двух протоколов
 |
 +---> Результат: [{remote_port, remote_hostname, remote_mac, ...}]
 |
 v
[Экспорт ИЛИ Синхронизация]
 |
 +---> ExcelExporter.export()           --> .xlsx файл
 +---> sync_cables_from_lldp(data)      --> кабели в NetBox
```

### 2.3 Шаг 1: Парсинг текста

Устройство возвращает текст вроде такого:

```
Local Intf: Gi1/0/49
Chassis id: 001a.3008.6c00
Port id: Gi3/13
System Name: c6509-e.corp.ogk4.ru
Management Addresses:
    IP: 10.195.124.8
```

TextFSM превращает его в словарь:

```python
# Результат TextFSM парсинга
{
    "local_interface": "Gi1/0/49",
    "chassis_id": "001a.3008.6c00",
    "neighbor_port_id": "Gi3/13",
    "neighbor": "c6509-e.corp.ogk4.ru",
    "management_ip": "10.195.124.8",
}
```

Обрати внимание на имена полей: `chassis_id`, `neighbor_port_id`, `neighbor`.
Это имена из TextFSM-шаблона, а не из нашего проекта. Следующий шаг исправит это.

### 2.4 Шаг 2: Нормализация

**Файл:** `core/domain/lldp.py`

Нормализатор решает две задачи:
1. **Маппинг ключей** -- переименовывает поля в единый формат
2. **Умная логика** -- определяет, что такое `port_id` (имя интерфейса или MAC?)

```python
# Маппинг ключей: сырое имя --> нормализованное
KEY_MAPPING = {
    "neighbor": "remote_hostname",
    "system_name": "remote_hostname",
    "device_id": "remote_hostname",
    "chassis_id": "remote_mac",
    "neighbor_port_id": "remote_port",
    "management_ip": "remote_ip",
}
```

Результат нормализации:

```python
# Было (из TextFSM)                    # Стало (после нормализации)
{                                       {
    "chassis_id": "001a.3008.6c00",         "remote_mac": "001a.3008.6c00",
    "neighbor_port_id": "Gi3/13",           "remote_port": "Gi3/13",
    "neighbor": "c6509-e.corp",             "remote_hostname": "c6509-e.corp",
    "management_ip": "10.195.124.8",        "remote_ip": "10.195.124.8",
}                                           "neighbor_type": "hostname",
                                            "hostname": "our-switch",
                                            "protocol": "LLDP",
                                        }
```

Обрати внимание на `neighbor_type: "hostname"`. Нормализатор определил, что сосед
передал своё имя -- это самый надёжный способ идентификации. Другие варианты:
`mac` (сосед передал только MAC) и `ip` (только IP).

### 2.5 Шаг 3: Объединение LLDP и CDP

Когда `protocol="both"`, коллектор собирает данные по обоим протоколам
и объединяет их. CDP -- база (Cisco проприетарный, надёжнее),
LLDP дополняет MAC-адресом:

```
CDP данные (база):                 LLDP данные (дополнение):
+---------------------------+      +---------------------------+
| remote_hostname: "sw2"   |      | remote_mac: "001a.3008"   |  <-- только LLDP
| remote_port: "Gi3/13"    |      | remote_hostname: "[MAC]"  |      даёт MAC
| remote_ip: "10.195.124.8"|      +---------------------------+
| remote_platform: "WS-C"  |
+---------------------------+
              |                                  |
              +------------- merge --------------+
                              |
                              v
              Объединённый результат:
              +---------------------------+
              | remote_hostname: "sw2"    |  <-- из CDP
              | remote_port: "Gi3/13"     |  <-- из CDP
              | remote_ip: "10.195.124.8" |  <-- из CDP
              | remote_platform: "WS-C"  |  <-- из CDP
              | remote_mac: "001a.3008"   |  <-- из LLDP (!)
              | protocol: "BOTH"          |
              +---------------------------+
```

### 2.6 Шаг 4: Модель LLDPNeighbor

**Файл:** `core/models.py`

Нормализованный словарь превращается в типизированный объект:

```python
@dataclass
class LLDPNeighbor:
    hostname: str = ""           # Наш хост
    device_ip: str = ""          # IP нашего хоста
    local_interface: str = ""    # Наш интерфейс
    remote_hostname: str = ""    # Имя соседа
    remote_port: str = ""        # Порт соседа
    remote_mac: str = ""         # MAC соседа
    remote_ip: str = ""          # IP соседа
    neighbor_type: str = ""      # hostname / mac / ip / unknown
    protocol: str = ""           # LLDP / CDP / BOTH

    @classmethod
    def from_dict(cls, data: Dict) -> "LLDPNeighbor":
        """Создаёт объект из словаря."""
        return cls(
            hostname=data.get("hostname", ""),
            remote_hostname=data.get("remote_hostname", ""),
            remote_port=data.get("remote_port", ""),
            # ... остальные поля
        )
```

### 2.7 Шаг 5: Создание кабелей в NetBox

**Файл:** `netbox/sync/cables.py`

Это самый сложный шаг. Для каждого LLDP-соседа нужно:
1. Найти **локальное** устройство в NetBox
2. Найти **локальный** интерфейс
3. Найти **соседнее** устройство (4 стратегии поиска!)
4. Найти **соседний** интерфейс
5. Создать кабель между ними

```python
def sync_cables_from_lldp(self, lldp_data, skip_unknown=True, cleanup=False):
    for entry in neighbors:
        # 1. Ищем ЛОКАЛЬНОЕ устройство
        local_device_obj = self._find_device(entry.hostname)

        # 2. Ищем ЛОКАЛЬНЫЙ интерфейс
        local_intf_obj = self._find_interface(local_device_obj.id, entry.local_interface)

        # 3. Ищем СОСЕДНЕЕ устройство (4 стратегии!)
        remote_device_obj = self._find_neighbor_device(entry)

        # 4. Ищем СОСЕДНИЙ интерфейс
        remote_intf_obj = self._find_interface(remote_device_obj.id, entry.remote_port)

        # 5. Создаём КАБЕЛЬ
        result = self._create_cable(local_intf_obj, remote_intf_obj)
```

**Диаграмма решений для одного соседа:**

```
LLDP запись: switch1:Gi0/1 --> switch2:Gi0/2
    |
    +-- neighbor_type == "unknown" && skip_unknown?  --> SKIP
    |
    +-- Локальное устройство не найдено?             --> FAILED
    +-- Локальный интерфейс не найден?               --> FAILED
    |
    +-- Соседнее устройство не найдено?              --> SKIP
    +-- Соседний интерфейс не найден?                --> SKIP
    |
    +-- Тип интерфейса == "lag"?                     --> SKIP
    |
    +-- На интерфейсе уже есть кабель?               --> EXISTS
    |
    +-- Все проверки пройдены                        --> CREATE
```

### 2.8 Поиск соседа: 4 стратегии

Метод `_find_neighbor_device()` -- ключевой. Он решает, как найти устройство
соседа в NetBox. В зависимости от `neighbor_type` используется своя цепочка:

```
neighbor_type = "hostname" (сосед передал имя):
    hostname --> IP --> MAC
    Самый надёжный. Сначала ищем по имени, если не нашли -- по IP, потом по MAC.

neighbor_type = "mac" (сосед передал только MAC):
    MAC --> IP
    LLDP chassis_id в формате MAC. Ищем по MAC, потом по IP.

neighbor_type = "ip" (сосед передал management IP):
    IP --> MAC
    Ищем по IP, потом по MAC.

neighbor_type = "unknown" (нет данных):
    IP --> MAC
    Пробуем всё что есть. Обычно skip_unknown=True и мы пропускаем.
```

Реальный код (упрощённо):

```python
def _find_neighbor_device(self, entry: LLDPNeighbor):
    if entry.neighbor_type == "hostname":
        # Убираем домен: switch1.corp.local --> switch1
        clean = entry.remote_hostname.split(".")[0]
        device = self._find_device(clean)
        if device:
            return device

        # Fallback: по IP
        if entry.remote_ip:
            device = self.client.get_device_by_ip(entry.remote_ip)
            if device:
                return device

        # Fallback: по MAC
        if entry.remote_mac:
            device = self._find_device_by_mac(entry.remote_mac)
            if device:
                return device

    elif entry.neighbor_type == "mac":
        # MAC --> IP
        ...
```

### 2.9 Дедупликация: один кабель -- две записи

LLDP работает двусторонне. Если switch1 и switch2 соединены кабелем,
каждый из них "видит" соседа:

```
От switch1: local=Gi0/1 --> remote=switch2:Gi0/2
От switch2: local=Gi0/2 --> remote=switch1:Gi0/1
```

Это **один и тот же кабель**, но два LLDP-записи. Без дедупликации
мы бы создали его дважды (или посчитали `created: 2` в dry_run).

Решение -- set с сортированными ключами:

```python
# Оба варианта дают одинаковый ключ:
cable_key = tuple(sorted(["switch1:Gi0/1", "switch2:Gi0/2"]))
# --> ("switch1:Gi0/1", "switch2:Gi0/2")

cable_key = tuple(sorted(["switch2:Gi0/2", "switch1:Gi0/1"]))
# --> ("switch1:Gi0/1", "switch2:Gi0/2")   <-- тот же ключ!
```

### 2.10 Полная диаграмма трансформации данных

Вот как одна запись проходит через все слои:

```
[1] Сырой текст с устройства:
    "Local Intf: Gi1/0/49\nChassis id: 001a.3008.6c00\nPort id: Gi3/13\n..."

        |  TextFSM парсинг
        v

[2] Словарь от парсера (сырые данные):
    {"local_interface": "Gi1/0/49", "chassis_id": "001a.3008.6c00",
     "neighbor_port_id": "Gi3/13", "neighbor": "c6509-e.corp"}

        |  LLDPNormalizer._normalize_row()
        v

[3] Нормализованный словарь:
    {"local_interface": "Gi1/0/49", "remote_mac": "001a.3008.6c00",
     "remote_port": "Gi3/13", "remote_hostname": "c6509-e.corp",
     "neighbor_type": "hostname", "protocol": "LLDP"}

        |  LLDPNeighbor.from_dict()
        v

[4] Типизированный объект:
    LLDPNeighbor(local_interface="Gi1/0/49", remote_port="Gi3/13",
                 remote_hostname="c6509-e.corp", neighbor_type="hostname")

        |  sync_cables_from_lldp()
        v

[5] NetBox API запрос:
    POST /api/dcim/cables/
    {"a_terminations": [{"object_type": "dcim.interface", "object_id": 42}],
     "b_terminations": [{"object_type": "dcim.interface", "object_id": 87}],
     "status": "connected"}
```

---

## 3. Полный пример: Match MAC

Match MAC -- это процесс сопоставления MAC-адресов из таблицы коммутатора
с именами хостов из справочника. Особенность этого потока -- он использует
Excel как промежуточное хранилище, и пользователь может вручную
отредактировать файл перед сопоставлением.

### 3.1 Диаграмма потока

```
[Шаг 1] Сбор MAC-адресов
    python -m network_collector mac --format excel
        |
        v
    MACCollector.collect(devices)
        |
        v
    SSH: "show mac address-table"  -->  TextFSM  -->  MACNormalizer
        |
        v
    Данные: [{"hostname": "sw1", "mac": "AA:BB:CC:DD:EE:FF",
              "interface": "Gi0/1", "vlan": "10"}]
        |
        v
    apply_fields_config(data, "mac")
        |  Переименование полей:
        |  hostname --> "DEVICE", interface --> "PORT", mac --> "MAC ADDRESS"
        v
    ExcelExporter --> mac_addresses.xlsx


[Шаг 2] Пользователь редактирует Excel (необязательно)

    +--------+---------+-------------+------+
    | DEVICE |  PORT   | MAC ADDRESS | VLAN |
    +--------+---------+-------------+------+
    | sw1    | Gi0/1   | AA:BB:CC... | 10   |
    | sw1    | Gi0/2   | 11:22:33... | 20   |
    +--------+---------+-------------+------+


[Шаг 3] Сопоставление
    python -m network_collector match-mac \
        --mac-file mac_addresses.xlsx \
        --hosts-file hosts.xlsx \
        --output matched.xlsx
        |
        v
    pd.read_excel("mac_addresses.xlsx")
        |  Колонки: "DEVICE", "PORT", "MAC ADDRESS", "VLAN"
        v
    get_reverse_mapping("mac")
        |  Обратный маппинг: "device" --> "hostname",
        |                    "port" --> "interface",
        |                    "mac address" --> "mac"
        v
    mac_df.columns = [reverse_map.get(col.lower(), col.lower()) ...]
        |  Обратно: "DEVICE" --> "hostname", "PORT" --> "interface"
        v
    matcher.match_mac_data(mac_data, mac_field="mac", hostname_field="hostname")
        |
        v
    Для каждого MAC: ищем в справочнике hosts.xlsx
        |
        v
    matched.xlsx с колонкой "Host Name" для найденных
```

### 3.2 Зачем нужен reverse mapping

Это ключевая идея. Данные проходят через два преобразования имён:

```
[Модель]              [Excel]                   [Обратно в модель]
hostname   --name:--> "DEVICE"   --reverse:--> hostname
interface  --name:--> "PORT"     --reverse:--> interface
mac        --name:--> "MAC ADDRESS" --reverse:--> mac
```

**Файл:** `fields_config.py`

```python
def get_reverse_mapping(data_type: str) -> Dict[str, str]:
    """
    Обратный маппинг: display_name --> field_name.
    Пример для mac: {"device": "hostname", "port": "interface", "mac address": "mac"}
    """
```

Зачем это нужно? Потому что `match_mac_data()` ожидает **оригинальные имена полей**
из модели (`mac`, `hostname`, `interface`), а в Excel они переименованы
(`MAC ADDRESS`, `DEVICE`, `PORT`).

### 3.3 Таблица трансформации имён полей

| Этап | hostname | interface | mac |
|------|----------|-----------|-----|
| Модель MACEntry | `hostname` | `interface` | `mac` |
| fields.yaml (name) | `"Device"` | `"Port"` | `"MAC Address"` |
| Excel колонки | `DEVICE` | `PORT` | `MAC ADDRESS` |
| reverse_map (ключ) | `device` | `port` | `mac address` |
| После reverse mapping | `hostname` | `interface` | `mac` |

Один источник правды -- `fields.yaml`. Изменил display name там --
и экспорт, и импорт автоматически подстроятся.

---

## 4. Полный пример: Синхронизация интерфейсов

Это поток с batch-операциями: вместо того чтобы создавать интерфейсы
по одному, мы собираем все нужные и отправляем одним запросом.

### 4.1 Команда

```bash
# Посмотреть что изменится (ничего не трогает)
python -m network_collector sync-netbox --interfaces --dry-run

# Синхронизировать
python -m network_collector sync-netbox --interfaces --site "Office"
```

### 4.2 Диаграмма потока

```
[Шаг 1] Сбор интерфейсов с устройства

    InterfaceCollector.collect(devices)
        |
        v
    SSH: "show interfaces"  -->  TextFSM  -->  InterfaceNormalizer
        |
        v
    Данные: [Interface(name="Gi0/1", status="up", description="Uplink",
                        speed="1000", mode="access", access_vlan=10)]


[Шаг 2] Получение интерфейсов из NetBox

    client.get_interfaces(device_id=42)
        |
        v
    NetBox API: GET /api/dcim/interfaces/?device_id=42
        |
        v
    Существующие: [NetBoxInterface(name="Gi0/1", description="Old"),
                   NetBoxInterface(name="Gi0/3", description="Deleted port")]


[Шаг 3] Сравнение (SyncComparator)

    comparator.compare_interfaces(local=..., remote=...)
        |
        v
    SyncDiff:
        to_create: [Gi0/2]           <-- есть на устройстве, нет в NetBox
        to_update: [Gi0/1]           <-- описание изменилось
        to_delete: [Gi0/3]           <-- нет на устройстве (если cleanup=True)
        to_skip:   [Gi0/4]           <-- всё совпадает


[Шаг 4] Batch операции

    _batch_create_interfaces(to_create)
        |  POST /api/dcim/interfaces/ (массив данных)
        v

    _batch_update_interfaces(to_update)
        |  PATCH /api/dcim/interfaces/ (массив изменений)
        v

    _batch_delete_interfaces(to_delete)
        |  DELETE /api/dcim/interfaces/ (массив ID)
        v

    Статистика: {created: 1, updated: 1, deleted: 1, skipped: 1}
```

### 4.3 Шаг 3 подробно: SyncComparator

**Файл:** `core/domain/sync.py`

SyncComparator -- это чистая функция сравнения. Она не знает
ни о NetBox, ни о SSH. Принимает два списка данных и возвращает diff.

```python
class SyncComparator:
    def compare_interfaces(
        self,
        local: List[Dict],          # Интерфейсы с устройства
        remote: List[Any],           # Интерфейсы из NetBox
        compare_fields: List[str],   # Какие поля сравнивать
        create_missing: bool = True, # Создавать отсутствующие?
        cleanup: bool = False,       # Удалять лишние?
    ) -> SyncDiff:
        """
        Сравнивает локальные и удалённые интерфейсы.

        Возвращает SyncDiff с четырьмя списками:
        - to_create: есть на устройстве, нет в NetBox
        - to_update: есть в обоих, но поля отличаются
        - to_delete: нет на устройстве, есть в NetBox
        - to_skip: всё совпадает
        """
```

Результат -- объект SyncDiff:

```python
@dataclass
class SyncDiff:
    object_type: str                            # "interfaces"
    to_create: List[SyncItem] = []              # Создать
    to_update: List[SyncItem] = []              # Обновить
    to_delete: List[SyncItem] = []              # Удалить
    to_skip: List[SyncItem] = []                # Пропустить

    @property
    def has_changes(self) -> bool:
        return len(self.to_create) + len(self.to_update) + len(self.to_delete) > 0
```

Каждый элемент -- SyncItem, который хранит что именно изменилось:

```python
@dataclass
class SyncItem:
    name: str                                   # "GigabitEthernet0/1"
    change_type: ChangeType                     # CREATE / UPDATE / DELETE / SKIP
    changes: List[FieldChange] = []             # Что именно изменилось

# Пример для UPDATE:
SyncItem(
    name="GigabitEthernet0/1",
    change_type=ChangeType.UPDATE,
    changes=[
        FieldChange(field="description", old_value="Old", new_value="Uplink to SW2"),
        FieldChange(field="enabled", old_value=False, new_value=True),
    ]
)
```

### 4.4 Шаг 4 подробно: Batch операции

**Файл:** `netbox/sync/interfaces.py`

Вместо поштучных запросов используются batch-операции (один запрос на
все создания, один на все обновления, один на все удаления).

```python
def _batch_create_interfaces(self, device_id, to_create, sorted_interfaces, stats, details):
    # 1. Собираем данные для batch
    create_batch = []
    for item in to_create:
        intf = next(i for i in sorted_interfaces if i.name == item.name)
        data, mac = self._build_create_data(device_id, intf)
        create_batch.append(data)

    # 2. Один API запрос вместо N
    if not self.dry_run:
        created = self.client.bulk_create_interfaces(create_batch)
        # POST /api/dcim/interfaces/ с массивом данных
```

Сравнение подходов:

```
Поштучно (медленно):              Batch (быстро):
POST /api/dcim/interfaces/ (Gi0/1)     POST /api/dcim/interfaces/
POST /api/dcim/interfaces/ (Gi0/2)         [Gi0/1, Gi0/2, Gi0/3]
POST /api/dcim/interfaces/ (Gi0/3)
= 3 HTTP запроса                       = 1 HTTP запрос
```

Если batch-запрос падает, используется fallback на поштучные операции,
чтобы хотя бы часть интерфейсов создалась.

### 4.5 Отличие от кабелей

Интерфейсы и кабели синхронизируются по-разному:

| Аспект | Интерфейсы | Кабели |
|--------|-----------|--------|
| Сравнение | SyncComparator --> SyncDiff | Проверка `interface.cable` |
| API вызовы | Batch (один запрос на все) | Поштучно |
| Определение "нужно обновить?" | Сравнение полей (description, enabled...) | Кабель есть или нет |
| Cleanup | Batch delete по списку ID | Поштучное удаление с защитой |

Кабели не используют batch, потому что каждый кабель требует проверки
**обоих** интерфейсов на его концах.

---

## 5. Диаграмма трансформации данных

Обобщённая схема, показывающая как данные трансформируются на каждом этапе
для любого типа коллектора:

### 5.1 От текста до модели

```
[Этап 1: ТЕКСТ]
"Vlan  Mac Address       Type     Ports\n 10  aabb.ccdd.eeff  DYNAMIC  Gi0/1"
    |
    | TextFSM: шаблон cisco_ios_show_mac_address-table.textfsm
    v
[Этап 2: СЫРОЙ СЛОВАРЬ]
{"destination_address": "aabb.ccdd.eeff", "destination_port": "Gi0/1",
 "vlan": "10", "type": "DYNAMIC"}
    |
    | Normalizer: маппинг ключей, нормализация MAC, фильтрация VLAN
    v
[Этап 3: НОРМАЛИЗОВАННЫЙ СЛОВАРЬ]
{"mac": "AA:BB:CC:DD:EE:FF", "interface": "Gi0/1",
 "vlan": "10", "type": "dynamic", "hostname": "sw1", "status": "online"}
    |
    | Model.from_dict(): создание dataclass
    v
[Этап 4: ТИПИЗИРОВАННЫЙ ОБЪЕКТ]
MACEntry(mac="AA:BB:CC:DD:EE:FF", interface="Gi0/1", vlan="10",
         mac_type="dynamic", hostname="sw1")
    |
    |  Два пути:
    +-----------------------------+
    |                             |
    v                             v
[Этап 5a: ЭКСПОРТ]           [Этап 5b: SYNC]
apply_fields_config()         SyncComparator.compare()
    |                             |
    v                             v
{"DEVICE": "sw1",             SyncDiff(
 "MAC": "AA:BB:CC:DD:EE:FF",     to_create=[...],
 "PORT": "Gi0/1"}                 to_update=[...])
    |                             |
    v                             v
Excel/CSV/JSON файл           NetBox API запросы
```

### 5.2 Нормализация по вендорам

Каждый вендор возвращает данные в своём формате. Normalizer делает их одинаковыми:

```
Cisco IOS (TextFSM):
    {"destination_address": "aabb.ccdd.eeff", "destination_port": "Gi0/1"}
                                    |
Cisco NX-OS (TextFSM):             |
    {"mac_address": "aabb.ccdd.eeff", "port": "Eth1/1"}
                                    |   MACNormalizer
Arista EOS (TextFSM):              |   normalize_dicts()
    {"mac": "aa:bb:cc:dd:ee:ff", "interface": "Et1"}
                                    |
                                    v
                        Единый формат для всех:
    {"mac": "AA:BB:CC:DD:EE:FF", "interface": "Gi0/1", "vlan": "10",
     "type": "dynamic", "hostname": "sw1", "status": "online"}
```

Ключевые функции нормализации:

```python
# core/constants.py

normalize_interface_short("GigabitEthernet0/1")  # --> "Gi0/1"
normalize_interface_short("TenGigabitEthernet1/0/1")  # --> "Te1/0/1"
normalize_interface_short("Port-channel10")  # --> "Po10"

normalize_mac("aabb.ccdd.eeff", format="ieee")  # --> "AA:BB:CC:DD:EE:FF"
normalize_mac("AA:BB:CC:DD:EE:FF", format="cisco")  # --> "aabb.ccdd.eeff"
```

---

## 6. Таблица ключевых файлов

| Файл | Роль в потоке данных |
|------|---------------------|
| `cli/commands/collect.py` | Точка входа CLI: `cmd_lldp()`, `cmd_mac()`, `cmd_devices()` |
| `cli/commands/sync.py` | Точка входа синхронизации: `cmd_sync_netbox()` |
| `cli/commands/match.py` | Точка входа match-mac: `cmd_match_mac()` |
| `collectors/lldp.py` | Сбор LLDP/CDP данных с устройств |
| `collectors/mac.py` | Сбор MAC-адресов с устройств |
| `collectors/interfaces.py` | Сбор интерфейсов с устройств |
| `collectors/base.py` | Базовый класс коллектора (SSH, TextFSM) |
| `parsers/textfsm_parser.py` | Обёртка над NTC Templates |
| `core/domain/lldp.py` | Нормализатор LLDP/CDP данных |
| `core/domain/mac.py` | Нормализатор MAC-данных |
| `core/domain/interface.py` | Нормализатор интерфейсов |
| `core/domain/sync.py` | SyncComparator: сравнение данных (чистая логика) |
| `core/models.py` | Dataclass модели: Interface, MACEntry, LLDPNeighbor |
| `core/constants.py` | Утилиты: нормализация интерфейсов, MAC, маппинги |
| `fields_config.py` | Фильтрация полей, reverse mapping |
| `fields.yaml` | Конфигурация полей для экспорта/синхронизации |
| `exporters/excel.py` | Экспорт в Excel |
| `netbox/sync/interfaces.py` | Синхронизация интерфейсов (batch) |
| `netbox/sync/cables.py` | Синхронизация кабелей (поштучно) |
| `netbox/sync/base.py` | Базовый класс SyncBase: кэши, общие методы |
| `netbox/client/` | HTTP-клиент NetBox: get/create/update/delete |
| `configurator/description.py` | DescriptionMatcher для match-mac |

---

## Итоги

Теперь ты понимаешь полный путь данных в проекте. Вот что важно запомнить:

1. **Всегда одни и те же слои:** Текст --> Парсер --> Normalizer --> Модель --> Результат.
   Не важно, собираешь ли ты MAC, LLDP или интерфейсы -- архитектура одинаковая.

2. **Normalizer -- ключевой слой.** Он превращает данные от разных вендоров
   в единый формат. Без него пришлось бы писать отдельную логику для каждой платформы.

3. **SyncComparator -- чистая функция.** Она не знает про NetBox и SSH.
   Принимает два списка, возвращает diff. Это облегчает тестирование.

4. **Batch vs поштучно.** Интерфейсы, IP, inventory используют batch API
   (один запрос на все объекты). Кабели -- поштучно (каждый требует проверки обоих концов).

5. **fields.yaml -- единый источник правды** для имён полей.
   Экспорт и импорт (reverse mapping) используют один и тот же файл.

6. **Дедупликация в кабелях** -- LLDP видит кабель с обеих сторон,
   поэтому нужен `seen_cables` set с сортированными ключами.

**Совет:** если хочешь понять конкретный поток глубже, загляни
в связанные документы:
- [DATA_FLOW_LLDP.md](../DATA_FLOW_LLDP.md) -- каждый метод LLDP-цепочки с кодом
- [DATA_FLOW_MATCH_MAC.md](../DATA_FLOW_MATCH_MAC.md) -- reverse mapping пошагово
- [DATA_FLOW_DETAILED.md](../DATA_FLOW_DETAILED.md) -- каждый шаг MAC-сбора
