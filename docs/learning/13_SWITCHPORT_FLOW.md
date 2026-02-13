# 13. Switchport Mode: полный путь данных от SSH до NetBox

Этот документ объясняет **полную цепочку** определения режима порта (access / tagged / tagged-all) — от отправки SSH-команды на коммутатор до записи в NetBox. На каждом шаге — реальный код, реальные данные, простые объяснения.

Если ты уже прочитал [10_COLLECTORS_DEEP_DIVE.md](10_COLLECTORS_DEEP_DIVE.md) и [11_SYNC_DEEP_DIVE.md](11_SYNC_DEEP_DIVE.md) — здесь ты увидишь, как конкретно работает switchport.

---

## Содержание

1. [Зачем это нужно](#1-зачем-это-нужно)
2. [Общая схема](#2-общая-схема)
3. [Шаг 1: Какую команду отправить](#3-шаг-1-какую-команду-отправить)
4. [Шаг 2: Отправка SSH-команды](#4-шаг-2-отправка-ssh-команды)
5. [Шаг 3: Парсинг через NTCParser](#5-шаг-3-парсинг-через-ntcparser)
6. [Шаг 4: Нормализация — три ветки для трёх платформ](#6-шаг-4-нормализация--три-ветки-для-трёх-платформ)
7. [Шаг 5: Алиасы имён интерфейсов](#7-шаг-5-алиасы-имён-интерфейсов)
8. [Шаг 6: Обогащение интерфейсов (Domain Layer)](#8-шаг-6-обогащение-интерфейсов-domain-layer)
9. [Шаг 7: Синхронизация с NetBox](#9-шаг-7-синхронизация-с-netbox)
10. [Три платформы — три формата (таблица сравнения)](#10-три-платформы--три-формата)
11. [Как возник баг с NX-OS](#11-как-возник-баг-с-nx-os)
12. [Диаграмма полного потока](#12-диаграмма-полного-потока)

---

## 1. Зачем это нужно

В NetBox у каждого интерфейса есть поле **mode** — режим работы порта:

| NetBox mode | Что значит | Пример |
|-------------|-----------|--------|
| `access` | Порт в одном VLAN | Порт к рабочей станции в VLAN 47 |
| `tagged` | Trunk с конкретным списком VLAN | Линк между коммутаторами, VLAN 10,30,38 |
| `tagged-all` | Trunk со всеми VLAN | Аплинк, пропускает все 4094 VLAN |

Когда мы собираем данные с реального коммутатора, нужно:
1. Узнать режим каждого порта
2. Узнать какие VLAN назначены
3. Записать это в NetBox

Звучит просто, но каждая платформа (Cisco IOS, NX-OS, QTech) возвращает данные **в разном формате**. Наша задача — привести их к единому виду.

---

## 2. Общая схема

```
┌─────────────────┐
│ SSH-команда      │  "show interface switchport"
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Сырой текст      │  Разный для каждой платформы
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ TextFSM парсинг  │  NTCParser.parse() — кастомный шаблон или NTC Templates
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Нормализация     │  InterfaceNormalizer.normalize_switchport_data() — три ветки
│ + Алиасы         │  + get_interface_aliases() — Gi0/1 ↔ GigabitEthernet0/1
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Обогащение       │  enrich_with_switchport() — присваиваем mode каждому интерфейсу
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Sync NetBox      │  _build_create_data() / _build_update_data() — записываем в NetBox
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ NetBox API       │  mode=tagged, untagged_vlan=ID, tagged_vlans=[ID1, ID2]
└─────────────────┘
```

---

## 3. Шаг 1: Какую команду отправить

### Файл: `core/constants/commands.py` (строки 103-111)

Для каждой платформы определена своя SSH-команда:

```python
SECONDARY_COMMANDS = {
    "switchport": {
        "cisco_ios":  "show interfaces switchport",   # ← Cisco IOS (с 's')
        "cisco_iosxe":"show interfaces switchport",
        "cisco_nxos": "show interface switchport",    # ← NX-OS (без 's')
        "arista_eos": "show interfaces switchport",
        "qtech":      "show interface switchport",    # ← QTech (без 's')
        "qtech_qsw":  "show interface switchport",
    },
}
```

**Зачем разные команды?** Cisco IOS и Arista используют `show interfaces` (множественное число), а NX-OS и QTech — `show interface` (единственное). Если отправить неправильную команду — коммутатор выдаст ошибку.

---

## 4. Шаг 2: Отправка SSH-команды

### Файл: `collectors/interfaces.py` (строки 254-274)

Внутри метода `_collect_from_device()` коллектор подключается по SSH и отправляет команду:

```python
switchport_modes = {}

if self.collect_switchport:
    # Берём команду для нашей платформы
    sw_cmd = self.switchport_commands.get(device.platform)
    # Например: для cisco_nxos → "show interface switchport"

    if sw_cmd:
        # Отправляем по SSH
        sw_response = conn.send_command(sw_cmd)

        # Парсим ответ
        switchport_modes = self._parse_switchport_modes(
            sw_response.result,   # Сырой текст с коммутатора
            device.platform,      # "cisco_nxos", "qtech", "cisco_ios"
            sw_cmd,               # "show interface switchport"
        )
```

**Что тут происходит:**
1. Берём команду из словаря `SECONDARY_COMMANDS["switchport"]`
2. Отправляем по SSH через уже открытое соединение
3. Получаем сырой текст (тот же самый, что видишь в терминале коммутатора)
4. Передаём текст + платформу в парсер

**Результат:** `switchport_modes` — словарь вида:
```python
{
    "Ethernet1/2": {"mode": "tagged", "native_vlan": "1", "access_vlan": "1", "tagged_vlans": "10,30,38"},
    "Ethernet1/1": {"mode": "tagged-all", "native_vlan": "1", "access_vlan": "1", "tagged_vlans": ""},
}
```

---

## 5. Шаг 3: Парсинг через NTCParser

### Файл: `collectors/interfaces.py` (строки 508-550)

Метод `_parse_switchport_modes()` — координатор. Он решает **как** парсить:

```python
def _parse_switchport_modes(self, output, platform, command):
    modes = {}

    # NTCParser.parse() сам ищет кастомный шаблон, потом NTC fallback
    if self._parser:
        try:
            parsed = self._parser.parse(
                output=output,
                platform=platform,     # Передаём оригинальную платформу!
                command=command,
                normalize=False,       # Не менять имена полей
            )
            if parsed:
                # Domain layer нормализует switchport данные
                modes = self._normalizer.normalize_switchport_data(parsed, platform)
                if modes:
                    return modes
        except Exception as e:
            logger.debug(f"Парсинг switchport не сработал: {e}")

    # Если парсер не справился — fallback на regex
    modes = self._parse_switchport_modes_regex(output)
    return modes
```

**Важный момент:** Передаём `platform` (например `"qtech"`) **как есть**, не конвертируя. Почему — объясню ниже.

### Файл: `parsers/textfsm_parser.py` (строки 132-210)

`NTCParser.parse()` — универсальный парсер с двумя приоритетами:

```python
def parse(self, output, platform, command, normalize=True):
    # 1. Сначала ищем КАСТОМНЫЙ шаблон
    template_key = (platform.lower(), command.lower())
    #  Пример: ("qtech", "show interface switchport")

    if template_key in CUSTOM_TEXTFSM_TEMPLATES:
        # Нашли! Используем наш шаблон из папки templates/
        template_file = CUSTOM_TEXTFSM_TEMPLATES[template_key]
        # → "qtech_show_interface_switchport.textfsm"
        parsed_data = self._parse_with_textfsm(output, template_path)
        return parsed_data

    # 2. Не нашли кастомный → пробуем NTC Templates (стандартная библиотека)
    ntc_platform = NTC_PLATFORM_MAP.get(platform, platform)
    #  "qtech" → "cisco_ios"  (NTC не знает про QTech)
    #  "cisco_nxos" → "cisco_nxos"  (NTC знает про NX-OS)
    parsed_data = parse_output(platform=ntc_platform, command=command, data=output)
    return parsed_data
```

**Что здесь важно понять:**

`NTC Templates` — это стандартная Python-библиотека с шаблонами для Cisco, Arista, Juniper. Но она **не знает** про QTech. Поэтому:

- Для **QTech** → используется наш кастомный шаблон из папки `templates/`
- Для **Cisco IOS/NX-OS** → используется стандартный NTC Templates
- Если бы мы передали `"cisco_ios"` вместо `"qtech"`, парсер не нашёл бы кастомный шаблон!

### Файл: `core/constants/commands.py` (строки 175-197)

Вот маппинг кастомных шаблонов:

```python
CUSTOM_TEXTFSM_TEMPLATES = {
    # QTech шаблоны
    ("qtech", "show interface switchport"):     "qtech_show_interface_switchport.textfsm",
    ("qtech_qsw", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
    ("qtech", "show interface"):                "qtech_show_interface.textfsm",
    ("qtech", "show version"):                  "qtech_show_version.textfsm",
    # ... и другие
}
```

Ключ — кортеж `(платформа, команда)`. Значение — имя файла шаблона в папке `templates/`.

### Маппинг платформ для NTC

### Файл: `core/connection.py` (строки 69-78)

```python
NTC_PLATFORM_MAP = {
    "cisco_ios":   "cisco_ios",
    "cisco_iosxe": "cisco_ios",
    "cisco_nxos":  "cisco_nxos",
    "arista_eos":  "arista_eos",
    "qtech":       "cisco_ios",     # ← QTech парсится как Cisco IOS в NTC
    "qtech_qsw":  "cisco_ios",
}
```

---

## 6. Шаг 4: Нормализация — три ветки для трёх платформ

### Файл: `core/domain/interface.py` (класс `InterfaceNormalizer`)

Это **самая важная** функция в цепочке. Она превращает разные форматы в единый. Метод перенесён из коллектора в Domain Layer — вся нормализация теперь в одном месте.

### Проблема: каждая платформа возвращает разные поля

Вот что возвращает TextFSM/NTC для каждой платформы:

**Cisco IOS** (через NTC Templates):
```python
{
    "interface": "Gi1/0/1",
    "admin_mode": "trunk",         # ← Есть! Определяющее поле
    "mode": "trunk",               # ← Operational mode (может быть "down")
    "trunking_vlans": ["10", "20", "30"],  # ← Список!
    "access_vlan": "1",
    "native_vlan": "1",
}
```

**NX-OS** (через NTC Templates):
```python
{
    "interface": "Ethernet1/2",
    "mode": "trunk",               # ← Есть, но admin_mode — НЕТ!
    "switchport": "Enabled",       # ← Есть
    "trunking_vlans": "10,30,38",  # ← Строка (не список)
    "access_vlan": "1",
    "native_vlan": "1",
}
```

**QTech** (через кастомный шаблон):
```python
{
    "interface": "TFGigabitEthernet 0/3",
    "switchport": "enabled",       # ← Есть
    "mode": "ACCESS",              # ← Есть, но заглавными
    "vlan_lists": "ALL",           # ← Своё поле (не trunking_vlans)
    "access_vlan": "1",
    "native_vlan": "1",
}
```

**Видишь разницу?** Три платформы — три набора полей. Метод `normalize_switchport_data()` определяет какая платформа перед ним и обрабатывает правильно:

```python
# core/domain/interface.py — метод InterfaceNormalizer.normalize_switchport_data()
def normalize_switchport_data(self, parsed, platform):
    modes = {}

    for row in parsed:
        iface = row.get("interface", "")
        if not iface:
            continue

        switchport = row.get("switchport", "").lower()
        if switchport == "disabled":
            continue  # Порт не switchport — пропускаем

        admin_mode = row.get("admin_mode", "").lower()
        native_vlan = row.get("native_vlan", row.get("trunking_native_vlan", ""))
        access_vlan = row.get("access_vlan", "")

        netbox_mode = ""
        trunking_vlans = ""

        # ═══════════════════════════════════════════════════
        # ВЕТКА 1: Cisco IOS / Arista
        # Определяем по наличию admin_mode
        # ═══════════════════════════════════════════════════
        if admin_mode:
            if "access" in admin_mode:
                netbox_mode = "access"
            elif "trunk" in admin_mode or "dynamic" in admin_mode:
                raw_vlans = row.get("trunking_vlans", "")
                # NTC может вернуть список: ["10", "20", "30"]
                if isinstance(raw_vlans, list):
                    trunking_vlans = ",".join(str(v) for v in raw_vlans).lower().strip()
                else:
                    trunking_vlans = str(raw_vlans).lower().strip()

                # "all" или "1-4094" → tagged-all (все VLAN)
                if (not trunking_vlans or
                    trunking_vlans == "all" or
                    trunking_vlans in ("1-4094", "1-4093", "1-4095")):
                    netbox_mode = "tagged-all"
                    trunking_vlans = ""
                else:
                    # Конкретные VLAN → tagged
                    netbox_mode = "tagged"

        # ═══════════════════════════════════════════════════
        # ВЕТКА 2: NX-OS
        # Нет admin_mode, но есть mode + trunking_vlans
        # ═══════════════════════════════════════════════════
        elif row.get("trunking_vlans") is not None and row.get("mode"):
            nxos_mode = row.get("mode", "").lower()
            if "trunk" in nxos_mode:
                raw_vlans = row.get("trunking_vlans", "")
                trunking_vlans = str(raw_vlans).lower().strip()

                if (not trunking_vlans or
                    trunking_vlans == "all" or
                    trunking_vlans in ("1-4094", "1-4093", "1-4095")):
                    netbox_mode = "tagged-all"
                    trunking_vlans = ""
                else:
                    netbox_mode = "tagged"
            elif "access" in nxos_mode:
                netbox_mode = "access"

        # ═══════════════════════════════════════════════════
        # ВЕТКА 3: QTech
        # switchport=enabled, mode=ACCESS/TRUNK/HYBRID, vlan_lists
        # ═══════════════════════════════════════════════════
        elif switchport == "enabled":
            qtech_mode = row.get("mode", "").upper()
            vlan_lists = row.get("vlan_lists", "")

            if qtech_mode == "ACCESS":
                netbox_mode = "access"
            elif qtech_mode == "TRUNK":
                vl = str(vlan_lists).strip().upper()
                if not vl or vl == "ALL":
                    netbox_mode = "tagged-all"
                else:
                    netbox_mode = "tagged"
                    trunking_vlans = str(vlan_lists).strip()
            elif qtech_mode == "HYBRID":
                netbox_mode = "tagged"
                vl = str(vlan_lists).strip().upper()
                if vl and vl != "ALL":
                    trunking_vlans = str(vlan_lists).strip()

        # Сохраняем результат в едином формате
        mode_data = {
            "mode": netbox_mode,
            "native_vlan": str(native_vlan) if native_vlan else "",
            "access_vlan": str(access_vlan) if access_vlan else "",
            "tagged_vlans": trunking_vlans if netbox_mode == "tagged" else "",
        }
        modes[iface] = mode_data

        # Алиасы: добавляем все варианты написания через единый источник
        for alias in get_interface_aliases(iface):
            if alias != iface:
                modes[alias] = mode_data  # Тот же объект — экономия памяти

    return modes
```

### Как код определяет платформу?

Не по имени платформы (`platform`), а **по наличию полей** в данных:

| Проверка | Платформа | Почему |
|----------|-----------|--------|
| `admin_mode` не пустой | Cisco IOS/Arista | Только IOS NTC возвращает `admin_mode` |
| `trunking_vlans` есть + `mode` есть | NX-OS | NX-OS имеет `mode` и `trunking_vlans`, но не `admin_mode` |
| `switchport == "enabled"` | QTech | Кастомный шаблон возвращает `switchport` + `vlan_lists` |

### Пример прохождения данных

**Вход** (NX-OS, Ethernet1/2):
```python
row = {
    "interface": "Ethernet1/2",
    "switchport": "Enabled",
    "mode": "trunk",
    "access_vlan": "1",
    "native_vlan": "1",
    "trunking_vlans": "10,30,38",   # ← Конкретные VLAN
}
```

**Проход по веткам:**
1. `admin_mode = ""` → пустой → **ветка 1 пропущена**
2. `row.get("trunking_vlans")` = `"10,30,38"` (не None) + `row.get("mode")` = `"trunk"` → **ветка 2 сработала!**
3. `nxos_mode = "trunk"` → `"trunk" in nxos_mode` = True
4. `trunking_vlans = "10,30,38"` → не пустой, не "all", не "1-4094"
5. → `netbox_mode = "tagged"` ✅

**Выход:**
```python
modes["Ethernet1/2"] = {
    "mode": "tagged",
    "native_vlan": "1",
    "access_vlan": "1",
    "tagged_vlans": "10,30,38",
}
```

---

## 7. Шаг 5: Алиасы имён интерфейсов

### Файл: `core/constants/interfaces.py` — функция `get_interface_aliases()`

Коммутатор может назвать интерфейс по-разному: `Gi0/1` или `GigabitEthernet0/1`. Чтобы потом найти соответствие — создаём алиасы.

Раньше алиасы генерировались вручную в коллекторе (метод `_add_switchport_aliases()`). Теперь используется **единый источник** — функция `get_interface_aliases()` из `core/constants/interfaces.py`. Она вызывается прямо внутри `normalize_switchport_data()` (Domain Layer), а не отдельным шагом в коллекторе:

```python
# core/constants/interfaces.py
def get_interface_aliases(interface: str) -> List[str]:
    """Возвращает все возможные варианты написания интерфейса."""
    aliases = {interface}
    clean = interface.replace(" ", "")
    aliases.add(clean)

    # Короткая форма: GigabitEthernet0/1 → Gi0/1
    short = normalize_interface_short(clean)
    if short != clean:
        aliases.add(short)

    # Полная форма: Gi0/1 → GigabitEthernet0/1
    full = normalize_interface_full(clean)
    if full != clean:
        aliases.add(full)

    # Дополнительные формы: Gig0/1, Ten1/1, Et1/1 и т.д.
    # ...
    return list(aliases)
```

Эта же функция используется и в `_parse_media_types()` (коллектор), и в `enrich_with_switchport()` (Domain Layer) — **один источник правды** для всех вариантов имён интерфейсов.

**Пример результата:**
```python
# get_interface_aliases("Gi0/1") возвращает:
# ["Gi0/1", "GigabitEthernet0/1", "Gig0/1"]

# В normalize_switchport_data() алиасы добавляются сразу:
modes = {
    "Gi0/1":                {"mode": "access", ...},
    "GigabitEthernet0/1":   {"mode": "access", ...},  # Один и тот же объект!
    "Gig0/1":               {"mode": "access", ...},  # Тоже тот же объект
}
```

Все записи указывают на **один и тот же словарь** в памяти (не копия). Это экономит память.

---

## 8. Шаг 6: Обогащение интерфейсов (Domain Layer)

### Файл: `core/domain/interface.py` (строки 286-347)

До этого шага у нас есть два отдельных набора данных:
- **interfaces** — список интерфейсов из `show interfaces` (имя, статус, скорость, ...)
- **switchport_modes** — словарь mode/vlan из `show interface switchport`

Метод `enrich_with_switchport()` **объединяет** их:

```python
def enrich_with_switchport(self, interfaces, switchport_modes, lag_membership=None):

    # 1. Для LAG (Port-channel) — определяем mode по member портам
    lag_modes = {}
    if lag_membership:
        for member_iface, lag_name in lag_membership.items():
            if member_iface in switchport_modes:
                member_mode = switchport_modes[member_iface].get("mode", "")
                if member_mode == "tagged-all":
                    lag_modes[lag_name] = "tagged-all"   # Приоритет
                elif member_mode == "tagged":
                    lag_modes[lag_name] = "tagged"

    # 2. Для каждого интерфейса ищем его switchport данные
    for iface in interfaces:
        iface_name = iface.get("interface", "")

        # Ищем по точному имени
        sw_data = switchport_modes.get(iface_name)

        if not sw_data:
            # Пробуем все варианты написания имени из constants
            for variant in get_interface_aliases(iface_name):
                if variant in switchport_modes:
                    sw_data = switchport_modes[variant]
                    break

        if sw_data:
            # Присваиваем данные
            iface["mode"] = sw_data.get("mode", "")
            iface["native_vlan"] = sw_data.get("native_vlan", "")
            iface["access_vlan"] = sw_data.get("access_vlan", "")
            iface["tagged_vlans"] = sw_data.get("tagged_vlans", "")

        elif iface_name.lower().startswith(("po", "port-channel")):
            # LAG — берём mode от member портов
            for lag_name, lag_mode in lag_modes.items():
                if self._is_same_lag(iface_name, lag_name):
                    iface["mode"] = lag_mode
                    break

    return interfaces
```

**Пример:**

До обогащения:
```python
interface = {"interface": "GigabitEthernet0/1", "status": "up", "speed": "1000"}
switchport_modes = {"Gi0/1": {"mode": "access", "access_vlan": "47", ...}}
```

После обогащения:
```python
interface = {
    "interface": "GigabitEthernet0/1",
    "status": "up",
    "speed": "1000",
    "mode": "access",           # ← Добавлено
    "access_vlan": "47",        # ← Добавлено
    "native_vlan": "1",         # ← Добавлено
    "tagged_vlans": "",         # ← Добавлено
}
```

---

## 9. Шаг 7: Синхронизация с NetBox

Теперь данные собраны и обогащены. Осталось записать в NetBox.

### Конфигурация: `fields.yaml`

Прежде чем sync запишет VLAN — нужно включить опцию:

```yaml
sync:
  interfaces:
    options:
      sync_vlans: true    # ← Главный переключатель VLAN sync
      enabled_mode: "link"
    fields:
      mode:
        enabled: true
      untagged_vlan:
        enabled: true
      tagged_vlans:
        enabled: true
```

Если `sync_vlans: false` — mode синхронизируется, но VLAN — нет.

### Создание нового интерфейса

### Файл: `netbox/sync/interfaces.py` (строки 398-481)

```python
def _build_create_data(self, device_id, intf, site_name=None):
    data = {
        "device": device_id,
        "name": intf.name,
        "type": intf.port_type or "1000base-t",
    }

    # Mode
    if sync_cfg.is_field_enabled("mode") and intf.mode:
        data["mode"] = intf.mode   # "access", "tagged", "tagged-all"

    # VLAN (только если sync_vlans включён)
    if sync_cfg.get_option("sync_vlans", False):

        # Untagged VLAN: access_vlan для access, native_vlan для trunk
        target_vid = None
        if intf.mode == "access" and intf.access_vlan:
            target_vid = int(intf.access_vlan)       # access → access_vlan
        elif intf.mode in ("tagged", "tagged-all") and intf.native_vlan:
            target_vid = int(intf.native_vlan)       # trunk → native_vlan

        if target_vid:
            vlan = self._get_vlan_by_vid(target_vid, site_name)
            if vlan:
                data["untagged_vlan"] = vlan.id      # NetBox ID, не VID!

        # Tagged VLANs: только для tagged (не tagged-all)
        if intf.mode == "tagged" and intf.tagged_vlans:
            target_vids = parse_vlan_range(intf.tagged_vlans)
            # "10,30,38" → [10, 30, 38]

            tagged_ids = []
            for vid in target_vids:
                vlan = self._get_vlan_by_vid(vid, site_name)
                if vlan:
                    tagged_ids.append(vlan.id)
            if tagged_ids:
                data["tagged_vlans"] = sorted(tagged_ids)

    return (data, mac_to_assign)
```

### Обновление существующего интерфейса

### Файл: `netbox/sync/interfaces.py` (строки 574-704)

При обновлении — **сравниваем** текущее значение в NetBox с тем, что собрали:

```python
# _check_mode() — строки 574-587
def _check_mode(self, nb_interface, intf, sync_cfg, updates, actual_changes):
    current_mode = getattr(nb_interface.mode, 'value', None)
    #  Текущее значение в NetBox: "tagged" или None

    if intf.mode and intf.mode != current_mode:
        updates["mode"] = intf.mode
        actual_changes.append(f"mode: {current_mode} → {intf.mode}")
    elif not intf.mode and current_mode:
        updates["mode"] = ""    # Очистить mode (порт без switchport)
```

```python
# _check_tagged_vlans() — строки 642-704
def _check_tagged_vlans(self, nb_interface, intf, sync_cfg, updates, actual_changes, site_name):
    if intf.mode == "tagged" and intf.tagged_vlans:
        target_vids = parse_vlan_range(intf.tagged_vlans)  # [10, 30, 38]

        # Ищем каждый VLAN в NetBox
        target_vlan_ids = []
        for vid in target_vids:
            vlan = self._get_vlan_by_vid(vid, site_name)
            if vlan:
                target_vlan_ids.append(vlan.id)

        # Сравниваем множества
        current = VlanSet.from_vlan_objects(nb_interface.tagged_vlans)
        target = VlanSet.from_ids(matched_vids)

        if current != target:
            updates["tagged_vlans"] = sorted(target_vlan_ids)
            added = target.added(current)
            removed = target.removed(current)
            actual_changes.append(f"tagged_vlans: +{sorted(added)}, -{sorted(removed)}")
```

### Кэш VLAN

### Файл: `netbox/sync/base.py` (строки 221-261)

Чтобы не делать отдельный API-запрос для каждого VLAN, загружаем **все VLAN сайта** одним запросом:

```python
def _get_vlan_by_vid(self, vid, site=None):
    # 1. Смотрим в кэше
    cache_key = (vid, site or "")
    if cache_key in self._vlan_cache:
        return self._vlan_cache[cache_key]

    # 2. Если сайт ещё не загружен — загружаем ВСЕ VLAN этого сайта
    site_cache_key = f"_site_loaded_{site or ''}"
    if site_cache_key not in self._vlan_cache:
        self._load_site_vlans(site)      # 1 API-запрос на ВСЕ VLAN
        self._vlan_cache[site_cache_key] = True

    # 3. Теперь ищем в кэше
    return self._vlan_cache.get(cache_key)

def _load_site_vlans(self, site=None):
    vlans = list(self.client.get_vlans(site=site))
    for vlan in vlans:
        cache_key = (vlan.vid, site or "")
        self._vlan_cache[cache_key] = vlan
        # Обратный кэш: NetBox ID → VID (чтобы не дёргать API при сравнении)
        self._vlan_id_to_vid[vlan.id] = vlan.vid
```

**Без кэша:** 22 устройства × 48 портов × 3 VLAN = ~3168 API-запросов
**С кэшем:** 22 устройства × 1 запрос = 22 API-запроса

### Парсинг диапазонов VLAN

### Файл: `core/domain/vlan.py` (строки 18-69)

```python
def parse_vlan_range(vlan_str):
    """
    "10,30,38"     → [10, 30, 38]
    "100-105"      → [100, 101, 102, 103, 104, 105]
    "10,20,30-35"  → [10, 20, 30, 31, 32, 33, 34, 35]
    "all"          → []     (означает tagged-all, не парсим)
    "1-4094"       → []     (полный диапазон = all)
    """
    if not vlan_str:
        return []

    vlan_str = vlan_str.strip().lower()
    if vlan_str in ("all", "1-4094", "1-4093", "1-4095"):
        return []   # tagged-all — не нужен список

    result = []
    for part in vlan_str.split(","):      # "10,20,30-35" → ["10", "20", "30-35"]
        part = part.strip()
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            result.extend(range(start, end + 1))   # 30-35 → [30,31,32,33,34,35]
        else:
            result.append(int(part))                # "10" → [10]

    return sorted(set(result))  # Убираем дубликаты, сортируем
```

---

## 10. Три платформы — три формата

Сводная таблица: что возвращает парсер для каждой платформы.

### Сырой вывод с коммутатора

**Cisco IOS:**
```
Name: Gi1/0/1
Switchport: Enabled
Administrative Mode: static access     ← Определяющее поле
Operational Mode: static access
Access Mode VLAN: 47 (VLAN0047)
Trunking Native Mode VLAN: 1 (default)
Trunking VLANs Enabled: ALL
```

**Cisco NX-OS:**
```
Name: Ethernet1/2
  Switchport: Enabled
  Operational Mode: trunk               ← Нет Administrative Mode!
  Access Mode VLAN: 1 (default)
  Trunking Native Mode VLAN: 1 (default)
  Trunking VLANs Allowed: 10,30,38
```

**QTech:**
```
Interface                        Switchport Mode      Access Native Protected VLAN lists
-------------------------------- ---------- --------- ------ ------ --------- ----------
TFGigabitEthernet 0/3            enabled    ACCESS    1      1      Disabled  ALL
```

### После парсинга TextFSM/NTC

| Поле | Cisco IOS | NX-OS | QTech |
|------|-----------|-------|-------|
| `interface` | `Gi1/0/1` | `Ethernet1/2` | `TFGigabitEthernet 0/3` |
| `admin_mode` | `static access` | ❌ нет | ❌ нет |
| `mode` | `static access` (operational) | `trunk` | `ACCESS` |
| `switchport` | — | `Enabled` | `enabled` |
| `trunking_vlans` | `["ALL"]` (список!) | `"10,30,38"` (строка) | ❌ нет |
| `vlan_lists` | ❌ нет | ❌ нет | `ALL` |
| `access_vlan` | `47` | `1` | `1` |
| `native_vlan` | `1` | `1` | `1` |

### После нормализации

Все три платформы приводятся к **единому формату**:

```python
{
    "mode": "access" | "tagged" | "tagged-all",
    "native_vlan": "1",
    "access_vlan": "47",
    "tagged_vlans": "10,30,38",   # Пустая строка для access и tagged-all
}
```

---

## 11. Как возник баг с NX-OS

### Старый код (работал)

```python
# Одна строка обрабатывала ВСЕ платформы:
mode = row.get("mode", row.get("admin_mode", "")).lower()
# IOS:  row["admin_mode"] = "trunk"   → используется admin_mode → "trunk"
# NX-OS: row["mode"] = "trunk"        → используется mode → "trunk"
# Оба попадали в "trunk" → правильно!
```

### Рефакторинг (сломал NX-OS)

При добавлении QTech нужно было разделить логику — QTech возвращает `mode=ACCESS/TRUNK` (не такой формат, как у Cisco). Код разделили на ветки:

```python
admin_mode = row.get("admin_mode", "")

if admin_mode:           # ← IOS/Arista попадает сюда
    ...
elif switchport == "enabled":  # ← QTech попадает сюда
    ...                        # ← NX-OS ТОЖЕ попадает сюда! (switchport=Enabled)
```

NX-OS **не имеет** `admin_mode` → первая ветка не срабатывает → попадает в QTech ветку → ищет `vlan_lists` → его нет → пустая строка → `tagged-all` вместо `tagged`.

### Исправление

Добавлена отдельная ветка для NX-OS **между** IOS и QTech:

```python
if admin_mode:                                              # ← IOS/Arista
    ...
elif row.get("trunking_vlans") is not None and row.get("mode"):  # ← NX-OS
    ...
elif switchport == "enabled":                               # ← QTech
    ...
```

NX-OS определяется по наличию `trunking_vlans` + `mode` при отсутствии `admin_mode`.

---

## 12. Диаграмма полного потока

```
                        ┌─────────────────────────────┐
                        │  config: SECONDARY_COMMANDS  │
                        │  "switchport" → команда      │
                        └──────────────┬──────────────┘
                                       │
                                       ▼
┌────────────┐    SSH    ┌──────────────────────────────┐
│ Коммутатор │◄─────────│ _collect_from_device()        │
│            │─────────►│ conn.send_command(sw_cmd)     │
└────────────┘  текст   └──────────────┬───────────────┘
                                       │ сырой текст
                                       ▼
                        ┌──────────────────────────────┐
                        │ _parse_switchport_modes()     │
                        │ → передаёт platform как есть  │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │ NTCParser.parse()             │
                        │                              │
                        │ 1. Кастомный шаблон?          │
                        │    ("qtech", "show interface  │
                        │     switchport") → ДА         │
                        │    ("cisco_nxos", ...) → НЕТ  │
                        │                              │
                        │ 2. NTC Templates (fallback)   │
                        │    qtech → cisco_ios          │
                        │    cisco_nxos → cisco_nxos    │
                        └──────────────┬───────────────┘
                                       │ List[Dict]
                                       ▼
                        ┌──────────────────────────────┐
                        │ InterfaceNormalizer           │  Domain Layer
                        │ .normalize_switchport_data()  │
                        │                              │
                        │ admin_mode?    → IOS ветка    │
                        │ trunking_vlans + mode?        │
                        │                → NX-OS ветка  │
                        │ switchport=enabled?           │
                        │                → QTech ветка  │
                        │                              │
                        │ + get_interface_aliases()     │  constants
                        │   Gi0/1 → GigabitEthernet0/1 │
                        │   TFGigabitEthernet 0/3→TF0/3│
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │ enrich_with_switchport()      │  Domain Layer
                        │ interfaces + switchport_modes │
                        │ → каждому интерфейсу          │
                        │   присвоен mode, vlans        │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │ sync_interfaces()             │  NetBox Sync
                        │                              │
                        │ _build_create_data():         │
                        │   mode → "tagged"             │
                        │   untagged_vlan → vlan.id     │
                        │   tagged_vlans → [id1, id2]   │
                        │                              │
                        │ _build_update_data():         │
                        │   _check_mode()               │
                        │   _check_untagged_vlan()      │
                        │   _check_tagged_vlans()       │
                        └──────────────┬───────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │ NetBox API                    │
                        │ PATCH /api/dcim/interfaces/42 │
                        │ {"mode": "tagged",            │
                        │  "untagged_vlan": 1001,       │
                        │  "tagged_vlans": [1010, 1030]}│
                        └──────────────────────────────┘
```

---

## Итого

| Что | Где |
|-----|-----|
| Команды switchport | `core/constants/commands.py` — `SECONDARY_COMMANDS` |
| Кастомные шаблоны | `core/constants/commands.py` — `CUSTOM_TEXTFSM_TEMPLATES` |
| QTech TextFSM шаблон | `templates/qtech_show_interface_switchport.textfsm` |
| Отправка SSH | `collectors/interfaces.py` — `_collect_from_device()` |
| Координация парсинга | `collectors/interfaces.py` — `_parse_switchport_modes()` |
| NTCParser (кастомный → NTC) | `parsers/textfsm_parser.py` — `NTCParser.parse()` |
| Нормализация (3 ветки) + алиасы | `core/domain/interface.py` — `InterfaceNormalizer.normalize_switchport_data()` |
| Алиасы имён (единый источник) | `core/constants/interfaces.py` — `get_interface_aliases()` |
| Обогащение (Domain) | `core/domain/interface.py` — `InterfaceNormalizer.enrich_with_switchport()` |
| Парсинг media_type | `collectors/interfaces.py` — `_parse_media_types()` (тоже использует `get_interface_aliases`) |
| Sync create data | `netbox/sync/interfaces.py` — `_build_create_data()` |
| Sync check mode | `netbox/sync/interfaces.py` — `_check_mode()` |
| Sync check untagged | `netbox/sync/interfaces.py` — `_check_untagged_vlan()` |
| Sync check tagged | `netbox/sync/interfaces.py` — `_check_tagged_vlans()` |
| VLAN кэш | `netbox/sync/base.py` — `_get_vlan_by_vid()` |
| Парсинг диапазонов | `core/domain/vlan.py` — `parse_vlan_range()` |
| VlanSet сравнение | `core/domain/vlan.py` — `VlanSet` |
| Конфиг sync_vlans | `fields.yaml` — `sync.interfaces.options` |
