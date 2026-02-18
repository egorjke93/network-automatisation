# 10. Collectors Deep Dive: от CLI до экспорта

Этот документ проводит тебя через **полную цепочку выполнения** при сборе данных: от ввода команды в терминале до готового Excel-файла. На каждом шаге -- реальный код из проекта и объяснение, что именно происходит.

Если ты уже прочитал [04_DATA_COLLECTION.md](04_DATA_COLLECTION.md), здесь ты увидишь те же концепции, но на уровне строк кода.

---

## Содержание

1. [CLI -> Collector](#1-cli--collector)
2. [BaseCollector](#2-basecollector)
3. [ConnectionManager](#3-connectionmanager)
4. [NTCParser (TextFSM)](#4-ntcparser-textfsm)
5. [InterfaceCollector](#5-interfacecollector)
6. [InterfaceNormalizer](#6-interfacenormalizer)
7. [Другие нормализаторы](#7-другие-нормализаторы)
8. [Каждый коллектор в деталях](#8-каждый-коллектор-в-деталях)
9. [Exporters](#9-exporters)
10. [Диаграмма потока данных](#10-диаграмма-потока-данных)

---

## 1. CLI -> Collector

Когда ты вводишь в терминале:

```bash
python -m network_collector interfaces --format excel
```

управление попадает в обработчик команды `cmd_interfaces`.

### Файл: cli/commands/collect.py (строки ~216-252)

```python
def cmd_interfaces(args, ctx=None) -> None:
    """Обработчик команды interfaces."""
    from ...collectors import InterfaceCollector
    from ...fields_config import apply_fields_config

    devices, credentials = prepare_collection(args)

    fields = args.fields.split(",") if args.fields else None

    collector = InterfaceCollector(
        credentials=credentials,
        ntc_fields=fields,
        transport=args.transport,
    )

    # --format parsed: пропускаем нормализацию
    if args.format == "parsed":
        collector._skip_normalize = True

    data = collector.collect_dicts(devices)

    if not data:
        logger.warning("Нет данных для экспорта")
        return

    # --format parsed: сырые данные TextFSM, без fields.yaml
    if args.format == "parsed":
        _export_parsed(data, "interfaces_parsed")
        return

    data = apply_fields_config(data, "interfaces")

    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "interfaces")

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

### Что здесь происходит

Всё начинается с `prepare_collection(args)` -- эта функция загружает список устройств из файла `devices_ips.py` и получает credentials (логин/пароль).

### Файл: cli/utils.py (строки ~148-161)

```python
def prepare_collection(args) -> Tuple[List, object]:
    """Подготавливает устройства и credentials для сбора данных."""
    devices = load_devices(args.devices)
    credentials = get_credentials()
    return devices, credentials
```

`load_devices()` читает Python-файл (`devices_ips.py`), находит переменную `devices_list` и превращает каждый dict в объект `Device`:

```python
devices.append(
    Device(
        host=host,
        platform=platform,         # "cisco_iosxe", "qtech", etc.
        device_type=device_type,   # "C9200L-24P-4X"
        role=role,                 # "Switch"
        site=d.get("site"),        # "Office"
    )
)
```

Дальше создается `InterfaceCollector` с credentials и вызывается `collect_dicts(devices)` -- это точка входа в систему сбора. Результат проходит через `apply_fields_config()` (переименование полей по `fields.yaml`) и отправляется в экспортер.

> **Python-концепция: argparse и \*\*kwargs** -- `args` это объект `argparse.Namespace`, содержащий все аргументы командной строки. `args.format`, `args.transport`, `args.fields` -- это атрибуты, заданные через `--format excel`, `--transport ssh2` и т.д. Конструктор `InterfaceCollector(**kwargs)` передает все неизвестные аргументы в `BaseCollector.__init__()` через распаковку kwargs.

**Входные данные:**
```python
# args (от argparse)
args.devices = "devices_ips.py"
args.format = "excel"
args.transport = "ssh2"
args.fields = None
```

**Выходные данные:**
```python
# data после collect_dicts()
[
    {"interface": "GigabitEthernet0/1", "status": "up", "hostname": "sw-01", ...},
    {"interface": "GigabitEthernet0/2", "status": "down", "hostname": "sw-01", ...},
]
```

---

## 2. BaseCollector

Все коллекторы наследуются от `BaseCollector`. Он определяет общую логику: параллельный сбор, подключение, парсинг, обработку ошибок.

### Файл: collectors/base.py (строки ~56-222)

```python
class BaseCollector(ABC):
    command: str = ""
    platform_commands: Dict[str, str] = {}
    model_class: Optional[Type[T]] = None

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        use_ntc: bool = True,
        ntc_fields: Optional[List[str]] = None,
        max_workers: int = 10,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        transport: str = "ssh2",
        max_retries: int = 2,
        retry_delay: int = 5,
        context: Optional[RunContext] = None,
    ):
        self.credentials = credentials
        self.ctx = context or get_current_context()
        self.use_ntc = use_ntc and NTC_AVAILABLE
        self.ntc_fields = ntc_fields
        self.max_workers = max_workers

        # Менеджер подключений с retry логикой
        self._conn_manager = ConnectionManager(
            timeout_socket=timeout_socket,
            timeout_transport=timeout_transport,
            transport=transport,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        # NTC парсер
        if self.use_ntc:
            try:
                self._parser = NTCParser()
            except ImportError:
                self._parser = None
                self.use_ntc = False
        else:
            self._parser = None

        self._skip_normalize = False
```

### Что здесь происходит

`BaseCollector` при создании инициализирует два ключевых компонента:
- **ConnectionManager** -- управляет SSH-подключениями через Scrapli
- **NTCParser** -- парсит вывод команд через TextFSM шаблоны

Атрибут класса `platform_commands` -- это словарь `{платформа: команда}`. Каждый конкретный коллектор устанавливает свои команды. `model_class` -- опциональный класс модели (Interface, MACEntry и т.д.) для типизированного вывода.

### Файл: collectors/base.py (строки ~189-292) -- collect_dicts и _collect_parallel

```python
def collect_dicts(
    self,
    devices: List[Device],
    parallel: bool = True,
    progress_callback: Optional[ProgressCallback] = None,
) -> List[Dict[str, Any]]:
    all_data = []
    total = len(devices)

    if parallel and len(devices) > 1:
        all_data = self._collect_parallel(devices, progress_callback)
    else:
        for idx, device in enumerate(devices):
            data = self._collect_from_device(device)
            success = len(data) > 0
            all_data.extend(data)
            if progress_callback:
                progress_callback(idx + 1, total, device.host, success)

    logger.info(f"{self._log_prefix()}Собрано записей: {len(all_data)} с {len(devices)} устройств")
    return all_data

def _collect_parallel(
    self,
    devices: List[Device],
    progress_callback: Optional[ProgressCallback] = None,
) -> List[Dict[str, Any]]:
    all_data = []
    total = len(devices)
    completed_count = 0

    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
        futures = {
            executor.submit(self._collect_from_device, device): device
            for device in devices
        }

        for future in as_completed(futures):
            device = futures[future]
            completed_count += 1
            success = False
            try:
                data = future.result()
                all_data.extend(data)
                success = len(data) > 0
            except CollectorError as e:
                logger.error(f"Ошибка сбора с {device.host}: {format_error_for_log(e)}")
            except Exception as e:
                logger.error(f"Неизвестная ошибка сбора с {device.host}: {e}")

            if progress_callback:
                progress_callback(completed_count, total, device.host, success)

    return all_data
```

### Что здесь происходит

`collect_dicts()` -- главная точка входа. Если устройств больше одного и `parallel=True`, запускается `_collect_parallel()`. Иначе -- последовательный обход.

`_collect_parallel()` создает пул потоков с `max_workers=10` потоками. Для каждого устройства отправляется задача `_collect_from_device(device)`. Dict comprehension `{executor.submit(...): device}` создает словарь `{Future: Device}` -- это нужно чтобы при получении результата знать, с какого устройства он пришел.

`as_completed(futures)` отдает Future в порядке завершения (а не отправки!). Это значит что быстрые устройства не ждут медленных.

> **Python-концепция: ThreadPoolExecutor и futures** -- `ThreadPoolExecutor` из модуля `concurrent.futures` управляет пулом потоков. `executor.submit(fn, arg)` возвращает объект `Future` -- "обещание" результата. `as_completed(futures)` -- итератор, который yield'ит futures по мере завершения. `future.result()` блокирует до получения результата или бросает исключение, которое произошло в потоке.

### Файл: collectors/base.py (строки ~294-466) -- _collect_from_device (базовый)

```python
def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
    command = self._get_command(device)
    if not command:
        logger.warning(f"Нет команды для {device.platform}")
        return []

    try:
        with self._conn_manager.connect(device, self.credentials) as conn:
            hostname = self._init_device_connection(conn, device)

            response = conn.send_command(command)
            data = self._parse_output(response.result, device)

            self._add_metadata_to_rows(data, hostname, device.host)
            logger.info(f"{hostname}: собрано {len(data)} записей")
            return data

    except Exception as e:
        return self._handle_collection_error(e, device)
```

### Что здесь происходит

Базовый `_collect_from_device` делает четыре вещи:
1. Выбирает команду для платформы (`_get_command`)
2. Подключается к устройству через SSH (`_conn_manager.connect`)
3. Выполняет команду и парсит вывод (`send_command` + `_parse_output`)
4. Добавляет hostname и device_ip к каждой записи (`_add_metadata_to_rows`)

Важно: конкретные коллекторы (Interface, MAC, LLDP, Inventory) **переопределяют** этот метод, добавляя дополнительные команды и нормализацию. Базовая версия используется только если наследник не переопределил.

> **Python-концепция: ABC и abstractmethod** -- `BaseCollector(ABC)` наследуется от `ABC` (Abstract Base Class). Метод `_parse_output` помечен как `@abstractmethod` -- это значит, что нельзя создать экземпляр `BaseCollector` напрямую, только через наследников. Каждый наследник обязан реализовать `_parse_output`.

---

## 3. ConnectionManager

Управляет SSH-подключениями через библиотеку Scrapli: retry при ошибках, извлечение hostname из prompt, маппинг платформ.

### Файл: core/connection.py (строки ~52-78) -- маппинги платформ

```python
SCRAPLI_PLATFORM_MAP = {
    "cisco_ios": "cisco_iosxe",
    "cisco_iosxe": "cisco_iosxe",
    "cisco_nxos": "cisco_nxos",
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
    "qtech": "cisco_iosxe",       # QTech использует cisco_iosxe драйвер
    "qtech_qsw": "cisco_iosxe",
}

NTC_PLATFORM_MAP = {
    "cisco_iosxe": "cisco_ios",
    "cisco_ios": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "arista_eos": "arista_eos",
    "qtech": "cisco_ios",          # QTech для NTC -> cisco_ios
    "qtech_qsw": "cisco_ios",
}
```

### Что здесь происходит

Два маппинга решают одну задачу -- привести название платформы из нашего формата к формату библиотеки:
- `SCRAPLI_PLATFORM_MAP` -- для SSH-драйвера Scrapli (QTech эмулирует Cisco IOS XE)
- `NTC_PLATFORM_MAP` -- для TextFSM шаблонов NTC Templates (QTech fallback на cisco_ios)

### Файл: core/connection.py (строки ~205-347) -- connect() с retry

```python
@contextmanager
def connect(
    self,
    device: Device,
    credentials: Credentials,
) -> Generator[Scrapli, None, None]:
    connection = None
    last_error = None
    params = self._build_connection_params(device, credentials)

    # Всего попыток = 1 (первая) + max_retries
    total_attempts = 1 + self.max_retries

    for attempt in range(1, total_attempts + 1):
        try:
            if attempt == 1:
                logger.info(f"Подключение к {device.host}...")
            else:
                logger.info(
                    f"Подключение к {device.host} (попытка {attempt}/{total_attempts})..."
                )

            connection = Scrapli(**params)
            connection.open()

            device.status = DeviceStatus.ONLINE
            device.hostname = self.get_hostname(connection)

            try:
                yield connection
            finally:
                if connection:
                    try:
                        connection.close()
                    except Exception:
                        pass
            return  # Успешно завершено

        except ScrapliAuthenticationFailed as e:
            # Ошибки аутентификации НЕ повторяем
            device.status = DeviceStatus.ERROR
            raise AuthenticationError(f"Ошибка аутентификации: {e}", device=device.host) from e

        except ScrapliTimeout as e:
            last_error = CollectorTimeoutError(...)
            if attempt < total_attempts:
                logger.warning(f"Таймаут, повтор через {self.retry_delay}с...")
                time.sleep(self.retry_delay)

        except ScrapliConnectionError as e:
            last_error = CollectorConnectionError(...)
            if attempt < total_attempts:
                time.sleep(self.retry_delay)

    # Все попытки исчерпаны
    if last_error:
        raise last_error
```

### Что здесь происходит

Метод `connect()` -- это **контекстный менеджер** с retry-логикой. Разберем по шагам:

1. `_build_connection_params()` формирует словарь для Scrapli: host, username, password, platform, transport, таймауты
2. Цикл `for attempt in range(1, total_attempts + 1)` -- до 3 попыток (1 основная + 2 retry)
3. `Scrapli(**params)` создает объект подключения, `connection.open()` устанавливает SSH-сессию
4. `yield connection` -- отдает управление коду внутри `with` блока
5. После `yield` в блоке `finally` -- `connection.close()` гарантированно закрывает соединение

Ключевая деталь: **ошибки аутентификации НЕ повторяются** (пароль неправильный -- retry не поможет). Таймауты и ошибки подключения -- повторяются.

> **Python-концепция: @contextmanager и yield** -- Декоратор `@contextmanager` превращает генератор-функцию в контекстный менеджер. Код до `yield` выполняется при входе в `with`, код после `yield` -- при выходе. `Generator[Scrapli, None, None]` -- тип: генератор, который yield'ит объект Scrapli. Блок `try/finally` вокруг `yield` гарантирует очистку ресурсов даже при исключении.

### Файл: core/connection.py (строки ~349-367) -- get_hostname

```python
@staticmethod
def get_hostname(connection: Scrapli) -> str:
    try:
        prompt = connection.get_prompt()
        # Убираем символы prompt (#, >, $, etc.)
        hostname = re.sub(r"[#>$\s]+$", "", prompt).strip()
        return hostname if hostname else "Unknown"
    except Exception as e:
        logger.warning(f"Не удалось получить hostname: {e}")
        return "Unknown"
```

### Что здесь происходит

Scrapli хранит текущий prompt устройства (например, `switch-01#`). `get_hostname()` берет prompt и убирает символы `#`, `>`, `$` -- получается чистый hostname `switch-01`.

---

## 4. NTCParser (TextFSM)

Парсер превращает сырой текстовый вывод команды в структурированные данные (список словарей). Поддерживает кастомные шаблоны для нестандартных платформ (QTech).

### Файл: parsers/textfsm_parser.py (строки ~73-102) -- UNIVERSAL_FIELD_MAP

```python
UNIVERSAL_FIELD_MAP = {
    "hostname": ["hostname", "host", "switchname", "device_id"],
    "hardware": ["hardware", "platform", "model", "chassis", "device_model"],
    "serial": ["serial", "serial_number", "sn", "chassis_sn", "serialnum"],
    "mac": ["mac", "mac_address", "destination_address"],
    "vlan": ["vlan", "vlan_id"],
    "interface": ["interface", "port", "destination_port"],
    "status": ["status", "link_status", "link"],
    "neighbor": ["neighbor", "neighbor_id", "device_id", "remote_system_name"],
    "local_interface": ["local_interface", "local_port"],
    "remote_interface": ["remote_interface", "remote_port", "port_id"],
    # ...
}
```

### Что здесь происходит

Разные платформы называют одно и то же поле по-разному. Cisco говорит `destination_address`, Arista -- `mac_address`, NTC шаблон может вернуть `mac`. `UNIVERSAL_FIELD_MAP` маппит все варианты к стандартному имени.

### Файл: parsers/textfsm_parser.py (строки ~132-216) -- parse()

```python
def parse(
    self,
    output: str,
    platform: str,
    command: str,
    fields: Optional[List[str]] = None,
    normalize: bool = True,
) -> List[Dict[str, Any]]:
    if not output or not output.strip():
        return []

    parsed_data = []
    used_custom_template = False

    try:
        # 1. Проверяем кастомный шаблон
        template_key = (platform.lower(), command.lower())
        if template_key in CUSTOM_TEXTFSM_TEMPLATES and TEXTFSM_AVAILABLE:
            template_file = CUSTOM_TEXTFSM_TEMPLATES[template_key]
            template_path = os.path.join(TEMPLATES_DIR, template_file)

            if os.path.exists(template_path):
                parsed_data = self._parse_with_textfsm(output, template_path)
                used_custom_template = True

        # 2. Fallback на NTC Templates
        if not parsed_data and not used_custom_template:
            ntc_platform = NTC_PLATFORM_MAP.get(platform, platform)
            parsed_data = parse_output(
                platform=ntc_platform,
                command=command,
                data=output
            )

        if not parsed_data:
            return []

        if isinstance(parsed_data, dict):
            parsed_data = [parsed_data]

        # Нормализуем имена полей
        if normalize:
            parsed_data = self._normalize_fields(parsed_data)

        # Фильтруем поля если указаны
        if fields:
            parsed_data = self._filter_fields(parsed_data, fields)

        return parsed_data

    except Exception as e:
        logger.error(f"Ошибка парсинга {platform}/{command}: {e}")
        return []
```

### Что здесь происходит

Алгоритм парсинга с двумя уровнями:

1. **Кастомный шаблон** -- проверяем ключ `(platform, command)` в словаре `CUSTOM_TEXTFSM_TEMPLATES`. Если есть -- используем наш .textfsm файл из папки `templates/`. Это нужно для QTech, потому что NTC Templates не знает эту платформу.

2. **NTC Templates** -- если кастомного шаблона нет или он вернул пустые данные, используем библиотеку `ntc_templates`. Она сама находит нужный шаблон по `platform + command`.

3. **Нормализация полей** -- после парсинга приводим имена полей к стандартным через `UNIVERSAL_FIELD_MAP`.

### Файл: parsers/textfsm_parser.py (строки ~218-256) -- _parse_with_textfsm (кастомные шаблоны)

```python
def _parse_with_textfsm(
    self,
    output: str,
    template_path: str,
) -> List[Dict[str, Any]]:
    try:
        with open(template_path, "r", encoding="utf-8-sig") as f:
            template_content = f.read()

        template_io = StringIO(template_content)
        fsm = textfsm.TextFSM(template_io)
        result = fsm.ParseText(output)

        # Преобразуем в список словарей
        headers = [h.lower() for h in fsm.header]
        parsed = []
        for row in result:
            parsed.append(dict(zip(headers, row)))

        return parsed

    except Exception as e:
        logger.error(f"Ошибка парсинга TextFSM шаблона {template_path}: {e}")
        return []
```

### Что здесь происходит

TextFSM работает так: шаблон определяет регулярные выражения для извлечения данных. `fsm.header` -- список имен полей из шаблона (["INTERFACE", "STATUS", "VLAN"]). `fsm.ParseText(output)` возвращает список списков (как таблица). `dict(zip(headers, row))` превращает каждую строку в словарь.

> **Python-концепция: StringIO и textfsm** -- `StringIO` создает файлоподобный объект из строки (TextFSM ожидает файл, а не строку). `textfsm.TextFSM(template_io)` компилирует шаблон в конечный автомат. `dict(zip(headers, row))` -- идиома Python: `zip` попарно соединяет два списка, `dict` превращает пары в словарь. Пример: `dict(zip(["a","b"], [1,2]))` = `{"a": 1, "b": 2}`.

**Пример преобразования:**

Входные данные (SSH вывод):
```
GigabitEthernet0/1 is up, line protocol is up
  Internet address is 10.0.0.1/24
  MTU 1500 bytes
```

Выходные данные (после TextFSM):
```python
[
    {
        "interface": "GigabitEthernet0/1",
        "link_status": "up",
        "protocol_status": "up",
        "ip_address": "10.0.0.1",
        "prefix_length": "24",
        "mtu": "1500",
    }
]
```

> **QTech: LINK_STATUS и administratively down**
>
> QTech может вернуть `administratively down` вместо простого `DOWN`:
> ```
> TFGigabitEthernet 0/3 is administratively down  , line protocol is DOWN
> ```
> TextFSM шаблон использует расширенный regex:
> ```
> Value LINK_STATUS ((?:administratively\s+)?(?:UP|DOWN|up|down))
> ```
> `(?:administratively\s+)?` — опциональная non-capturing группа, матчит `administratively ` перед `down`.
> Далее нормализатор `STATUS_MAP` преобразует: `"administratively down"` → `"disabled"`.

---

## 5. InterfaceCollector

Самый сложный коллектор. Помимо основной команды (`show interfaces`), собирает LAG membership, switchport mode и media_type через дополнительные команды.

### Файл: collectors/interfaces.py (строки ~39-93) -- класс и __init__

```python
class InterfaceCollector(BaseCollector):
    model_class = Interface

    # Команды для разных платформ (из централизованного хранилища)
    platform_commands = COLLECTOR_COMMANDS.get("interfaces", {})

    # Вторичные команды (из централизованного хранилища commands.py)
    error_commands = SECONDARY_COMMANDS.get("interface_errors", {})
    lag_commands = SECONDARY_COMMANDS.get("lag", {})
    switchport_commands = SECONDARY_COMMANDS.get("switchport", {})
    media_type_commands = SECONDARY_COMMANDS.get("media_type", {})

    def __init__(
        self,
        include_errors: bool = False,
        collect_lag_info: bool = True,
        collect_switchport: bool = True,
        collect_media_type: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.include_errors = include_errors
        self.collect_lag_info = collect_lag_info
        self.collect_switchport = collect_switchport
        self.collect_media_type = collect_media_type
        self._normalizer = InterfaceNormalizer()
```

### Что здесь происходит

Коллектор загружает команды из централизованного хранилища `core/constants/commands.py`. Атрибуты класса `platform_commands`, `lag_commands` и т.д. -- это словари вида `{платформа: команда}`.

### Файл: core/constants/commands.py (строки ~86-129) -- SECONDARY_COMMANDS

```python
SECONDARY_COMMANDS: Dict[str, Dict[str, str]] = {
    "lag": {
        "cisco_ios": "show etherchannel summary",
        "cisco_iosxe": "show etherchannel summary",
        "cisco_nxos": "show port-channel summary",
        "qtech": "show aggregatePort summary",
    },
    "switchport": {
        "cisco_ios": "show interfaces switchport",
        "cisco_nxos": "show interface switchport",
        "qtech": "show interface switchport",
    },
    "media_type": {
        # Cisco IOS/IOS-XE: НЕ нужен — media_type из основной show interfaces
        "cisco_nxos": "show interface status",
        "qtech": "show interface transceiver",
        "qtech_qsw": "show interface transceiver",
    },
    "transceiver": {
        "cisco_nxos": "show interface transceiver",
        "qtech": "show interface transceiver",
    },
}
```

### Файл: collectors/interfaces.py (строки ~195-308) -- _collect_from_device (переопределенный)

```python
def _collect_from_device(self, device: Device) -> List[Dict[str, Any]]:
    command = self._get_command(device)
    if not command:
        return []

    try:
        with self._conn_manager.connect(device, self.credentials) as conn:
            hostname = self._init_device_connection(conn, device)

            # 1. Парсим основную команду show interfaces (СЫРЫЕ данные)
            response = conn.send_command(command)
            raw_data = self._parse_output(response.result, device)

            # --format parsed: сырые данные TextFSM, без нормализации
            if self._skip_normalize:
                self._add_metadata_to_rows(raw_data, hostname, device.host)
                return raw_data

            # 2. Domain Layer: нормализация через InterfaceNormalizer
            data = self._normalizer.normalize_dicts(
                raw_data, hostname=hostname, device_ip=device.host
            )

            # 3. Собираем дополнительные данные для обогащения
            lag_membership = {}
            if self.collect_lag_info:
                lag_cmd = self.lag_commands.get(device.platform)
                if lag_cmd:
                    lag_response = conn.send_command(lag_cmd)
                    # Data-driven dispatch: LAG_PARSERS dict вместо if/elif
                    parser_name = self.LAG_PARSERS.get(device.platform)
                    if parser_name:
                        lag_membership = getattr(self, parser_name)(lag_response.result)
                    else:
                        lag_membership = self._parse_lag_membership(
                            lag_response.result, device.platform, lag_cmd,
                        )

            switchport_modes = {}
            if self.collect_switchport:
                sw_cmd = self.switchport_commands.get(device.platform)
                if sw_cmd:
                    sw_response = conn.send_command(sw_cmd)
                    switchport_modes = self._parse_switchport_modes(...)

            media_types = {}
            if self.collect_media_type:
                mt_cmd = self.media_type_commands.get(device.platform)
                if mt_cmd:
                    mt_response = conn.send_command(mt_cmd)
                    media_types = self._parse_media_types(...)

            # 4. Domain Layer: обогащение данных
            if lag_membership:
                data = self._normalizer.enrich_with_lag(data, lag_membership)
            if switchport_modes:
                data = self._normalizer.enrich_with_switchport(
                    data, switchport_modes, lag_membership
                )
            if media_types:
                data = self._normalizer.enrich_with_media_type(data, media_types)

            return data

    except Exception as e:
        return self._handle_collection_error(e, device)
```

### Что здесь происходит

`InterfaceCollector` переопределяет базовый `_collect_from_device` и выполняет до **4 SSH команд** за одно подключение:

1. `show interfaces` -- основные данные (статус, MAC, IP, MTU, speed)
2. `show etherchannel summary` -- какие порты объединены в LAG
3. `show interfaces switchport` -- режим порта (access/trunk)
4. `show interface status` (NX-OS) / `show interface transceiver` (QTech) -- точный тип трансивера (на IOS уже в основной команде)

Все эти данные объединяются через `InterfaceNormalizer` из Domain Layer.

> **Паттерн: data-driven dispatch** -- для LAG парсинга используется `LAG_PARSERS` dict вместо `if/elif`:
> ```python
> LAG_PARSERS = {
>     "qtech": "_parse_lag_membership_qtech",
>     "qtech_qsw": "_parse_lag_membership_qtech",
> }
> ```
> Платформы с кастомным парсером указаны в dict. Все остальные используют generic `_parse_lag_membership()`.
> Добавление нового парсера = одна строка в dict + метод-парсер. Не нужно править if/elif.
> Используется `getattr(self, parser_name)` для получения метода по имени из строки.

> **Python-концепция: method override и dict.get()** -- `_collect_from_device` переопределяет метод родительского класса. Python использует MRO (Method Resolution Order) чтобы найти правильную реализацию. `self.lag_commands.get(device.platform)` безопасно возвращает `None` если платформа не поддерживается (вместо KeyError).

**Входные данные:** объект `Device(host="10.0.0.1", platform="cisco_iosxe")`

**Выходные данные (после всех обогащений):**
```python
[
    {
        "interface": "GigabitEthernet0/1",
        "status": "up",
        "mac": "0011.2233.4455",
        "ip_address": "10.0.0.1",
        "port_type": "1g-rj45",
        "mode": "access",
        "access_vlan": "10",
        "lag": "",
        "hostname": "sw-01",
        "device_ip": "10.0.0.1",
    },
]
```

---

## 6. InterfaceNormalizer

Domain Layer -- чистая логика без SSH. Превращает сырые данные парсера в нормализованный формат с определением типа порта.

### Файл: core/domain/interface.py (строки ~14-26) -- STATUS_MAP

```python
STATUS_MAP: Dict[str, str] = {
    "connected": "up",
    "up": "up",
    "notconnect": "down",
    "notconnected": "down",
    "down": "down",
    "disabled": "disabled",
    "err-disabled": "error",
    "errdisabled": "error",  # вариант без дефиса
    "administratively down": "disabled",
    "admin down": "disabled",
}
```

### Файл: core/domain/interface.py (строки ~70-132) -- normalize_dicts и _normalize_row

```python
def normalize_dicts(
    self,
    data: List[Dict[str, Any]],
    hostname: str = "",
    device_ip: str = "",
) -> List[Dict[str, Any]]:
    result = []
    for row in data:
        normalized = self._normalize_row(row)
        if hostname:
            normalized["hostname"] = hostname
        if device_ip:
            normalized["device_ip"] = device_ip
        result.append(normalized)
    return result

def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(row)

    # Убираем пробелы в имени интерфейса (QTech: "TFGigabitEthernet 0/39" -> "TFGigabitEthernet0/39")
    iface_name = row.get("interface", "")
    if iface_name:
        result["interface"] = iface_name.replace(" ", "")

    # Нормализуем статус
    status = row.get("link_status", row.get("status", ""))
    if status:
        result["status"] = self.normalize_status(status)

    # Унифицируем MAC из разных полей NTC
    if not result.get("mac"):
        for mac_field in ["mac_address", "address", "bia", "hardware_address"]:
            if row.get(mac_field):
                result["mac"] = row[mac_field]
                break

    # Унифицируем hardware_type и media_type
    if "hardware_type" not in result and "hardware" in row:
        result["hardware_type"] = row["hardware"]
    if "media_type" not in result and "media" in row:
        result["media_type"] = row["media"]

    # Определяем port_type если не задан
    if not result.get("port_type"):
        iface = result.get("interface", result.get("name", ""))
        result["port_type"] = self.detect_port_type(result, iface.lower())

    return result
```

### Что здесь происходит

`_normalize_row()` делает четыре вещи с каждой записью:

1. **Статус** -- `"connected"` -> `"up"`, `"notconnect"` -> `"down"` через STATUS_MAP
2. **MAC** -- ищет MAC-адрес в разных полях (NTC может назвать поле `mac_address`, `bia` или `address`)
3. **Hardware/media type** -- унифицирует имена полей
4. **Port type** -- вызывает `detect_port_type()` для определения типа порта

### Файл: core/domain/interface.py (строки ~147-263) -- detect_port_type (ПОЛНЫЙ алгоритм)

```python
def detect_port_type(self, row: Dict[str, Any], iface_lower: str) -> str:
    hardware_type = row.get("hardware_type", "").lower()
    media_type = row.get("media_type", "").lower()

    # LAG интерфейсы (Cisco Port-channel, QTech AggregatePort)
    # Единый источник: is_lag_name() из core/constants/interfaces.py
    if is_lag_name(iface_lower):
        return "lag"

    # Виртуальные интерфейсы
    if iface_lower.startswith(("vlan", "loopback", "null", "tunnel", "nve")):
        return "virtual"

    # Management - обычно copper
    if iface_lower.startswith(("mgmt", "management")):
        return "1g-rj45"

    # 1. По media_type (наиболее точный)
    if media_type and media_type not in ("unknown", "not present", ""):
        port_type = self._detect_from_media_type(media_type)
        if port_type:
            return port_type

    # 2. По hardware_type (максимальная скорость порта)
    if hardware_type:
        port_type = self._detect_from_hardware_type(hardware_type)
        if port_type:
            return port_type

    # 3. По имени интерфейса
    return self._detect_from_interface_name(iface_lower)
```

### Что здесь происходит

Алгоритм определения типа порта с **тремя приоритетами**:

1. **Специальные интерфейсы** -- LAG (`Port-channel1`, `Ag1`), виртуальные (`Vlan100`, `Loopback0`), management
2. **media_type** -- самый точный источник. `"SFP-10GBase-LR"` -> `"10g-sfp+"`
3. **hardware_type** -- менее точный. `"Gigabit Ethernet"` -> `"1g-rj45"`
4. **Имя интерфейса** -- fallback. `"TenGigabitEthernet1/1"` -> `"10g-sfp+"`

Для NetBox эти значения потом преобразуются в конкретные типы через `PORT_TYPE_MAP` и `get_netbox_interface_type()`.

### Маппинги port_type (core/constants/interfaces.py)

Три `_detect_from_*()` метода используют **shared маппинги** из `core/constants/interfaces.py`:

```python
# media_type паттерн → port_type
MEDIA_TYPE_PORT_TYPE_MAP = {
    "100gbase": "100g-qsfp28", "100g": "100g-qsfp28",
    "10gbase": "10g-sfp+",     "10g": "10g-sfp+",
    "1000base-t": "1g-rj45",   "rj45": "1g-rj45",
    "1000base": "1g-sfp",      "sfp": "1g-sfp",
    ...
}

# hardware_type паттерн → port_type (порядок: 10000 перед 1000!)
HARDWARE_TYPE_PORT_TYPE_MAP = {
    "100/1000/10000": "10g-sfp+",  # NX-OS multi-speed первым
    "100000": "100g-qsfp28", "10000": "10g-sfp+",
    "gigabit": "1g-rj45",  # 1G только после 10G
    ...
}

# Префикс имени → port_type (hu, te, gi — требуют цифру после)
INTERFACE_NAME_PORT_TYPE_MAP = {
    "hundredgig": "100g-qsfp28", "hu": "100g-qsfp28",
    "tengig": "10g-sfp+",        "te": "10g-sfp+",
    "gigabit": "1g-rj45",        "gi": "1g-rj45",
    ...
}
```

**Зачем маппинги, а не if/elif?** Единый источник данных, easy to extend, порядок гарантирован dict-ом (Python 3.7+). Для новой скорости — добавить запись в маппинг.

### Двухуровневый маппинг: port_type vs NetBox type

Это важный момент: media_type используется на **двух уровнях**, и даёт **разные результаты**.

**Уровень 1 — Collector (port_type):** `detect_port_type()` определяет **грубую категорию** порта. Из media_type `"10GBASE-SR-SFP+"` он извлекает `"10g-sfp+"` (видит "10gbase" в строке). Это нужно для внутренней логики (определение LAG, switchport mode и т.д.).

**Уровень 2 — NetBox Sync:** `get_netbox_interface_type()` определяет **точный тип** для API NetBox. Он проверяет media_type по `NETBOX_INTERFACE_TYPE_MAP` — словарю из ~80 паттернов. Паттерн `"10gbase-sr"` совпадает с `"10gbase-sr-sfp+"` и возвращает NetBox тип `"10gbase-sr"`.

**Пример: QTech интерфейс TFGigabitEthernet 0/1**

```
БЕЗ transceiver (определение по имени):
  detect_port_type("tfgigabitethernet 0/1") → "10g-sfp+" (по имени)
  get_netbox_interface_type("TFGi 0/1")     → "10gbase-x-sfpp" (generic SFP+)

С transceiver (media_type = "10GBASE-SR-SFP+"):
  detect_port_type()                        → "10g-sfp+" (та же категория)
  get_netbox_interface_type(media_type=...) → "10gbase-sr" (ТОЧНЫЙ тип!)
```

Разница видна в NetBox: вместо generic "SFP+" отображается конкретный "10GBASE-SR".

Ключевой момент: `get_netbox_interface_type()` проверяет media_type **до** port_type (приоритет 4 vs 5 в функции), поэтому точный тип из трансивера всегда побеждает generic тип из имени.

### Как добавить media_type для другой платформы

Механизм универсальный — нужно знать **какая команда** возвращает тип трансивера и **какие поля** в TextFSM шаблоне.

**Текущее состояние media_type по платформам:**

| Платформа | Откуда берётся media_type | Доп. команда? |
|-----------|--------------------------|---------------|
| `cisco_ios` | Основная `show interfaces` (поле `MEDIA_TYPE`) | Не нужна (уже в основной) |
| `cisco_iosxe` | Основная `show interfaces` (поле `MEDIA_TYPE`) | Не нужна (уже в основной) |
| `cisco_nxos` | `show interface status` (поле `type`) | ✅ В SECONDARY_COMMANDS |
| `qtech` | `show interface transceiver` (поле `TYPE`) | ✅ В SECONDARY_COMMANDS |

**Кастомная настройка:** Любую платформу можно добавить в `SECONDARY_COMMANDS["media_type"]`,
даже если media_type уже приходит из основной команды. Например:

```python
"media_type": {
    "cisco_nxos": "show interface status",
    "cisco_ios": "show interfaces status",      # опционально
    "arista_eos": "show interfaces status",     # опционально (NTC шаблон готов)
    "qtech": "show interface transceiver",
}
```

`enrich_with_media_type()` перезапишет media_type только если новое значение более
информативно. Для Cisco IOS это лишний SSH запрос (данные уже есть), но работать будет.

> **Важно:** Cisco IOS `show interface transceiver` **НЕ подходит** — возвращает только оптические
> параметры (температура, напряжение, мощность), но **не тип трансивера**. Тип трансивера на
> Cisco IOS находится в `show interfaces` (основная) или `show interfaces status` (доп.).
> Это отличается от QTech, где `show interface transceiver` возвращает `Transceiver Type: 10GBASE-SR-SFP+`.

**Если нужен кастомный шаблон:**

`_parse_media_types()` поддерживает две пары полей:
- NTC (lowercase): `port` + `type` — Cisco, Arista
- TextFSM (UPPERCASE): `INTERFACE` + `TYPE` — QTech и кастомные шаблоны

```python
# Код автоматически определяет формат:
port = row.get("port") or row.get("INTERFACE", "")
media_type = row.get("type") or row.get("TYPE", "")
```

Для нового вендора:
1. Создать `templates/<vendor>_show_<command>.textfsm` с полями `INTERFACE` и `TYPE`
2. Зарегистрировать в `CUSTOM_TEXTFSM_TEMPLATES`
3. Добавить в `SECONDARY_COMMANDS["media_type"]`

### Файл: core/constants/netbox.py (строки ~185-195) -- PORT_TYPE_MAP

```python
PORT_TYPE_MAP: Dict[str, str] = {
    "100g-qsfp28": "100gbase-x-qsfp28",
    "40g-qsfp": "40gbase-x-qsfpp",
    "25g-sfp28": "25gbase-x-sfp28",
    "10g-sfp+": "10gbase-x-sfpp",
    "1g-sfp": "1000base-x-sfp",
    "1g-rj45": "1000base-t",
    "100m-rj45": "100base-tx",
    "lag": "lag",
    "virtual": "virtual",
}
```

### Что здесь происходит

`PORT_TYPE_MAP` -- финальное преобразование нашего внутреннего формата (`"10g-sfp+"`) в формат API NetBox (`"10gbase-x-sfpp"`). Используется в `netbox/sync/interfaces.py` при создании/обновлении интерфейсов.

> **Python-концепция: startswith(tuple) и in-place mutation** -- `iface_lower.startswith(("port-channel", "po", "aggregateport"))` принимает кортеж строк -- вернет True если строка начинается с любой из них. `result = dict(row)` создает **копию** словаря, а не ссылку. Поэтому мутация `result["status"]` не меняет оригинальный `row`.

**Пример трансформации:**

Входные данные (сырые от TextFSM):
```python
{
    "interface": "TenGigabitEthernet1/0/1",
    "link_status": "connected",
    "hardware_type": "Ten Gigabit Ethernet SFP+",
    "media_type": "SFP-10GBase-SR",
    "mac_address": "0011.2233.4455",
}
```

Выходные данные (после нормализации):
```python
{
    "interface": "TenGigabitEthernet1/0/1",
    "status": "up",                         # connected -> up
    "hardware_type": "Ten Gigabit Ethernet SFP+",
    "media_type": "SFP-10GBase-SR",
    "mac": "0011.2233.4455",                # mac_address -> mac
    "port_type": "10g-sfp+",               # определен из media_type
    "hostname": "sw-01",
    "device_ip": "10.0.0.1",
}
```

---

## 7. Другие нормализаторы

Каждый тип данных имеет свой нормализатор в Domain Layer.

### Файл: core/domain/mac.py (строки ~85-194) -- MACNormalizer

```python
def normalize_dicts(
    self,
    data: List[Dict[str, Any]],
    interface_status: Optional[Dict[str, str]] = None,
    hostname: str = "",
    device_ip: str = "",
) -> List[Dict[str, Any]]:
    interface_status = interface_status or {}
    result = []
    seen_macs: Set[Tuple[str, str, str]] = set()

    for row in data:
        normalized = self._normalize_row(row, interface_status)
        if normalized is None:
            continue  # Отфильтрован

        # Дедупликация по (mac, vlan, interface)
        mac_raw = normalize_mac_raw(normalized.get("mac", ""))
        vlan = normalized.get("vlan", "")
        interface = normalized.get("interface", "")
        key = (mac_raw, vlan, interface)

        if key in seen_macs:
            continue
        seen_macs.add(key)

        result.append(normalized)
    return result

def _normalize_row(self, row, interface_status):
    result = dict(row)

    # Нормализуем интерфейс
    interface = row.get("interface", row.get("destination_port", ""))
    if self.normalize_interfaces:
        interface = normalize_interface_short(interface)
    result["interface"] = interface

    # Проверяем исключения по интерфейсу
    if self._should_exclude_interface(interface):
        return None

    # Нормализуем MAC
    mac = row.get("mac", row.get("destination_address", ""))
    if mac:
        normalized_mac = normalize_mac(mac, format=self.mac_format)
        result["mac"] = normalized_mac if normalized_mac else mac

    # Тип MAC: dynamic или static
    raw_type = str(row.get("type", "")).lower()
    result["type"] = "dynamic" if "dynamic" in raw_type else "static"

    # Определяем status по состоянию порта
    port_status = interface_status.get(interface, "")
    if port_status.lower() in ONLINE_PORT_STATUSES:
        result["status"] = "online"
    elif port_status:
        result["status"] = "offline"
    else:
        result["status"] = "unknown"

    return result
```

### Что здесь происходит

MACNormalizer делает больше, чем просто нормализацию:

1. **Фильтрация** -- исключает интерфейсы по regex-паттернам (CPU, Vlan, Port-channel)
2. **Дедупликация** -- один и тот же MAC может появиться в таблице несколько раз (на разных VLAN или портах). `Set` с ключом `(mac, vlan, interface)` убирает дубликаты
3. **Формат MAC** -- `normalize_mac(mac, format="ieee")` превращает `0011.2233.4455` в `00:11:22:33:44:55`
4. **Статус** -- сопоставляет MAC с состоянием порта (connected -> online, notconnect -> offline)

> **Python-концепция: Set для дедупликации** -- `seen_macs: Set[Tuple[str, str, str]]` хранит уникальные кортежи. Проверка `key in seen_macs` работает за O(1) благодаря хэш-таблице. Кортежи (tuple) можно хэшировать (в отличие от списков).

### Файл: core/domain/lldp.py (строки ~48-190) -- LLDPNormalizer

```python
class LLDPNormalizer:
    def normalize_dicts(self, data, protocol="lldp", hostname="", device_ip=""):
        result = []
        for row in data:
            normalized = self._normalize_row(row)
            normalized["protocol"] = protocol.upper()
            if hostname:
                normalized["hostname"] = hostname
            result.append(normalized)
        return result

    def _normalize_row(self, row):
        result = {}
        port_id_value = None

        # Применяем маппинг ключей
        for key, value in row.items():
            key_lower = key.lower()
            if key_lower in ("port_id", "neighbor_port_id"):
                port_id_value = value
                continue
            new_key = KEY_MAPPING.get(key_lower, key_lower)
            result[new_key] = value

        # Определяем remote_port с приоритетом:
        # 1. port_id (если похож на интерфейс)
        # 2. port_description (если port_id = MAC)
        if not result.get("remote_port"):
            if port_id_value:
                port_id_str = str(port_id_value).strip()
                if self._is_interface_name(port_id_str):
                    result["remote_port"] = port_id_str
                elif self.is_mac_address(port_id_str):
                    if not result.get("remote_mac"):
                        result["remote_mac"] = port_id_str

        result["neighbor_type"] = self.determine_neighbor_type(result)
        return result
```

### Что здесь происходит

LLDP нормализация сложнее остальных из-за **неоднозначности полей**. TextFSM может вернуть `neighbor_port_id` как:
- `"Te1/0/2"` -- настоящий интерфейс
- `"00:11:22:33:44:55"` -- MAC-адрес (если сосед не передал имя порта)
- `"3"` -- числовой ID порта

`_normalize_row()` анализирует каждый вариант и раскладывает данные по правильным полям. Метод `merge_lldp_cdp()` объединяет данные двух протоколов: CDP дает hostname и platform, LLDP дает MAC-адрес (chassis_id).

### Файл: core/domain/inventory.py (строки ~90-141) -- InventoryNormalizer

```python
def _normalize_row(self, row):
    pid = row.get("pid", "")

    result = {
        "name": row.get("name", ""),
        "description": row.get("descr", row.get("description", "")),
        "pid": pid,
        "vid": row.get("vid", ""),
        "serial": row.get("sn", row.get("serial", "")),
        "manufacturer": self.detect_manufacturer_by_pid(pid),
    }
    return result

def detect_manufacturer_by_pid(self, pid: str) -> str:
    if not pid:
        return ""
    pid_upper = pid.upper()
    for manufacturer, patterns in PID_MANUFACTURER_PATTERNS.items():
        for pattern in patterns:
            if pattern in pid_upper or pid_upper.startswith(pattern):
                return manufacturer
    return ""
```

### Что здесь происходит

InventoryNormalizer унифицирует поля из разных форматов NTC (поле `descr` или `description`, `sn` или `serial`) и автоматически определяет производителя по Product ID: `"WS-C3750X"` -> `"Cisco"`, `"DCS-7050TX"` -> `"Arista"`. Трансиверы от сторонних вендоров определяются по имени из `show interface transceiver`.

Важная деталь: при синхронизации с NetBox имя inventory item ограничено **64 символами**. Обрезка происходит в sync-слое: первые 61 символ + "...".

---

## 8. Каждый коллектор в деталях

### Файл: collectors/mac.py (строки ~51-224) -- MACCollector

```python
class MACCollector(BaseCollector):
    model_class = MACEntry
    platform_commands = COLLECTOR_COMMANDS.get("mac", {})

    def __init__(
        self,
        mac_format: str = "ieee",
        collect_descriptions: bool = False,
        collect_trunk_ports: bool = False,
        collect_port_security: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.mac_format = mac_format
        self.collect_trunk_ports = collect_trunk_ports
        self.collect_port_security = collect_port_security
        self._normalizer = MACNormalizer(
            mac_format=self.mac_format,
            exclude_interfaces=self.exclude_interfaces,
            exclude_vlans=self.exclude_vlans,
        )
```

### Что здесь происходит

MACCollector переопределяет `_collect_from_device` и за одно подключение выполняет до **5 команд**:

1. `show mac address-table` -- основная MAC-таблица
2. `show interfaces status` -- статус портов (для определения online/offline)
3. `show interfaces description` -- описания (если `collect_descriptions=True`)
4. `show interfaces trunk` -- список trunk портов (для фильтрации)
5. `show running-config` -- sticky MAC из port-security (если `collect_port_security=True`)

Фильтрация trunk-портов -- ключевая функция. По умолчанию MAC с trunk-портов не включаются в отчет (на транке может быть сотни MAC-адресов). Включается флагом `--include-trunk`.

### Файл: collectors/lldp.py (строки ~46-169) -- LLDPCollector

```python
class LLDPCollector(BaseCollector):
    model_class = LLDPNeighbor
    lldp_commands = COLLECTOR_COMMANDS.get("lldp", {})
    cdp_commands = COLLECTOR_COMMANDS.get("cdp", {})
    lldp_summary_commands = SECONDARY_COMMANDS.get("lldp_summary", {})

    def __init__(self, protocol: str = "lldp", **kwargs):
        super().__init__(**kwargs)
        self.protocol = protocol.lower()
        self._normalizer = LLDPNormalizer()

        if self.protocol == "cdp":
            self.platform_commands = self.cdp_commands
        elif self.protocol == "both":
            self.platform_commands = self.lldp_commands
        else:
            self.platform_commands = self.lldp_commands
```

### Что здесь происходит

LLDPCollector поддерживает три режима:
- `protocol="lldp"` -- только LLDP
- `protocol="cdp"` -- только CDP
- `protocol="both"` -- оба протокола, потом merge через `LLDPNormalizer.merge_lldp_cdp()`

При `protocol="both"` выполняются до **3 команд**:
1. `show lldp neighbors` (summary) -- для получения `local_interface` (LLDP detail не всегда его содержит)
2. `show lldp neighbors detail` -- полные данные LLDP
3. `show cdp neighbors detail` -- полные данные CDP

CDP имеет приоритет по hostname и platform (проприетарный Cisco, надежнее). LLDP дополняет MAC-адресом (chassis_id).

### Файл: collectors/inventory.py (строки ~39-217) -- InventoryCollector

```python
class InventoryCollector(BaseCollector):
    model_class = InventoryItem
    platform_commands = COLLECTOR_COMMANDS.get("inventory", {})
    transceiver_commands = SECONDARY_COMMANDS.get("transceiver", {})

    def __init__(self, collect_transceivers: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.collect_transceivers = collect_transceivers
        self._normalizer = InventoryNormalizer()
```

### Что здесь происходит

InventoryCollector собирает модули, блоки питания и трансиверы. Для NX-OS и QTech трансиверы не видны через `show inventory` -- нужна отдельная команда `show interface transceiver`.

Алгоритм:
1. `show inventory` -- шасси, модули, PSU, вентиляторы
2. `show interface transceiver` -- SFP/QSFP модули с серийниками
3. `InventoryNormalizer.merge_with_transceivers()` -- объединяет оба источника

Для QTech `show inventory` вообще отсутствует -- весь inventory строится из transceiver.

### Файл: collectors/device.py (строки ~63-349) -- DeviceCollector

```python
class DeviceCollector:
    model_class = DeviceInfo

    def _collect_from_device(self, device: Device) -> Optional[Dict[str, Any]]:
        data = {}
        data["ip_address"] = device.host
        data["platform"] = device.platform
        data["manufacturer"] = device.vendor.capitalize() if device.vendor else "Cisco"

        try:
            with self._conn_manager.connect(device, self.credentials) as conn:
                response = conn.send_command("show version")
                output = response.result

                parsed_data = parse_output(
                    platform=ntc_platform,
                    command="show version",
                    data=output
                )
                parsed = parsed_data[0] if isinstance(parsed_data, list) and parsed_data else {}

                for device_key, csv_key in self.device_fields.items():
                    value = self._get_parsed_value(parsed, device_key)
                    data[csv_key] = value

                if "model" in data and data["model"]:
                    data["model"] = normalize_device_model(data["model"])

                hostname = self._conn_manager.get_hostname(conn)
                data["hostname"] = hostname
                data["name"] = hostname

        except (ConnectionError, AuthenticationError, TimeoutError) as e:
            # Fallback: используем данные из devices_ips.py
            data["name"] = device.hostname or device.host
            data["model"] = normalize_device_model(device.device_type) if device.device_type else "Unknown"
```

### Что здесь происходит

DeviceCollector -- особенный: он **не наследуется от BaseCollector** (исторически). Выполняет только `show version` и извлекает: hostname, модель, серийник, версию ПО, uptime.

Ключевая особенность: при ошибке подключения DeviceCollector **не пропускает устройство**, а заполняет данные из `devices_ips.py` (hostname, model). Это нужно для синхронизации -- устройство может быть offline, но его запись в NetBox должна быть.

`DeviceInventoryCollector` расширяет базовый, добавляя поля для NetBox: site, role, manufacturer, tenant.

---

## 9. Exporters

Экспортеры превращают список словарей в файлы разных форматов.

### Файл: exporters/base.py (строки ~24-170) -- BaseExporter

```python
class BaseExporter(ABC):
    file_extension: str = ".txt"

    def __init__(self, output_folder: str = "reports", encoding: str = "utf-8"):
        self.output_folder = Path(output_folder)
        self.encoding = encoding

    def export(
        self,
        data: List[Dict[str, Any]],
        filename: Optional[str] = None,
        columns: Optional[List[str]] = None,
    ) -> Optional[Path]:
        if not data:
            return None

        self._ensure_output_folder()

        if not filename:
            filename = self._generate_filename()

        if not filename.endswith(self.file_extension):
            filename += self.file_extension

        file_path = self.output_folder / filename

        if columns:
            data = self._filter_columns(data, columns)

        try:
            self._write(data, file_path)
            return file_path
        except Exception as e:
            logger.error(f"Ошибка экспорта в {file_path}: {e}")
            return None

    @abstractmethod
    def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
        pass
```

### Что здесь происходит

`BaseExporter` реализует паттерн **Template Method**: метод `export()` определяет алгоритм (создать папку -> сгенерировать имя -> отфильтровать колонки -> записать), а конкретную запись делегирует абстрактному `_write()`.

### Файл: exporters/excel.py (строки ~111-144) -- ExcelExporter._write

```python
def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"

    columns = self._get_all_columns(data)

    # Заголовок
    self._write_header(ws, columns)

    # Данные
    self._write_data(ws, data, columns)

    # Форматирование
    if self.auto_width:
        self._adjust_column_widths(ws, columns, data)
    if self.autofilter:
        ws.auto_filter.ref = ws.dimensions
    if self.freeze_header:
        ws.freeze_panes = "A2"

    wb.save(file_path)
```

### Что здесь происходит

ExcelExporter использует библиотеку `openpyxl`. Создает книгу с форматированием: синий заголовок, автофильтр, закрепленная первая строка, автоподбор ширины, цветовая индикация (зеленый для online, красный для offline).

### Файл: exporters/csv_exporter.py (строки ~97-128) -- CSVExporter._write

```python
def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
    columns = self._get_all_columns(data)

    with open(file_path, "w", newline="", encoding=self.encoding) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            delimiter=self.delimiter,
            quotechar=self.quotechar,
            quoting=self.quoting,
            extrasaction="ignore",
        )
        if self.include_header:
            writer.writeheader()
        writer.writerows(data)
```

### Что здесь происходит

CSVExporter использует стандартный `csv.DictWriter`. Параметр `extrasaction="ignore"` -- если в словаре есть ключи, которых нет в `fieldnames`, они игнорируются (без ошибки). Поддерживает разные разделители (запятая, точка с запятой, табуляция) и BOM для Excel.

### Файл: exporters/json_exporter.py (строки ~72-103) -- JSONExporter._write

```python
def _write(self, data: List[Dict[str, Any]], file_path: Path) -> None:
    if self.include_metadata:
        output = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_records": len(data),
                "columns": self._get_all_columns(data),
            },
            "data": data,
        }
    else:
        output = data

    with open(file_path, "w", encoding=self.encoding) as f:
        json.dump(output, f, indent=self.indent, ensure_ascii=self.ensure_ascii,
                  default=self._json_serializer)
```

### Файл: exporters/raw_exporter.py (строки ~55-83) -- RawExporter.export

```python
def export(self, data, filename="", **kwargs):
    if not data:
        print("[]")
        return None

    json_str = json.dumps(data, indent=self.indent, ensure_ascii=False,
                          default=self._json_serializer)
    print(json_str)
    return None
```

### Что здесь происходит

RawExporter -- особенный: он переопределяет `export()` целиком и выводит JSON прямо в stdout (без сохранения в файл). Используется для `--format parsed` -- отладка парсинга.

> **Python-концепция: Template Method pattern** -- паттерн проектирования, где базовый класс определяет скелет алгоритма (`export`), а конкретные шаги (`_write`) реализуются в подклассах. Это позволяет менять формат вывода без изменения общей логики (создание папок, генерация имени и т.д.). Стандартный модуль `csv` предоставляет `DictWriter` для записи словарей в CSV.

### Файл: fields_config.py (строки ~88-133) -- apply_fields_config

```python
def apply_fields_config(data: List[Dict[str, Any]], data_type: str) -> List[Dict[str, Any]]:
    enabled_fields = get_enabled_fields(data_type)
    if not enabled_fields:
        return data

    result = []
    for row in data:
        new_row = {}
        for field_name, display_name, _, default_value in enabled_fields:
            value = None
            for key in row.keys():
                if key.lower() == field_name.lower():
                    value = row[key]
                    break

            if value is None or value == "":
                if default_value is not None:
                    value = default_value

            if value is not None:
                new_row[display_name] = value

        if new_row:
            result.append(new_row)

    return result
```

### Что здесь происходит

`apply_fields_config()` -- финальное преобразование перед экспортом. Читает `fields.yaml` и:
1. Оставляет только **включённые** поля (`enabled: true`)
2. **Переименовывает** внутренние имена в display names (`interface` -> `Port`, `hostname` -> `Device`)
3. Сортирует поля по `order`
4. Подставляет `default` если значение пустое

Это то, что превращает технические имена полей в человекочитаемые заголовки Excel.

---

## 10. Диаграмма потока данных

```
python -m network_collector interfaces --format excel
    |
    v
+--------------------+
| cmd_interfaces()   |  cli/commands/collect.py
| prepare_collection |  -> load_devices() + get_credentials()
+--------------------+
    |
    v
+------------------------+
| InterfaceCollector     |  collectors/interfaces.py
| .collect_dicts()       |  -> BaseCollector.collect_dicts()
+------------------------+
    |
    v
+---------------------------+
| _collect_parallel()       |  collectors/base.py
| ThreadPoolExecutor(10)    |  10 потоков, as_completed()
+---------------------------+
    |  (для каждого устройства)
    v
+----------------------------+
| _collect_from_device()     |  collectors/interfaces.py (override)
+----------------------------+
    |
    v
+---------------------------+
| ConnectionManager         |  core/connection.py
| .connect() + retry        |  SSH через Scrapli, до 3 попыток
+---------------------------+
    |
    v
+------------------------------+
| conn.send_command(           |  1. "show interfaces"
|   "show interfaces")        |  2. "show etherchannel summary"
|                              |  3. "show interfaces switchport"
+------------------------------+
    |
    v
+----------------------------+
| NTCParser.parse()          |  parsers/textfsm_parser.py
| 1. Кастомный TextFSM      |  (QTech -> templates/*.textfsm)
| 2. NTC Templates           |  (Cisco/Arista -> ntc_templates)
+----------------------------+
    |
    |  Сырые данные TextFSM:
    |  {"interface": "Gi0/1", "link_status": "connected",
    |   "hardware_type": "Gigabit Ethernet", "mac_address": "0011.2233.4455"}
    v
+----------------------------+
| InterfaceNormalizer        |  core/domain/interface.py
| .normalize_dicts()         |
| .enrich_with_lag()         |
| .enrich_with_switchport()  |
+----------------------------+
    |
    |  Нормализованные данные:
    |  {"interface": "Gi0/1", "status": "up", "port_type": "1g-rj45",
    |   "mac": "0011.2233.4455", "mode": "access", "hostname": "sw-01"}
    v
+----------------------------+
| apply_fields_config()      |  fields_config.py
| fields.yaml: порядок,     |  переименование, фильтрация
| display names             |
+----------------------------+
    |
    |  Данные для экспорта:
    |  {"Device": "sw-01", "Port": "Gi0/1", "Status": "up",
    |   "Type": "1g-rj45", "Mode": "access"}
    v
+----------------------------+
| ExcelExporter._write()     |  exporters/excel.py
| openpyxl: заголовки,      |  автофильтр, цвета, авто-ширина
| форматирование            |
+----------------------------+
    |
    v
  reports/interfaces.xlsx
```

**Сводка по файлам:**

| Слой | Файлы | Ответственность |
|------|-------|-----------------|
| CLI | `cli/commands/collect.py`, `cli/utils.py` | Разбор аргументов, запуск |
| Collector | `collectors/base.py`, `collectors/interfaces.py` | SSH, параллельный сбор |
| Connection | `core/connection.py` | SSH через Scrapli, retry |
| Parser | `parsers/textfsm_parser.py` | TextFSM/NTC шаблоны |
| Domain | `core/domain/interface.py`, `core/domain/mac.py` | Нормализация, бизнес-логика |
| Constants | `core/constants/commands.py`, `core/constants/netbox.py` | Маппинги, команды |
| Config | `fields_config.py`, `fields.yaml` | Поля экспорта, display names |
| Export | `exporters/excel.py`, `exporters/csv_exporter.py` | Запись в файлы |

---

## Что дальше

- [04_DATA_COLLECTION.md](04_DATA_COLLECTION.md) -- обзор сбора данных (верхнеуровневый)
- [07_DATA_FLOWS.md](07_DATA_FLOWS.md) -- потоки данных: LLDP match, MAC match
- [05_SYNC_NETBOX.md](05_SYNC_NETBOX.md) -- как собранные данные синхронизируются с NetBox
- [03_CLI_INTERNALS.md](03_CLI_INTERNALS.md) -- как работает CLI от ввода до результата
