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
13. [Python-концепции в этом коде](#13-python-концепции-в-этом-коде)
14. [Как данные меняют тип на каждом шаге](#14-как-данные-меняют-тип-на-каждом-шаге)
15. [Отладка: как проверить каждый шаг](#15-отладка-как-проверить-каждый-шаг)
16. [Частые ошибки и как их найти](#16-частые-ошибки-и-как-их-найти)
17. [Попробуй сам (упражнения)](#17-попробуй-сам-упражнения)
18. [Как работает определение платформы и что делать для новой](#18-как-работает-определение-платформы-и-что-делать-для-новой)

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

## 13. Python-концепции в этом коде

Этот раздел объясняет Python-приёмы, которые встречаются в коде выше. Если ты уже
прочитал [01_PYTHON_BASICS.md](01_PYTHON_BASICS.md) — здесь будет глубже, с примерами
конкретно из switchport flow.

### 13.1 dict.get() с вложенным fallback

```python
# Обычный .get() — если ключа нет, вернёт значение по умолчанию:
row.get("admin_mode", "")
# Если "admin_mode" есть → его значение
# Если нет → пустая строка ""

# Вложенный .get() — цепочка поиска по двум ключам:
native_vlan = row.get("native_vlan", row.get("trunking_native_vlan", ""))
```

**Как это работает пошагово:**
1. Python сначала вычисляет аргументы функции (справа налево не работает — всё вычисляется ДО вызова)
2. Внутренний `row.get("trunking_native_vlan", "")` выполняется **всегда** — вернёт значение или `""`
3. Затем внешний `row.get("native_vlan", <результат_шага_2>)` ищет `"native_vlan"`
4. Если `"native_vlan"` есть — возвращает его, внутренний результат **выбрасывается**
5. Если нет — возвращает результат шага 2

**Почему не `row["native_vlan"]`?** — Вызовет `KeyError` если ключа нет. `.get()` безопасен.

```python
# Разница:
row = {"mode": "trunk"}

row["admin_mode"]        # → KeyError! Программа упадёт
row.get("admin_mode")    # → None (по умолчанию)
row.get("admin_mode", "") # → "" (наш default)
```

### 13.2 Кортеж (tuple) как ключ словаря

```python
# В CUSTOM_TEXTFSM_TEMPLATES ключ — кортеж из двух строк:
CUSTOM_TEXTFSM_TEMPLATES = {
    ("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm",
}

# Почему это работает?
template_key = (platform.lower(), command.lower())   # Создаём кортеж
if template_key in CUSTOM_TEXTFSM_TEMPLATES:         # Ищем в словаре
    template_file = CUSTOM_TEXTFSM_TEMPLATES[template_key]
```

**Правило Python:** ключом словаря может быть любой **неизменяемый** (immutable) тип:
- `str` — да: `{"hello": 1}`
- `int` — да: `{42: "answer"}`
- `tuple` — да: `{("a", "b"): 1}` ← используем здесь
- `list` — **нет**: `{[1, 2]: "x"}` → `TypeError: unhashable type: 'list'`

**Зачем кортеж?** Нужен составной ключ из двух значений (платформа + команда). Альтернатива — строка `"qtech|show interface switchport"`, но кортеж удобнее: не нужно думать о разделителе, нельзя случайно разрезать не там.

### 13.3 Truthiness (правдивость значений)

В Python многие значения можно проверять в `if` без `== True`:

```python
# Эти значения FALSY (считаются False):
if not "":        # Пустая строка → False
if not []:        # Пустой список → False
if not {}:        # Пустой словарь → False
if not None:      # None → False
if not 0:         # Ноль → False

# Эти значения TRUTHY (считаются True):
if "trunk":       # Непустая строка → True
if [1, 2]:        # Непустой список → True
if {"a": 1}:      # Непустой словарь → True
```

**Где это используется в нашем коде:**

```python
# 1. Проверка что парсинг вернул результат:
parsed = self._parser.parse(output, platform, command)
if parsed:        # True если список НЕ пустой (есть данные)
    modes = self._normalizer.normalize_switchport_data(parsed, platform)
    if modes:     # True если словарь НЕ пустой (есть mode)
        return modes

# 2. Проверка что команда есть для платформы:
sw_cmd = self.switchport_commands.get(device.platform)
if sw_cmd:        # True если строка НЕ пустая (команда найдена)
                  # None тоже falsy — если .get() не нашёл ключ

# 3. Пропуск пустых интерфейсов:
iface = row.get("interface", "")
if not iface:     # True если iface пустой ("") → пропускаем
    continue

# 4. Проверка VLAN:
if intf.tagged_vlans:  # "10,30,38" → True (непустая строка)
                       # "" → False (пустая строка)
```

**Частая ошибка новичков:** путать `if not x` (проверка truthiness) и `if x is not None` (проверка на None конкретно). Разница:

```python
value = ""

if not value:          # True! Пустая строка — falsy
    print("Пусто")

if value is not None:  # True! "" это НЕ None, это пустая строка
    print("Не None")

# Оба условия могут быть True одновременно!
```

**В нашем коде NX-OS** это критично (строка 350):
```python
elif row.get("trunking_vlans") is not None and row.get("mode"):
#    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^      ^^^^^^^^^^^^^^^^^^^
#    is not None: проверяет что ключ ЕСТЬ     truthiness: проверяет что НЕ пустой
#    (даже если значение "")                  (пустая строка не пройдёт)
```

Для NX-OS `trunking_vlans` может быть `""` (пустая строка) — это **не** None. Если бы мы написали `if row.get("trunking_vlans")`, пустая строка была бы False и NX-OS ветка не сработала бы.

### 13.4 isinstance() — проверка типа данных

```python
raw_vlans = row.get("trunking_vlans", "")

# NTC Templates для Cisco IOS возвращает СПИСОК:
#   raw_vlans = ["10", "20", "30"]
# NTC Templates для NX-OS возвращает СТРОКУ:
#   raw_vlans = "10,30,38"

# Нужно обработать оба варианта:
if isinstance(raw_vlans, list):
    # Список → объединяем в строку через запятую
    trunking_vlans = ",".join(str(v) for v in raw_vlans)
else:
    # Уже строка → используем как есть
    trunking_vlans = str(raw_vlans)
```

**Зачем `isinstance()` вместо `type()`?**

```python
# type() — проверяет ТОЧНЫЙ тип:
type(raw_vlans) == list     # True только для list, не для подклассов

# isinstance() — проверяет тип И его наследников:
isinstance(raw_vlans, list)  # True для list и любого подкласса list
```

`isinstance()` — предпочтительный способ в Python. Но здесь разница не важна — нам нужно просто отличить список от строки.

### 13.5 Генераторное выражение в join()

```python
trunking_vlans = ",".join(str(v) for v in raw_vlans).lower().strip()
#                         ^^^^^^^^^^^^^^^^^^^^^^^^
#                         Генераторное выражение
```

**Разберём по частям:**

```python
# Шаг 1: Генераторное выражение
str(v) for v in raw_vlans
# raw_vlans = ["10", "20", "30"]
# Для каждого элемента вызывает str(v):
# str("10") → "10", str("20") → "20", str("30") → "30"
# Результат: генератор, который выдаёт "10", "20", "30"

# Шаг 2: join() объединяет через запятую
",".join(...)  # "10,20,30"

# Шаг 3: .lower() → приводит к нижнему регистру
"10,20,30".lower()  # "10,20,30" (цифры не меняются)
# Но если было "ALL" → "all"

# Шаг 4: .strip() → убирает пробелы по краям
"10,20,30".strip()  # "10,20,30"
```

**Генератор vs список:**
```python
# Генераторное выражение (без скобок в join):
",".join(str(v) for v in raw_vlans)     # Экономит память — элементы по одному

# List comprehension (со скобками):
",".join([str(v) for v in raw_vlans])   # Создаёт весь список в памяти

# Для маленьких списков разницы нет. Для больших — генератор эффективнее.
```

**Цепочка методов** (method chaining) — каждый метод строки возвращает НОВУЮ строку:
```python
# Строки в Python НЕИЗМЕНЯЕМЫ (immutable):
s = "  Hello World  "
s.lower()   # → "  hello world  " (новая строка, s НЕ изменился!)
s.strip()   # → "Hello World" (новая строка, s НЕ изменился!)

# Чтобы сохранить результат:
s = s.lower().strip()  # → "hello world"

# В нашем коде:
trunking_vlans = ",".join(...).lower().strip()
# join() → новая строка → .lower() → новая строка → .strip() → итоговая строка
```

### 13.6 Ссылки на объекты (reference sharing)

Это **самая важная** Python-концепция в этом коде:

```python
# В normalize_switchport_data():
mode_data = {
    "mode": netbox_mode,
    "native_vlan": str(native_vlan) if native_vlan else "",
    "access_vlan": str(access_vlan) if access_vlan else "",
    "tagged_vlans": trunking_vlans if netbox_mode == "tagged" else "",
}
modes[iface] = mode_data

# Алиасы указывают на ТОТ ЖЕ объект:
for alias in get_interface_aliases(iface):
    if alias != iface:
        modes[alias] = mode_data   # НЕ копия! Та же ссылка!
```

**Что это значит в памяти?**

```python
# После выполнения:
modes = {
    "Gi0/1":                mode_data,   # ─┐
    "GigabitEthernet0/1":   mode_data,   # ─┤ Все три указывают
    "Gig0/1":               mode_data,   # ─┘ на ОДИН объект в памяти
}

# Проверим:
modes["Gi0/1"] is modes["GigabitEthernet0/1"]  # → True (один объект)

# Если изменить через один ключ — изменится везде:
modes["Gi0/1"]["mode"] = "access"
print(modes["GigabitEthernet0/1"]["mode"])  # → "access" (тоже изменился!)
```

**Почему это безопасно в нашем коде?** После `normalize_switchport_data()` словари
только ЧИТАЮТСЯ (в `enrich_with_switchport()`), но не изменяются. Если бы код
изменял `mode_data` после создания алиасов — был бы баг.

**Как создать КОПИЮ (если нужно):**
```python
# Поверхностная копия:
modes[alias] = mode_data.copy()       # Новый dict, но значения — те же объекты

# Глубокая копия (для вложенных структур):
import copy
modes[alias] = copy.deepcopy(mode_data)  # Полная копия всего дерева
```

### 13.7 Порядок elif имеет значение

```python
if admin_mode:                                              # Ветка 1: IOS
    ...
elif row.get("trunking_vlans") is not None and row.get("mode"):  # Ветка 2: NX-OS
    ...
elif switchport == "enabled":                               # Ветка 3: QTech
    ...
```

**Это НЕ три независимые проверки.** Это цепочка — выполнится **только первая** подходящая:

```python
# Данные NX-OS:
row = {"mode": "trunk", "switchport": "Enabled", "trunking_vlans": "10,30"}

admin_mode = ""              # row.get("admin_mode", "").lower() → пустая строка
switchport = "enabled"       # row.get("switchport", "").lower() → "enabled"

# Ветка 1: if admin_mode → "" → False → пропускаем
# Ветка 2: elif trunking_vlans is not None AND mode → True → ВЫПОЛНЯЕМ
# Ветка 3: elif switchport == "enabled" → НЕ ПРОВЕРЯЕТСЯ (ветка 2 уже сработала)
```

**Что будет если поменять порядок веток 2 и 3?**

```python
# НЕПРАВИЛЬНЫЙ порядок:
if admin_mode:                    # Ветка 1: IOS
    ...
elif switchport == "enabled":     # Ветка 3 стала второй: QTech
    ...
elif row.get("trunking_vlans")...: # Ветка 2 стала третьей: NX-OS
    ...
```

NX-OS имеет `switchport = "Enabled"` → `.lower()` → `"enabled"` → **попадёт в QTech ветку!**
А QTech ветка ищет `vlan_lists`, которого у NX-OS нет → mode будет пустой → **баг!**

**Вывод:** порядок elif — это неявная логика определения платформы по полям данных (duck typing). Менять порядок нельзя.

### 13.8 Атрибуты класса vs экземпляра

```python
class InterfacesCollector(BaseCollector):
    # АТРИБУТЫ КЛАССА — общие для всех экземпляров:
    lag_commands = SECONDARY_COMMANDS.get("lag", {})
    switchport_commands = SECONDARY_COMMANDS.get("switchport", {})
    media_type_commands = SECONDARY_COMMANDS.get("media_type", {})

    def __init__(self, collect_switchport=True, **kwargs):
        super().__init__(**kwargs)
        # АТРИБУТЫ ЭКЗЕМПЛЯРА — у каждого экземпляра свои:
        self.collect_switchport = collect_switchport
        self._normalizer = InterfaceNormalizer()
```

**В чём разница?**

```python
# Атрибуты класса:
# Вычисляются ОДИН раз при загрузке модуля
# Доступны через класс: InterfacesCollector.lag_commands
# И через экземпляр: self.lag_commands (читает из класса)
# Одинаковые для ВСЕХ экземпляров

# Атрибуты экземпляра:
# Создаются в __init__ при каждом вызове конструктора
# Доступны только через self: self.collect_switchport
# У каждого экземпляра свои значения

# Пример:
c1 = InterfacesCollector(collect_switchport=True)
c2 = InterfacesCollector(collect_switchport=False)

c1.lag_commands is c2.lag_commands        # True — один объект (атрибут класса)
c1.collect_switchport == c2.collect_switchport  # False — разные значения
```

**Зачем `lag_commands` — атрибут класса?** Словарь команд не зависит от конкретного
экземпляра. Он загружается один раз из `SECONDARY_COMMANDS` и используется всеми
коллекторами. Экономит память и время.

### 13.9 try/except для graceful degradation

```python
switchport_modes = {}

if self.collect_switchport:
    sw_cmd = self.switchport_commands.get(device.platform)
    if sw_cmd:
        try:
            sw_response = conn.send_command(sw_cmd)
            switchport_modes = self._parse_switchport_modes(...)
        except Exception as e:
            logger.warning(f"ошибка получения switchport info: {e}")
```

**Что здесь происходит:**

1. `switchport_modes = {}` — пустой словарь (значение по умолчанию)
2. Пытаемся собрать данные в `try`
3. Если **любая** ошибка (SSH упал, парсер сломался) — `except` ловит её
4. `switchport_modes` остаётся `{}` (пустой)
5. Дальше в коде: `if switchport_modes:` → False → обогащение пропускается

**Это паттерн "graceful degradation"** — программа продолжает работу без этих данных.
Интерфейсы соберутся, просто без switchport mode. Лучше частичные данные, чем краш.

**Почему `except Exception` (а не конкретный тип)?**

```python
# Конкретный тип — ловит только его:
except ConnectionError as e:      # Только ошибки соединения
except ValueError as e:           # Только ошибки значений

# Exception — ловит ВСЁ (кроме SystemExit, KeyboardInterrupt):
except Exception as e:            # Любая ошибка

# В нашем случае Exception оправдан — мы не знаем заранее какая ошибка
# может возникнуть (SSH, парсинг, кодировка...), и для всех реакция одна:
# залогировать и продолжить.
```

### 13.10 set (множество) — зачем и как

```python
# core/constants/interfaces.py — get_interface_aliases()
def get_interface_aliases(interface: str) -> List[str]:
    aliases = {interface}        # ← Это SET (множество), не dict!
    clean = interface.replace(" ", "")
    aliases.add(clean)           # .add() — метод set (не .append()!)
    ...
    return list(aliases)         # Конвертируем set → list перед возвратом
```

**Почему `{interface}` — это set, а не dict?**

```python
# Пустые скобки — dict:
x = {}           # dict
type(x)          # <class 'dict'>

# Скобки с ОДНИМ значением (без двоеточия) — set:
x = {"hello"}    # set
type(x)          # <class 'set'>

# Скобки с двоеточием — dict:
x = {"key": "value"}  # dict
```

**Зачем set вместо list?**

```python
# Set автоматически убирает дубликаты:
aliases = {"Gi0/1"}
aliases.add("GigabitEthernet0/1")   # Добавился
aliases.add("Gi0/1")                # НЕ добавился — уже есть!
# aliases = {"Gi0/1", "GigabitEthernet0/1"}

# Список НЕ убирает дубликаты:
aliases = ["Gi0/1"]
aliases.append("Gi0/1")             # Добавился!
# aliases = ["Gi0/1", "Gi0/1"] — дубликат!
```

Для алиасов нам важно: `normalize_interface_short("Gi0/1")` может вернуть `"Gi0/1"`
(то же самое) — set автоматически отсечёт дубликат.

**Зачем `list(aliases)` в конце?**

Set неупорядочен и не поддерживает индексацию (`aliases[0]` — ошибка). Возвращаем
list, чтобы вызывающий код мог работать с результатом обычным способом.

### 13.11 break в вложенном цикле

```python
# enrich_with_switchport():
for iface in interfaces:                        # Внешний цикл
    sw_data = switchport_modes.get(iface_name)
    if not sw_data:
        for variant in get_interface_aliases(iface_name):  # Внутренний цикл
            if variant in switchport_modes:
                sw_data = switchport_modes[variant]
                break                            # Выходит ТОЛЬКО из внутреннего!
    # Здесь продолжается ВНЕШНИЙ цикл
    if sw_data:
        iface["mode"] = sw_data.get("mode", "")
```

**`break` выходит ТОЛЬКО из ближайшего цикла:**

```python
for i in [1, 2, 3]:           # Цикл A
    for j in ["a", "b", "c"]: # Цикл B
        if j == "b":
            break              # Выходит из цикла B
    # Цикл A продолжается!
    print(i)                   # Выведет 1, 2, 3
```

В нашем коде `break` нужен для оптимизации: нашли алиас — хватит перебирать остальные.
Без `break` код тоже работал бы, но проверял бы лишние варианты.

### 13.12 Изменение словаря "на месте" (in-place mutation)

```python
def enrich_with_switchport(self, interfaces, switchport_modes, ...):
    for iface in interfaces:
        ...
        if sw_data:
            iface["mode"] = sw_data.get("mode", "")        # Изменяем dict!
            iface["native_vlan"] = sw_data.get("native_vlan", "")
    return interfaces   # Возвращаем ТОТ ЖЕ список (не копию)
```

**Что здесь неочевидно для новичка:**

```python
# interfaces — это список словарей:
interfaces = [
    {"interface": "Gi0/1", "status": "up"},
    {"interface": "Gi0/2", "status": "down"},
]

# for iface in interfaces — iface это ССЫЛКА на словарь в списке:
iface = interfaces[0]  # iface и interfaces[0] — один объект!

# Когда мы пишем iface["mode"] = "access":
iface["mode"] = "access"
print(interfaces[0]["mode"])  # → "access" (изменился оригинал!)
```

**Это называется "side effect"** — функция изменяет входные данные. В нашем проекте
это осознанный выбор: обогащение модифицирует существующие словари, а не создаёт новые.
`return interfaces` возвращает тот же список для удобства, но можно было бы не возвращать.

### 13.13 Тернарный оператор (условное выражение)

```python
# В normalize_switchport_data():
mode_data = {
    "native_vlan": str(native_vlan) if native_vlan else "",
    #              ^^^^^^^^^^^^^^^^^    ^^^^^^^^^^^     ^^
    #              значение если True   условие       значение если False
    "tagged_vlans": trunking_vlans if netbox_mode == "tagged" else "",
}
```

**Синтаксис:** `значение_true if условие else значение_false`

```python
# Это эквивалентно:
if native_vlan:
    result = str(native_vlan)
else:
    result = ""

# Но в одну строку. Удобно для присваивания значений.

# Ещё примеры из проекта:
data["type"] = intf.port_type or "1000base-t"
#              ^^^^^^^^^^^^^^    ^^^^^^^^^^^^
#              Если truthy       Если falsy (None, "")
# Это short-circuit OR — не тернарный, но похожий паттерн.
```

---

## 14. Как данные меняют тип на каждом шаге

Одна из главных сложностей — понять, **какой тип данных** на каждом этапе.
Вот полная карта трансформаций:

```
Шаг 1: SSH-ответ
─────────────────
Тип: str (одна большая строка)
Пример:
"Name: Ethernet1/2\n  Switchport: Enabled\n  Operational Mode: trunk\n  ..."
│
▼

Шаг 2: TextFSM парсинг
───────────────────────
Тип: List[Dict[str, str]]  (список словарей, все значения — строки)
Пример:
[
    {"interface": "Ethernet1/2", "mode": "trunk", "trunking_vlans": "10,30,38", ...},
    {"interface": "Ethernet1/3", "mode": "access", "trunking_vlans": "", ...},
]
│
▼

Шаг 3: normalize_switchport_data()
───────────────────────────────────
Тип: Dict[str, Dict[str, str]]  (словарь словарей, ключ = имя интерфейса)
Пример:
{
    "Ethernet1/2":  {"mode": "tagged", "native_vlan": "1", "access_vlan": "1", "tagged_vlans": "10,30,38"},
    "Eth1/2":       {"mode": "tagged", ...},   ← алиас (тот же объект!)
    "Ethernet1/3":  {"mode": "access", "native_vlan": "1", "access_vlan": "1", "tagged_vlans": ""},
    "Eth1/3":       {"mode": "access", ...},   ← алиас
}
│
▼

Шаг 4: enrich_with_switchport()
────────────────────────────────
Тип: List[Dict[str, str]]  (входной список модифицирован, добавлены поля)
Пример:
[
    {
        "interface": "Ethernet1/2",
        "status": "up",
        "speed": "10000",
        "mode": "tagged",            ← ДОБАВЛЕНО
        "native_vlan": "1",          ← ДОБАВЛЕНО
        "access_vlan": "1",          ← ДОБАВЛЕНО
        "tagged_vlans": "10,30,38",  ← ДОБАВЛЕНО
    },
    ...
]
│
▼

Шаг 5: _build_create_data() / _build_update_data()
───────────────────────────────────────────────────
Тип: Dict[str, Any]  (словарь для NetBox API, значения — разных типов!)
Пример:
{
    "device": 42,                     ← int (ID устройства в NetBox)
    "name": "Ethernet1/2",           ← str
    "type": "10gbase-x-sfpp",        ← str (slug типа порта)
    "mode": "tagged",                ← str
    "untagged_vlan": 1001,           ← int (NetBox ID VLAN, НЕ VID!)
    "tagged_vlans": [1010, 1030],    ← List[int] (список NetBox ID VLAN)
}
│
▼

Шаг 6: NetBox API
──────────────────
Тип: JSON (отправляется как HTTP PATCH/POST)
{"mode": "tagged", "untagged_vlan": 1001, "tagged_vlans": [1010, 1030]}
```

**Обрати внимание на превращения VLAN:**

```
Коммутатор: trunking_vlans = "10,30,38"     ← строка с VID (номерами VLAN)
          ↓
Парсинг:   tagged_vlans = "10,30,38"        ← всё ещё строка с VID
          ↓
parse_vlan_range("10,30,38") → [10, 30, 38] ← список int (VID)
          ↓
_get_vlan_by_vid(10) → vlan.id = 1010       ← NetBox ID (не VID!)
          ↓
NetBox API: tagged_vlans = [1010, 1030, 1038] ← список NetBox ID
```

VID (VLAN ID на коммутаторе, например 10) и NetBox ID (внутренний идентификатор
в базе NetBox, например 1010) — **разные числа!** Их нельзя путать.

---

## 15. Отладка: как проверить каждый шаг

Если switchport mode не работает — нужно найти на каком шаге данные "ломаются".
Вот как проверить каждый шаг.

### 15.1 Шаг 1: Проверить сырой вывод коммутатора

```bash
# Сохранить сырой текст (как видишь в терминале коммутатора):
cd /home/sa/project
source network_collector/myenv/bin/activate
python -m network_collector run "show interface switchport" --format raw > raw_switchport.txt
```

Откройте `raw_switchport.txt` — это именно то, что коммутатор вернул по SSH.
Если текст пустой или ошибка — проблема на уровне SSH/команды.

### 15.2 Шаг 2: Проверить парсинг TextFSM

```bash
# Парсинг без нормализации (сырой результат TextFSM):
python -m network_collector interfaces --format parsed > parsed_output.json
```

В файле будут словари **до** нормализации — именно то, что возвращает TextFSM.
Проверь:
- Есть ли поле `admin_mode`? (Cisco IOS) или `mode`? (NX-OS)
- Есть ли `switchport`? (QTech, NX-OS)
- Есть ли `trunking_vlans`? Какого типа — список или строка?

### 15.3 Шаг 3: Добавить временный print в нормализацию

```python
# core/domain/interface.py — в normalize_switchport_data():
def normalize_switchport_data(self, parsed, platform):
    modes = {}
    for row in parsed:
        iface = row.get("interface", "")

        # ═══ ВРЕМЕННАЯ ОТЛАДКА ═══
        print(f"DEBUG: interface={iface}")
        print(f"  admin_mode={row.get('admin_mode', '')!r}")
        print(f"  mode={row.get('mode', '')!r}")
        print(f"  switchport={row.get('switchport', '')!r}")
        print(f"  trunking_vlans={row.get('trunking_vlans')!r}")
        # ═══ КОНЕЦ ОТЛАДКИ ═══
        ...
```

`!r` в f-string показывает значение с кавычками — видно разницу между `""` и `None`:
```
DEBUG: interface=Ethernet1/2
  admin_mode=''              ← пустая строка (не None!)
  mode='trunk'
  switchport='Enabled'
  trunking_vlans='10,30,38'  ← строка (не список!)
```

### 15.4 Шаг 4: Проверить обогащение

```python
# collectors/interfaces.py — после вызова enrich_with_switchport():
if switchport_modes:
    data = self._normalizer.enrich_with_switchport(data, switchport_modes, lag_membership)

    # ═══ ВРЕМЕННАЯ ОТЛАДКА ═══
    for iface in data[:3]:   # Первые 3 интерфейса
        print(f"ENRICHED: {iface.get('interface')} → mode={iface.get('mode', 'НЕТ')}")
    # ═══ КОНЕЦ ОТЛАДКИ ═══
```

Если mode = `"НЕТ"` — данные из switchport_modes не нашлись для этого интерфейса.
Скорее всего проблема с алиасами имён.

### 15.5 Шаг 5: Проверить sync (dry-run)

```bash
# Запуск синхронизации без реальных изменений:
python -m network_collector sync-netbox --interfaces --dry-run

# dry-run покажет:
# [DRY-RUN] Создать: GigabitEthernet0/1 (mode=access, untagged_vlan=47)
# [DRY-RUN] Обновить: Ethernet1/2 (mode: None → tagged)
```

Если mode `None → tagged` — значит данные собраны правильно, но в NetBox ещё не записаны.
Если mode не показан — проверь `fields.yaml`:

```yaml
# Должно быть:
sync:
  interfaces:
    options:
      sync_vlans: true    # ← Должно быть true
    fields:
      mode:
        enabled: true     # ← Должно быть true
```

### 15.6 Таблица диагностики

| Симптом | Где проблема | Как проверить |
|---------|-------------|---------------|
| Пустой raw output | SSH/команда | `--format raw`, проверить доступ к устройству |
| Нет полей в parsed | TextFSM шаблон | `--format parsed`, проверить шаблон |
| mode пустой после нормализации | `normalize_switchport_data()` | print/debug в методе |
| mode есть, но не в интерфейсе | `enrich_with_switchport()` | Проблема с алиасами имён |
| mode есть, но VLAN не пишется | `fields.yaml` | Проверить `sync_vlans: true` |
| Неправильный mode (tagged вместо tagged-all) | Ветка нормализации | Посмотреть какая ветка сработала |

---

## 16. Частые ошибки и как их найти

### 16.1 "У меня mode пустой для всех интерфейсов"

**Причина 1:** Платформы нет в `SECONDARY_COMMANDS["switchport"]`

```python
# core/constants/commands.py
SECONDARY_COMMANDS["switchport"] = {
    "cisco_ios": "show interfaces switchport",
    "cisco_nxos": "show interface switchport",
    # Нет "eltex"! → sw_cmd = None → команда не выполнится
}
```

Решение: добавить платформу в словарь.

**Причина 2:** Кастомный шаблон зарегистрирован, но файла нет

```python
# В CUSTOM_TEXTFSM_TEMPLATES:
("qtech", "show interface switchport"): "qtech_show_interface_switchport.textfsm"
# Но файл templates/qtech_show_interface_switchport.textfsm отсутствует!
```

Парсер залогирует warning: `"Кастомный шаблон не найден"`, затем fallback на NTC
(который не знает QTech) → пустой результат.

**Причина 3:** Неправильный `normalize=False`

В `_parse_switchport_modes()` парсер вызывается с `normalize=False`. Это значит
имена полей НЕ приводятся к lower_case. Если шаблон возвращает `ADMIN_MODE` а код
ищет `admin_mode` — поле не найдётся.

### 16.2 "tagged вместо tagged-all (или наоборот)"

**Причина:** Данные NX-OS попали в неправильную ветку нормализации.

Проверь вывод парсера:
```python
# Если trunking_vlans = "1-4094" → должно быть tagged-all
# Если trunking_vlans = "10,30,38" → должно быть tagged

# Ошибка: trunking_vlans = None (не пустая строка, а None!)
# → ветка NX-OS не сработает (проверка is not None провалится)
# → данные попадут в QTech ветку → неправильный результат
```

### 16.3 "Данные есть, но алиасы не работают"

**Симптом:** `switchport_modes` содержит `"Gi0/1"`, а интерфейс называется
`"GigabitEthernet0/1"` — обогащение не находит соответствие.

**Как проверить:**
```python
# Добавить print в enrich_with_switchport():
print(f"Ищу: {iface_name}")
print(f"Алиасы: {get_interface_aliases(iface_name)}")
print(f"Ключи switchport: {list(switchport_modes.keys())[:5]}")
```

Если алиасы не содержат нужный вариант — нужно добавить маппинг в
`core/constants/interfaces.py` → `INTERFACE_SHORT_MAP` / `INTERFACE_FULL_MAP`.

### 16.4 "VLAN не синхронизируется, хотя mode правильный"

Проверь по порядку:

1. `fields.yaml` → `sync_vlans: true`? (по умолчанию может быть false)
2. VLAN с таким VID **существует в NetBox**? (`_get_vlan_by_vid()` вернёт None если нет)
3. VLAN привязан к правильному **site**? (кэш загружает VLAN по site)
4. Для `tagged-all` VLAN **не синхронизируются** — это by design (все 4094 VLAN не нужно перечислять)

### 16.5 "Ошибка 'str' object has no attribute 'get'"

```python
# Ошибка в строке:
iface["mode"] = sw_data.get("mode", "")
# TypeError: 'str' object has no attribute 'get'
```

Значит `sw_data` — строка, а не словарь. Скорее всего `normalize_switchport_data()`
вернул неправильную структуру. Ожидается `Dict[str, Dict]`, а получился `Dict[str, str]`.

---

## 17. Попробуй сам (упражнения)

### Упражнение 1: Прочитай данные глазами Python

Вот данные NX-OS. Пройди по коду `normalize_switchport_data()` вручную и определи
какой `netbox_mode` получится:

```python
row = {
    "interface": "Ethernet1/5",
    "switchport": "Enabled",
    "mode": "trunk",
    "access_vlan": "1",
    "native_vlan": "1",
    "trunking_vlans": "1-4094",
}
```

<details>
<summary>Ответ</summary>

1. `admin_mode = row.get("admin_mode", "").lower()` → `""` (ключа нет)
2. `switchport = row.get("switchport", "").lower()` → `"enabled"`
3. Ветка 1: `if admin_mode:` → `""` → False → пропуск
4. Ветка 2: `row.get("trunking_vlans") is not None` → `"1-4094" is not None` → True
   AND `row.get("mode")` → `"trunk"` → True → **ветка 2 сработала!**
5. `nxos_mode = "trunk"` → `"trunk" in nxos_mode` → True
6. `trunking_vlans = "1-4094"` → `.lower().strip()` → `"1-4094"`
7. `trunking_vlans in ("1-4094", "1-4093", "1-4095")` → **True!**
8. → `netbox_mode = "tagged-all"`, `trunking_vlans = ""`

**Результат:** `{"mode": "tagged-all", "native_vlan": "1", ...}`
</details>

### Упражнение 2: Найди баг

В этом коде есть ошибка. Найди её:

```python
def normalize_switchport_data(self, parsed, platform):
    modes = {}
    for row in parsed:
        iface = row.get("interface", "")
        admin_mode = row.get("admin_mode", "").lower()

        if admin_mode:
            if "access" in admin_mode:
                netbox_mode = "access"
            elif "trunk" in admin_mode:
                netbox_mode = "tagged"  # ← Всегда tagged?

        modes[iface] = {"mode": netbox_mode}
    return modes
```

<details>
<summary>Ответ</summary>

**Баг:** Trunk с `trunking_vlans = "ALL"` должен быть `tagged-all`, а не `tagged`.
Код не проверяет значение `trunking_vlans` — всегда ставит `tagged` для любого trunk.

**Как исправить:** Добавить проверку `trunking_vlans` (как в реальном коде):
```python
elif "trunk" in admin_mode:
    raw_vlans = row.get("trunking_vlans", "")
    if not raw_vlans or raw_vlans == "all":
        netbox_mode = "tagged-all"
    else:
        netbox_mode = "tagged"
```
</details>

### Упражнение 3: Что выведет код?

```python
data = {"mode": "access", "vlan": "10"}
modes = {}
modes["Gi0/1"] = data
modes["GigabitEthernet0/1"] = data

modes["Gi0/1"]["mode"] = "tagged"

print(modes["GigabitEthernet0/1"]["mode"])
```

<details>
<summary>Ответ</summary>

**Выведет: `tagged`**

Обе записи указывают на **один и тот же объект** `data`. Изменение через один ключ
видно через другой. Это то, как работают алиасы в `normalize_switchport_data()` —
все варианты имени ссылаются на один словарь.

Если нужны независимые копии:
```python
modes["GigabitEthernet0/1"] = data.copy()  # Поверхностная копия
```
</details>

### Упражнение 4: Добавь новую платформу

Представь, что появилась платформа `eltex` с командой `show interfaces switchport`.
TextFSM возвращает данные в формате Cisco IOS (есть `admin_mode`).

Что нужно сделать, чтобы switchport заработал?

<details>
<summary>Ответ</summary>

**Только одну строку в `core/constants/commands.py`:**

```python
SECONDARY_COMMANDS["switchport"] = {
    ...
    "eltex": "show interfaces switchport",     # ← Добавить
}
```

Больше ничего не нужно, потому что:
1. Формат как у Cisco IOS → NTC Templates справится (fallback через `NTC_PLATFORM_MAP`)
2. Есть `admin_mode` → сработает ветка 1 в `normalize_switchport_data()`
3. Алиасы уже поддерживают стандартные имена Cisco

Если бы формат был уникальный — понадобился бы кастомный TextFSM шаблон
и возможно новая ветка в `normalize_switchport_data()`.
</details>

### Упражнение 5: Отладь проблему

Пользователь жалуется: "У QTech mode = пустой для всех портов".
Ты добавляешь print в `normalize_switchport_data()` и видишь:

```
DEBUG: interface=TFGigabitEthernet 0/3
  admin_mode=''
  mode='ACCESS'
  switchport='Enabled'
  trunking_vlans=None
```

Какая ветка сработает? Почему mode пустой?

<details>
<summary>Ответ</summary>

Пройдём по веткам:
1. `if admin_mode:` → `""` → False → пропуск
2. `elif row.get("trunking_vlans") is not None and row.get("mode"):` →
   `None is not None` → **False!** → пропуск
3. `elif switchport == "enabled":` → `"Enabled".lower()` → нужно проверить...
   `switchport = row.get("switchport", "").lower()` → `"enabled"` → **True!** → сработает!

Стоп, если ветка 3 сработала — mode не должен быть пустой. Проверяем внимательнее:
`switchport` в DEBUG = `'Enabled'` (с большой буквы). А в коде:
`switchport = row.get("switchport", "").lower()` → `"enabled"`.

Значит ветка 3 должна сработать. Проблема в другом: `qtech_mode = row.get("mode", "").upper()` → `"ACCESS"`.
`if qtech_mode == "ACCESS":` → True → `netbox_mode = "access"`.

**Ответ:** В этом примере mode **не** должен быть пустым — он должен быть `"access"`.
Если он пустой — баг в другом месте (например, ключ поля `"mode"` в TextFSM шаблоне
написан с другим регистром, или `normalize=True` изменил имена полей).

Это реальный паттерн отладки: добавляй print на каждом шаге и проверяй
какая ветка РЕАЛЬНО сработала.
</details>

---

## 18. Как работает определение платформы и что делать для новой

### Проблема: код не проверяет название платформы

В `normalize_switchport_data()` **нигде нет** проверки вида `if platform == "cisco_ios"`.
Вместо этого код определяет платформу по **наличию полей** в данных (duck typing):

```python
# Упрощённая схема ветвления:
if admin_mode:                                              # Ветка 1
    ...
elif row.get("trunking_vlans") is not None and row.get("mode"):  # Ветка 2
    ...
elif switchport == "enabled":                               # Ветка 3
    ...
# НЕТ else-ветки! Если ничего не подошло → mode = "" (пустой)
```

Почему это работает? Потому что **каждая платформа возвращает уникальный набор полей**:

### Какие поля возвращает каждый TextFSM-шаблон

Мы проверили реальные NTC-шаблоны и наш кастомный шаблон QTech. Вот полная таблица:

| Поле | Cisco IOS (NTC) | NX-OS (NTC) | QTech (кастомный) |
|------|:---------------:|:-----------:|:-----------------:|
| `interface` | + | + | + |
| `switchport` | + (`Enabled`) | + (`Enabled`) | + (`enabled`) |
| **`admin_mode`** | **+ (ключевое!)** | **нет** | **нет** |
| `mode` | + (operational) | + (operational) | + (`ACCESS`/`TRUNK`) |
| `access_vlan` | + | + | + |
| `native_vlan` | + | + | + |
| `trunking_vlans` | + (**список!**) | + (**строка!**) | **нет** |
| `voice_vlan` | + | + | нет |
| `vlan_lists` | нет | нет | **+ (только QTech)** |
| `protected` | нет | нет | + |

### Дерево принятия решений

Вот точный алгоритм, по которому код определяет платформу:

```
Вход: row = словарь из TextFSM парсинга
│
├─ switchport == "disabled"? → ДА → пропускаем порт (не switchport)
│
├─ admin_mode непустой? (row.get("admin_mode", "").lower())
│  │
│  ├─ ДА → ВЕТКА 1: CISCO IOS / ARISTA
│  │   Почему: ТОЛЬКО Cisco IOS/Arista NTC-шаблон возвращает поле admin_mode
│  │   NX-OS — не возвращает. QTech — не возвращает.
│  │
│  └─ НЕТ (admin_mode пустой или отсутствует) → идём дальше
│
├─ trunking_vlans is not None И mode непустой?
│  │
│  ├─ ДА → ВЕТКА 2: NX-OS
│  │   Почему: NX-OS имеет trunking_vlans (строка) + mode, но НЕ имеет admin_mode
│  │   QTech тоже не имеет admin_mode, но у него trunking_vlans = None (нет такого поля)
│  │
│  └─ НЕТ → идём дальше
│
├─ switchport == "enabled"?
│  │
│  ├─ ДА → ВЕТКА 3: QTECH
│  │   Почему: у QTech нет ни admin_mode, ни trunking_vlans
│  │   Остаётся только switchport="enabled" + свои поля (mode, vlan_lists)
│  │
│  └─ НЕТ → НИЧЕГО НЕ СРАБОТАЛО
│
└─ Результат: mode = "" (пустой) — порт записывается, но без mode
```

**Ключевой момент:** ветвление работает по **исключению**. Cisco IOS "забирает" всё
что имеет `admin_mode`. Из оставшихся NX-OS "забирает" всё что имеет `trunking_vlans`.
Из оставшихся QTech "забирает" всё с `switchport=enabled`.

### Что было с NX-OS багом

Изначально NX-OS ветки **не было** — был только Cisco и QTech:

```python
# Старый код (2 ветки):
if admin_mode:                  # Cisco IOS/Arista
    ...
elif switchport == "enabled":   # QTech ... и NX-OS тоже попадал СЮДА!
    ...
```

NX-OS возвращает `switchport: "Enabled"` → `.lower()` → `"enabled"` → попадал в QTech ветку.
QTech ветка ищет `vlan_lists`, которого у NX-OS нет → mode получался неправильный.

**Исправление:** добавлена ветка 2 **между** Cisco и QTech, которая перехватывает NX-OS
по уникальной комбинации `trunking_vlans is not None + mode`.

### Что будет когда добавляем новую платформу

Вот главный вопрос: **нужна ли новая ветка для новой платформы?**

#### Сценарий 1: NTC Templates справляется (формат как у Cisco)

Если новая платформа (например Eltex) парсится через NTC Templates с маппингом
на `cisco_ios`, и NTC возвращает поле `admin_mode`:

```python
# NTC вернёт данные в формате Cisco IOS:
{"interface": "Gi0/1", "admin_mode": "static access", "trunking_vlans": ["ALL"], ...}
```

→ Попадёт в **ветку 1 (Cisco)**. Всё работает **без изменений кода**.

**Что нужно:** только добавить команду в `SECONDARY_COMMANDS["switchport"]`.

#### Сценарий 2: Формат как у NX-OS

Если новая платформа возвращает `mode` + `trunking_vlans`, но **не** `admin_mode`:

```python
{"interface": "Eth1/1", "mode": "trunk", "trunking_vlans": "10-20", ...}
```

→ Попадёт в **ветку 2 (NX-OS)**. Работает **если формат значений совпадает**.

**Что нужно:** добавить команду + проверить что значения `mode` содержат `"trunk"` или `"access"`.

#### Сценарий 3: Нужен кастомный шаблон (уникальный формат)

Если платформа возвращает данные в своём формате (как QTech), есть три подварианта:

**3a. Шаблон возвращает стандартные поля:**

Если ваш кастомный шаблон возвращает поля с теми же именами (`admin_mode`, `mode`,
`trunking_vlans`) — данные попадут в существующую ветку автоматически.

```python
# Кастомный шаблон для Eltex возвращает:
{"interface": "Gi0/1", "admin_mode": "trunk", "trunking_vlans": "10,20", ...}
# → Попадёт в ветку 1 (Cisco) — всё работает!
```

**3b. Шаблон возвращает поля QTech-формата:**

Если шаблон возвращает `switchport=enabled` + `mode` (uppercase) + `vlan_lists`:

```python
{"interface": "Gi0/1", "switchport": "enabled", "mode": "TRUNK", "vlan_lists": "ALL"}
# → Попадёт в ветку 3 (QTech) — работает если значения совпадают
```

**3c. Шаблон возвращает УНИКАЛЬНЫЕ поля (НИ ОДНА ветка не подходит):**

```python
# Гипотетический Huawei шаблон:
{"interface": "GE0/0/1", "port_link_type": "trunk", "permit_vlan": "10 20 30"}
# admin_mode нет → ветка 1 пропущена
# trunking_vlans нет → ветка 2 пропущена
# switchport нет → ветка 3 пропущена
# → mode = "" (ПУСТОЙ!) — данные потеряны!
```

**В этом случае нужно:**
1. Либо переименовать поля в шаблоне под существующий формат
2. Либо добавить **новую ветку** в `normalize_switchport_data()`

### Таблица: что делать для новой платформы

| Формат данных | Попадёт в ветку | Нужна новая ветка? | Что делать |
|---------------|----------------|--------------------|-----------|
| Есть `admin_mode` (как Cisco IOS) | Ветка 1 (Cisco) | Нет | Добавить команду в `SECONDARY_COMMANDS` |
| Есть `mode` + `trunking_vlans`, нет `admin_mode` (как NX-OS) | Ветка 2 (NX-OS) | Нет | Добавить команду + проверить формат значений |
| Есть `switchport=enabled` + `mode` uppercase (как QTech) | Ветка 3 (QTech) | Нет | Добавить команду + кастомный шаблон |
| Совсем другие поля | Никуда | **Да** | Кастомный шаблон + новая ветка + тесты |

### Ловушка: платформа может попасть в ЧУЖУЮ ветку

Это **главный риск** текущей архитектуры. Примеры:

**Ловушка 1:** Новая платформа случайно имеет `admin_mode`

```python
# Если NTC для нового вендора тоже возвращает admin_mode:
{"admin_mode": "trunk-mode", "mode": "trunk", ...}
# → Ветка 1 (Cisco) сработает
# → "access" in "trunk-mode" → False
# → "trunk" in "trunk-mode" → True → ОК в данном случае
# НО если admin_mode = "layer2-access" → "access" in "layer2-access" → True
# а "trunk" in "layer2-access" → False → будет "access" хотя это может быть trunk!
```

**Ловушка 2:** NX-OS и новая платформа пересекаются

```python
# Новая платформа имеет mode + trunking_vlans:
{"mode": "hybrid", "trunking_vlans": "10-20", ...}
# → Ветка 2 (NX-OS) сработает
# → "trunk" in "hybrid" → False
# → "access" in "hybrid" → False
# → mode = "" (ПУСТОЙ!) — hybrid не обработан!
```

**Ловушка 3:** QTech ветка слишком широкая

```python
# Любая платформа с switchport=enabled попадёт в QTech ветку
# если у неё НЕТ admin_mode и trunking_vlans
{"switchport": "enabled", "mode": "routed", ...}
# → Ветка 3 (QTech) сработает
# → "ROUTED".upper() не равно "ACCESS", "TRUNK", "HYBRID"
# → mode = "" (пустой)
```

### Как безопасно добавить новую платформу

**Шаг 1.** Соберите сырой вывод:
```bash
python -m network_collector run "show interface switchport" --format raw > raw_switchport.txt
```

**Шаг 2.** Посмотрите что вернёт парсинг:
```bash
python -m network_collector interfaces --format parsed > parsed.json
```

**Шаг 3.** Проверьте какие поля вернул TextFSM. Сравните с таблицей выше.

**Шаг 4.** Определите в какую ветку попадут данные:
- Есть `admin_mode`? → Ветка 1. Проверьте что значения `access`/`trunk` совпадают.
- Есть `trunking_vlans` + `mode`? → Ветка 2. Проверьте что mode содержит `trunk`/`access`.
- Есть `switchport=enabled`? → Ветка 3. Проверьте что mode = `ACCESS`/`TRUNK`/`HYBRID`.
- Ничего не подходит? → Нужна новая ветка.

**Шаг 5.** Если нужна новая ветка — добавьте её **перед** QTech веткой (QTech должна быть последней, т.к. `switchport=enabled` — слишком общее условие):

```python
if admin_mode:                                              # Cisco IOS/Arista
    ...
elif row.get("trunking_vlans") is not None and row.get("mode"):  # NX-OS
    ...
elif row.get("port_link_type"):                             # ← НОВАЯ ВЕТКА (Huawei)
    # Уникальное поле port_link_type есть только у Huawei
    huawei_mode = row.get("port_link_type", "").lower()
    if huawei_mode == "access":
        netbox_mode = "access"
    elif huawei_mode == "trunk":
        ...
elif switchport == "enabled":                               # QTech (последняя!)
    ...
```

**Шаг 6.** Добавьте тесты в `tests/test_collectors/test_switchport_mode.py`:

```python
def test_new_platform_switchport_mode(normalizer):
    """Новая платформа: проверяем что данные попадают в правильную ветку."""
    parsed = [{
        "interface": "GE0/0/1",
        "port_link_type": "trunk",
        "permit_vlan": "10 20 30",
    }]
    result = normalizer.normalize_switchport_data(parsed, "huawei")
    assert result["GE0/0/1"]["mode"] == "tagged"
```

### Почему не проверяется platform напрямую?

Текущий код определяет платформу по полям, а не по параметру `platform`. Это было
осознанное решение:

**Плюсы duck typing (по полям):**
- Новая платформа с тем же форматом данных работает автоматически
- Не нужно обновлять список платформ при добавлении `cisco_iosxe`, `arista_eos` и т.д.
- Если NTC-шаблон для нового вендора возвращает `admin_mode` — всё работает

**Минусы duck typing:**
- Платформа может попасть в чужую ветку (ловушки выше)
- Неочевидно какая ветка сработает — нужно знать какие поля вернёт шаблон
- Нет `else` ветки — если ничего не подошло, ошибка молча проглатывается

**Альтернатива — явная проверка `platform`:**

```python
# Явный вариант (НЕ используется в проекте):
if platform in ("cisco_ios", "cisco_iosxe", "arista_eos"):
    # Cisco IOS формат
elif platform == "cisco_nxos":
    # NX-OS формат
elif platform in ("qtech", "qtech_qsw"):
    # QTech формат
else:
    logger.warning(f"Неизвестная платформа: {platform}")
```

Явная проверка надёжнее, но требует обновления кода при каждой новой платформе.
Текущий подход (по полям) — компромисс: работает для большинства случаев,
но при добавлении экзотической платформы нужно проверить ветвление.

### Итог: чеклист для новой платформы

- [ ] Добавить команду в `SECONDARY_COMMANDS["switchport"]` (`core/constants/commands.py`)
- [ ] Если формат не как у Cisco — создать кастомный TextFSM шаблон в `templates/`
- [ ] Зарегистрировать шаблон в `CUSTOM_TEXTFSM_TEMPLATES`
- [ ] Запустить `--format parsed` и проверить какие поля возвращает парсер
- [ ] Проверить в какую ветку попадают данные (таблица выше)
- [ ] Если ни одна ветка не подходит — добавить новую ветку **перед** QTech
- [ ] Написать тесты для новой платформы в `test_switchport_mode.py`
- [ ] Проверить что старые тесты не сломались: `pytest tests/ -v`

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
