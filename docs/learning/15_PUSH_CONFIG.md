# 15. Push Config: от YAML-файла до конфигурации устройства

Этот документ описывает **полную цепочку** команды `push-config`: от YAML-файла с командами через маппинг платформ до применения конфигурации на устройствах через Netmiko.

Если ты уже прочитал [03_CLI_INTERNALS.md](03_CLI_INTERNALS.md), ты знаешь как работает CLI. Здесь мы разберём конкретный flow — конфигурирование устройств по платформам.

---

## Содержание

1. [Зачем это нужно](#1-зачем-это-нужно)
2. [Общая схема](#2-общая-схема)
3. [YAML-файл с командами](#3-yaml-файл-с-командами)
4. [CLI: парсинг аргументов](#4-cli-парсинг-аргументов)
5. [Загрузка устройств](#5-загрузка-устройств)
6. [Загрузка и валидация YAML](#6-загрузка-и-валидация-yaml)
7. [Маппинг команд по платформам](#7-маппинг-команд-по-платформам)
8. [Dry-run vs Apply](#8-dry-run-vs-apply)
9. [ConfigPusher: подключение и отправка](#9-configpusher-подключение-и-отправка)
10. [Маппинг платформ для Netmiko](#10-маппинг-платформ-для-netmiko)
11. [Retry логика](#11-retry-логика)
12. [Тестирование](#12-тестирование)
13. [Сравнение с push-descriptions](#13-сравнение-с-push-descriptions)
14. [Диаграмма полного потока](#14-диаграмма-полного-потока)

---

## 1. Зачем это нужно

Представь: у тебя 50 коммутаторов — Cisco IOS-XE, NX-OS и QTech. Нужно на всех включить `spanning-tree portfast` на access-портах. Проблема:

- Команды **разные** для каждой платформы
- Подключаться к каждому вручную долго
- Хочется сначала **посмотреть** что будет сделано, а потом применить

`push-config` решает это:

```bash
# 1. Описываем команды в YAML (один раз)
# 2. Проверяем (dry-run)
python -m network_collector push-config --commands config_commands.yaml

# 3. Применяем
python -m network_collector push-config --commands config_commands.yaml --apply
```

---

## 2. Общая схема

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│  config_commands.yaml│     │    devices_ips.py     │     │   Credentials       │
│                     │     │                      │     │  (username/password) │
│  _common:           │     │  devices_list = [    │     └──────────┬──────────┘
│    config:          │     │    {device_type:     │                │
│      - logging ...  │     │     "cisco_iosxe",  │                │
│    exec:            │     │     host: "10.0.0.1"}│                │
│      - show clock   │     │  ]                   │                │
│  cisco_iosxe:       │     │                      │                │
│    config:          │     └──────────┬───────────┘                │
│      - spanning-tree│                │                            │
│    exec:            │                │                            │
│      - show version │                │                            │
└────────┬────────────┘                │                            │
         │                             │                            │
         ▼                             ▼                            │
┌─────────────────────────────────────────────────┐                │
│              cmd_push_config()                   │                │
│                                                 │                │
│  1. _load_commands_yaml()                       │                │
│     → {platform: {"config": [...], "exec": []}} │                │
│  2. load_devices() → [Device, Device...]        │                │
│  3. _build_device_commands() для каждого        │                │
│  4. dry-run? → показать превью и выйти          │                │
│  5. --apply? → создать ConfigPusher             │◄───────────────┘
└────────┬────────────────────────────────────────┘
         │ apply
         ▼
┌─────────────────────────────────────────────────┐
│              ConfigPusher                        │
│                                                 │
│  Для каждого устройства:                        │
│  1. NETMIKO_PLATFORM_MAP[platform] → device_type│
│  2. ConnectHandler(**params)                    │
│  3. conn.enable() (если есть secret)            │
│  4. conn.send_config_set(config_cmds)           │
│  5. conn.send_command(exec_cmd) для каждой      │
│  6. conn.save_config() (если не --no-save)      │
│  7. При ошибке → retry (до max_retries раз)     │
│                                                 │
│  Возвращает: ConfigResult(success, device, ...) │
└─────────────────────────────────────────────────┘
```

---

## 3. YAML-файл с командами

Файл `config_commands.yaml` — это словарь, где каждый ключ (платформа или `_common`) содержит подсекции `config:` и `exec:`.

### Рекомендуемый формат (unified/nested)

```yaml
# Общие команды для ВСЕХ платформ
# config: выполняются в config mode ПЕРЕД платформенными
# exec: выполняются в exec mode ПЕРЕД платформенными
_common:
  config:
    - logging buffered 16384
    - no ip domain-lookup
  exec:
    - show running-config | include logging

# Ключи = значения device.platform
cisco_iosxe:
  config:
    - interface range GigabitEthernet0/1 - 48
    - spanning-tree portfast
    - no shutdown
  exec:
    - show version

cisco_nxos:
  config:
    - interface Ethernet1/1-48
    - spanning-tree port type edge

arista_eos:
  config:
    - interface Ethernet1
    - spanning-tree portfast

qtech:
  config:
    - spanning-tree portfast
  exec:
    - copy running-config startup-config
```

### Правила YAML-файла

| Правило | Пример |
|---------|--------|
| Ключи верхнего уровня — имена платформ | `cisco_iosxe`, `cisco_nxos`, `arista_eos` |
| Подсекции — `config:` и `exec:` | Оба опциональны внутри платформы |
| Значения подсекций — списки строк | `- spanning-tree portfast` |
| `_common` — зарезервировано | Общие команды для всех платформ |
| Порядок config | `_common.config` → `{platform}.config` |
| Порядок exec | `_common.exec` → `{platform}.exec` |
| Порядок выполнения | config → exec → save |
| Пустые секции | Можно опустить `config:` или `exec:` |

### Какие ключи использовать?

Ключи YAML должны совпадать со значением `device.platform` из `devices_ips.py`:

| В devices_ips.py | device.platform | Ключ в YAML |
|-----------------|----------------|-------------|
| `device_type: "cisco_iosxe"` | `cisco_iosxe` | `cisco_iosxe:` |
| `device_type: "cisco_ios"` | `cisco_ios` | `cisco_ios:` |
| `platform: "cisco_nxos"` | `cisco_nxos` | `cisco_nxos:` |
| `device_type: "arista_eos"` | `arista_eos` | `arista_eos:` |
| `device_type: "qtech"` | `qtech` | `qtech:` |

---

## 4. CLI: парсинг аргументов

Команда зарегистрирована в `cli/__init__.py` как subparser:

```python
# cli/__init__.py
push_config_parser = subparsers.add_parser("push-config", ...)
push_config_parser.add_argument("--commands", required=True, ...)
push_config_parser.add_argument("--platform", ...)
push_config_parser.add_argument("--apply", action="store_true", ...)
push_config_parser.add_argument("--no-save", action="store_true", ...)
```

И маршрутизируется в `main()`:

```python
elif args.command == "push-config":
    cmd_push_config(args, ctx)
```

Все аргументы:

| Аргумент | Обязательный | По умолчанию | Описание |
|----------|:------------:|:------------:|----------|
| `--commands FILE` | да | — | YAML-файл с командами |
| `--platform NAME` | нет | все | Фильтр по платформе |
| `--apply` | нет | dry-run | Реально применить |
| `--no-save` | нет | сохранять | Не делать write memory |
| `-d FILE` | нет | devices_ips.py | Файл со списком устройств |

---

## 5. Загрузка устройств

Устройства загружаются из `devices_ips.py` через `load_devices()` (`cli/utils.py`):

```python
# cli/utils.py
devices = load_devices(args.devices)
```

Формат `devices_ips.py`:

```python
devices_list = [
    {"platform": "cisco_iosxe", "device_type": "C9200L-24P-4X", "host": "192.168.1.1"},
    {"platform": "cisco_nxos",  "host": "192.168.2.1"},
    {"platform": "qtech",      "host": "192.168.4.1"},
]
```

Поле `device.platform` используется для маппинга команд из YAML.

---

## 6. Загрузка и валидация YAML

Функция `_load_commands_yaml()` (`cli/commands/push.py`) загружает YAML и парсит в внутреннюю структуру.

### Внутренняя структура

```python
Dict[str, Dict[str, List[str]]]
# {platform: {"config": [...], "exec": [...]}}
```

Пример:

```python
{
    "_common": {"config": ["logging buffered 16384"], "exec": ["show clock"]},
    "cisco_iosxe": {"config": ["spanning-tree portfast"], "exec": ["show version"]},
    "qtech": {"config": ["spanning-tree portfast"], "exec": ["copy running-config startup-config"]},
}
```

### Код загрузки

```python
def _load_commands_yaml(filepath: str) -> Dict[str, Dict[str, List[str]]]:
    import yaml

    path = Path(filepath)

    # Ищем файл в директории модуля если не найден
    if not path.exists():
        module_dir = Path(__file__).parent.parent.parent
        path = module_dir / filepath

    # Парсим YAML
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Валидация: должен быть dict
    if not isinstance(data, dict):
        sys.exit(1)

    # Парсинг: каждая секция — dict с ключами config/exec
    result = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            sys.exit(1)  # Секция должна быть dict

        section = {}
        for sub_key in ("config", "exec"):
            if sub_key in value:
                section[sub_key] = [str(cmd) for cmd in value[sub_key]]

        # Проверяем неизвестные ключи
        unknown = set(value.keys()) - {"config", "exec"}
        if unknown:
            sys.exit(1)

        if not section:
            sys.exit(1)  # Пустая секция

        result[key] = section

    return result
```

### Пример парсинга

```yaml
# Вход:
_common:
  config:
    - logging buffered 16384
  exec:
    - show clock
cisco_iosxe:
  config:
    - spanning-tree portfast
  exec:
    - show version
```

```python
# Результат:
{
    "_common": {"config": ["logging buffered 16384"], "exec": ["show clock"]},
    "cisco_iosxe": {"config": ["spanning-tree portfast"], "exec": ["show version"]},
}
```

### Что проверяется

| Проверка | Ошибка |
|----------|--------|
| Файл не найден | `sys.exit(1)` |
| Невалидный YAML | `sys.exit(1)` |
| Пустой файл | `sys.exit(1)` |
| Не словарь (список) | `sys.exit(1)` |
| Числа в командах | Конвертируются в строки |

---

## 7. Маппинг команд по платформам

Функция `_build_device_commands()` собирает итоговые команды для устройства. После нормализации в `_load_commands_yaml()` логика стала простой — просто мержим словари `_common` и `{platform}`:

```python
def _build_device_commands(commands_data, platform):
    common = commands_data.get("_common", {})
    platform_data = commands_data.get(platform, {})

    config_cmds = common.get("config", []) + platform_data.get("config", [])
    exec_cmds = common.get("exec", []) + platform_data.get("exec", [])

    return config_cmds, exec_cmds
```

### Порядок выполнения команд

```
1. _common.config     → config mode (conf t → команды → end)
2. {platform}.config  → config mode (продолжение)
3. _common.exec       → exec/privileged mode (send_command)
4. {platform}.exec    → exec/privileged mode (send_command)
5. save_config()      → write memory (если не --no-save)
```

### Примеры маппинга

```
Устройство: platform="cisco_iosxe"
YAML (нормализованный):
  _common: {"config": ["logging buffered 16384"], "exec": ["show clock"]}
  cisco_iosxe: {"config": ["spanning-tree portfast"], "exec": ["show version"]}

config_cmds = ["logging buffered 16384", "spanning-tree portfast"]
exec_cmds   = ["show clock", "show version"]
```

```
Устройство: platform="juniper_junos"
YAML: _common есть, juniper_junos отсутствует

config_cmds = ["logging buffered 16384"]  ← только _common.config
exec_cmds   = ["show clock"]              ← только _common.exec
```

```
Устройство: platform="unknown"
YAML: нет _common, нет unknown

config_cmds = []  ← пустой
exec_cmds   = []  ← пустой, устройство пропускается с warning
```

### Фильтр по платформе

Если указан `--platform`, применяется фильтр:

```python
if platform_filter:
    devices = [d for d in devices if d.platform == platform_filter]
```

Это позволяет применить команды только на часть устройств:

```bash
# Только на Cisco IOS-XE
python -m network_collector push-config --commands cmds.yaml --platform cisco_iosxe --apply

# Только на NX-OS
python -m network_collector push-config --commands cmds.yaml --platform cisco_nxos --apply
```

---

## 8. Dry-run vs Apply

По умолчанию команда работает в режиме **dry-run** — только показывает что будет сделано:

```
$ python -m network_collector push-config --commands config_commands.yaml

Загружены команды для платформ: cisco_iosxe, cisco_nxos
Общие команды (_common): config: 2, exec: 1
Загружено устройств: 3
Устройств: 3, команд всего: 15

=== DRY RUN (команды не будут применены) ===

  192.168.1.1 (192.168.1.1) [cisco_iosxe]:
    [config mode]:
      logging buffered 16384
      no ip domain-lookup
      spanning-tree portfast
    [exec mode]:
      show clock
      show version

Для применения используйте флаг --apply
```

С `--apply` — реально подключается и отправляет:

```
$ python -m network_collector push-config --commands config_commands.yaml --apply

Подключение к 192.168.1.1...
192.168.1.1: применено 3 config + 2 exec команд
Подключение к 192.168.1.2...
192.168.1.2: применено 3 config + 1 exec команд

=== РЕЗУЛЬТАТЫ ===
Устройств: 2
Успешно: 2
Ошибки: 0
Команд отправлено: 9
Конфигурация сохранена на устройствах
```

**Почему dry-run по умолчанию?** Безопасность. Конфигурация сетевого оборудования — необратимое действие. Лучше сначала посмотреть.

---

## 9. ConfigPusher: подключение и отправка

`ConfigPusher` (`configurator/base.py`) — класс, который непосредственно подключается к устройству и отправляет команды. Использует **Netmiko** (не Scrapli!).

### Почему Netmiko, а не Scrapli?

В проекте два SSH-инструмента:

| Инструмент | Где используется | Почему |
|-----------|-----------------|--------|
| **Scrapli** | Сбор данных (show-команды) | Быстрый, хорошо парсит вывод |
| **Netmiko** | Конфигурация (config-команды) | Проверен годами для config mode |

### Как работает push_config()

```python
# configurator/base.py
def push_config(self, device, config_commands, exec_commands, dry_run=True):
    # 1. Формируем параметры Netmiko
    params = self._build_connection_params(device)

    # 2. Подключаемся
    with ConnectHandler(**params) as conn:
        # 3. Enable mode (если есть secret)
        if self.credentials.secret:
            conn.enable()

        # 4. Config-команды (входит в config mode автоматически)
        if config_commands:
            output = conn.send_config_set(config_commands)

        # 5. Exec-команды (в privileged mode)
        if exec_commands:
            for cmd in exec_commands:
                conn.send_command(cmd)

        # 6. Сохраняем (write memory / copy run start)
        if self.save_config:
            conn.save_config()

    # 7. Возвращаем результат
    return ConfigResult(success=True, device=device.host, ...)
```

### send_config_set — что делает Netmiko

Когда ты передаёшь `conn.send_config_set(config_commands)`, Netmiko автоматически:

```
1. Вводит "configure terminal"
2. Отправляет каждую команду по очереди
3. Ждёт промпт после каждой
4. Вводит "end"
```

Т.е. для команд `["interface Gi0/1", "shutdown"]` на устройство уйдёт:

```
switch# configure terminal
switch(config)# interface Gi0/1
switch(config-if)# shutdown
switch(config-if)# end
switch#
```

### exec-команды — send_command

Exec-команды выполняются **после** config mode, в privileged mode:

```
switch# show version          ← exec-команда из _common.exec
switch# show clock            ← exec-команда из {platform}.exec
```

Это полезно для:
- Проверочных команд (`show running-config | include ...`)
- Сохранения на платформах, где `save_config()` не работает
- Диагностики после применения конфигурации

### ConfigResult — что возвращается

```python
@dataclass
class ConfigResult:
    success: bool          # True/False
    device: str            # IP устройства
    commands_sent: int     # Количество отправленных команд
    output: str = ""       # Вывод устройства
    error: str = ""        # Текст ошибки (если success=False)
```

---

## 10. Маппинг платформ для Netmiko

Важный нюанс: Netmiko **не знает** `cisco_iosxe`. Для него есть только `cisco_ios`.

Маппинг в `core/constants/platforms.py`:

```python
NETMIKO_PLATFORM_MAP = {
    "cisco_iosxe": "cisco_ios",    # ← IOS-XE → IOS для Netmiko
    "cisco_ios":   "cisco_ios",
    "cisco_nxos":  "cisco_nxos",
    "cisco_iosxr": "cisco_xr",
    "arista_eos":  "arista_eos",
    "juniper_junos": "juniper_junos",
    "qtech":       "cisco_ios",    # ← QTech как Cisco IOS
    "qtech_qsw":   "cisco_ios",
}
```

Используется в `ConfigPusher._build_connection_params()`:

```python
def _build_connection_params(self, device):
    netmiko_device_type = NETMIKO_PLATFORM_MAP.get(
        device.platform, device.platform
    )
    params = {
        "device_type": netmiko_device_type,  # ← cisco_ios, а не cisco_iosxe
        "host": device.host,
        ...
    }
```

### Полная цепочка маппинга (пример)

```
devices_ips.py        Device.__post_init__     YAML                 Netmiko
──────────────        ────────────────────     ────                 ───────
device_type:       →  platform:             →  секция:           →  device_type:
"cisco_iosxe"         "cisco_iosxe"            "cisco_iosxe:"       "cisco_ios"
                                                    │
                                               config:
                                               ["spanning-tree
                                                 portfast"]
                                               exec:
                                               ["show version"]
```

### Три маппинга в проекте

В проекте три маппинга платформ — каждый для своей библиотеки:

```
device.platform = "cisco_iosxe"
        │
        ├── SCRAPLI_PLATFORM_MAP["cisco_iosxe"]  → "cisco_iosxe"   (сбор данных)
        ├── NTC_PLATFORM_MAP["cisco_iosxe"]      → "cisco_ios"     (TextFSM парсинг)
        └── NETMIKO_PLATFORM_MAP["cisco_iosxe"]  → "cisco_ios"     (конфигурация) ← используется тут
```

---

## 11. Retry логика

Если подключение не удалось — ConfigPusher повторяет попытку:

```python
# configurator/base.py
total_attempts = 1 + self.max_retries  # По умолчанию: 1 + 2 = 3

for attempt in range(1, total_attempts + 1):
    try:
        with ConnectHandler(**params) as conn:
            output = conn.send_config_set(commands)
            return ConfigResult(success=True, ...)

    except NetmikoAuthenticationException:
        # Ошибка логина — НЕ повторяем (бесполезно)
        return ConfigResult(success=False, error="Ошибка аутентификации")

    except NetmikoTimeoutException:
        # Таймаут — повторяем
        time.sleep(self.retry_delay)  # По умолчанию 5 сек

    except Exception:
        # Другие ошибки — повторяем
        time.sleep(self.retry_delay)
```

### Таблица поведения

| Ошибка | Retry? | Почему |
|--------|:------:|--------|
| Таймаут | Да | Может быть временный сбой сети |
| Auth error | Нет | Пароль не изменится от повтора |
| Connection refused | Да | Устройство могло перезагружаться |
| Любая другая | Да | На всякий случай |

---

## 12. Тестирование

Тесты в `tests/test_configurator/test_push_config.py` — 25 тестов в 4 группах:

### Группа 1: Загрузка YAML (9 тестов)

```python
class TestLoadCommandsYaml:
    def test_load_valid_yaml(self, yaml_file):
        """Загрузка корректного YAML → нормализованная структура."""
        data = _load_commands_yaml(yaml_file)
        assert "_common" in data
        assert "cisco_iosxe" in data
        # Каждый ключ — dict с "config" и "exec"
        assert "config" in data["_common"]
        assert "exec" in data["_common"]

    def test_file_not_found(self):
        """Несуществующий файл → SystemExit."""
        with pytest.raises(SystemExit):
            _load_commands_yaml("/nonexistent/commands.yaml")

```

Используем `tmp_path` fixture из pytest для создания временных YAML-файлов:

```python
@pytest.fixture
def yaml_file(tmp_path):
    """YAML с config и exec командами."""
    content = """
_common:
  config:
    - logging buffered 16384
  exec:
    - show clock
cisco_iosxe:
  config:
    - spanning-tree portfast
  exec:
    - show version
"""
    filepath = tmp_path / "test_commands.yaml"
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)
```

### Группа 2: Маппинг команд (11 тестов)

```python
class TestBuildDeviceCommands:
    def test_common_plus_platform(self, yaml_file):
        """Общие + платформенные команды (config и exec отдельно)."""
        data = _load_commands_yaml(yaml_file)
        config_cmds, exec_cmds = _build_device_commands(data, "cisco_iosxe")

        # config: _common.config + cisco_iosxe.config
        assert config_cmds[0] == "logging buffered 16384"
        assert "spanning-tree portfast" in config_cmds

        # exec: _common.exec + cisco_iosxe.exec
        assert exec_cmds[0] == "show clock"
        assert "show version" in exec_cmds
```

### Группа 3: Backward compatibility device_type → platform (4 теста)

```python
class TestBackwardCompatibility:
    def test_commands_match_regardless_of_format(self, yaml_file):
        """Device с device_type и platform дают одинаковые команды."""
        data = _load_commands_yaml(yaml_file)

        device_new = Device(host="10.0.0.1", platform="cisco_iosxe")
        device_old = Device(host="10.0.0.2", device_type="cisco_iosxe")

        assert _build_device_commands(data, device_new.platform) == \
               _build_device_commands(data, device_old.platform)
```

### Группа 4: Интеграция cmd_push_config (9 тестов)

```python
class TestCmdPushConfig:
    @patch("network_collector.configurator.base.ConnectHandler")
    @patch("network_collector.cli.commands.push.load_devices")
    def test_apply_calls_pusher(self, mock_load, mock_conn, ...):
        """--apply вызывает ConfigPusher и send_config_set."""
        mock_load.return_value = [device]
        mock_conn.return_value.__enter__.return_value.send_config_set.return_value = "OK"

        args = self._make_args(yaml_file, apply=True)
        cmd_push_config(args)

        # Проверяем что Netmiko вызван
        mock_conn.return_value.__enter__.return_value.send_config_set.assert_called_once()
```

### Запуск тестов

```bash
# Только push-config
pytest tests/test_configurator/test_push_config.py -v

# Все configurator тесты (push-config + retry)
pytest tests/test_configurator/ -v
```

---

## 13. Сравнение с push-descriptions

В проекте есть две push-команды. Вот чем они отличаются:

| Параметр | push-descriptions | push-config |
|----------|:-----------------:|:-----------:|
| **Источник команд** | Excel файл (matched.xlsx) | YAML файл |
| **Группировка** | По устройству (IP) | По платформе |
| **Команды** | Генерируются автоматически | Пишутся вручную |
| **Типовое применение** | Описания интерфейсов | Любая конфигурация |
| **Класс** | DescriptionPusher | ConfigPusher |
| **Зависимости** | pandas, match-mac | yaml (stdlib) |

### Общее

Обе команды используют:
- `ConfigPusher` как базовый класс (DescriptionPusher наследует его)
- Netmiko для SSH
- `NETMIKO_PLATFORM_MAP` для маппинга платформ
- dry-run / --apply паттерн
- Retry логику при ошибках подключения

---

## 14. Диаграмма полного потока

```
Пользователь
     │
     │  python -m network_collector push-config
     │      --commands config_commands.yaml
     │      --platform cisco_iosxe
     │      --apply
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│  CLI: cli/__init__.py                                    │
│                                                          │
│  1. setup_parser() → subparser "push-config"             │
│  2. args.command == "push-config"                        │
│  3. cmd_push_config(args, ctx)                           │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  cmd_push_config(): cli/commands/push.py                 │
│                                                          │
│  Шаг 1: _load_commands_yaml("config_commands.yaml")      │
│          → yaml.safe_load() → нормализация               │
│          → {"_common": {"config": [...], "exec": [...]}, │
│             "cisco_iosxe": {"config": [...], "exec": []}}│
│                                                          │
│  Шаг 2: load_devices("devices_ips.py")                   │
│          → importlib загрузка → Device.__post_init__     │
│          → [Device(platform="cisco_iosxe", host=...)]    │
│                                                          │
│  Шаг 3: Фильтр --platform cisco_iosxe                   │
│          → оставляем только matching устройства          │
│                                                          │
│  Шаг 4: _build_device_commands() для каждого устройства  │
│          → common.config + platform.config = config_cmds │
│          → common.exec + platform.exec = exec_cmds       │
│                                                          │
│  Шаг 5: --apply → создаём ConfigPusher                   │
│          credentials = get_credentials() (ввод с клавиш.)│
│          pusher = ConfigPusher(credentials)               │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼  (для каждого устройства)
┌──────────────────────────────────────────────────────────┐
│  ConfigPusher.push_config(): configurator/base.py        │
│                                                          │
│  Шаг 6: _build_connection_params(device)                 │
│          NETMIKO_PLATFORM_MAP["cisco_iosxe"] → "cisco_ios"│
│          params = {device_type: "cisco_ios", host: ...}  │
│                                                          │
│  Шаг 7: ConnectHandler(**params) — Netmiko SSH           │
│          → SSH подключение к устройству                  │
│                                                          │
│  Шаг 8: conn.enable() — если есть secret                 │
│          → переход в privileged mode                     │
│                                                          │
│  Шаг 9: conn.send_config_set(config_cmds)                │
│          → conf t → config-команды → end                 │
│                                                          │
│  Шаг 10: conn.send_command(exec_cmd) для каждой          │
│           → exec-команды в privileged mode               │
│                                                          │
│  Шаг 11: conn.save_config() — если не --no-save          │
│           → write memory / copy running-config           │
│                                                          │
│  → ConfigResult(success=True, commands_sent=5)           │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼  (ошибка подключения?)
┌──────────────────────────────────────────────────────────┐
│  Retry логика                                            │
│                                                          │
│  Timeout/ConnectionError → sleep(5) → повтор (до 3 раз) │
│  AuthenticationError → сразу fail (не повторяем)         │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Результат                                               │
│                                                          │
│  === РЕЗУЛЬТАТЫ ===                                      │
│  Устройств: 3                                            │
│  Успешно: 2                                              │
│  Ошибки: 1                                               │
│  Команд отправлено: 10                                   │
│  Конфигурация сохранена на устройствах                   │
│                                                          │
│  192.168.3.1: Таймаут подключения (исчерпаны 3 попытки) │
└──────────────────────────────────────────────────────────┘
```

---

## Связанные файлы

| Файл | Роль |
|------|------|
| `config_commands.yaml` | YAML с командами по платформам (nested формат) |
| `devices_ips.py` | Список устройств |
| `cli/commands/push.py` | CLI-обработчик: `cmd_push_config()`, `_load_commands_yaml()`, `_build_device_commands()` |
| `cli/__init__.py` | Парсер аргументов, маршрутизация |
| `configurator/base.py` | `ConfigPusher` — SSH подключение, отправка, retry |
| `core/device.py` | `Device.__post_init__()` — маппинг device_type → platform |
| `core/constants/platforms.py` | `NETMIKO_PLATFORM_MAP` — маппинг платформ |
| `core/credentials.py` | Запрос логина/пароля |
| `tests/test_configurator/test_push_config.py` | 25 тестов |

## Связанная документация

| Документ | Что дополняет |
|----------|--------------|
| [MANUAL.md](../MANUAL.md) — раздел 3.11 | Полное описание команды и опций |
| [03_CLI_INTERNALS.md](03_CLI_INTERNALS.md) | Как работает CLI в целом |
| [DEVELOPMENT.md](../DEVELOPMENT.md) — раздел 2.6 | Тесты retry и push-config |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Слои системы, Presentation Layer |
