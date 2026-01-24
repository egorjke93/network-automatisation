# Полный путь данных — Детальный разбор

Этот документ объясняет **каждый шаг** от ввода команды до результата.
Для каждой функции и класса — что делает, какие параметры, как связан с другими.

---

## Содержание

1. [Что происходит при вводе команды](#1-что-происходит-при-вводе-команды)
2. [Разбор команды (argparse)](#2-разбор-команды-argparse)
3. [Загрузка конфигурации](#3-загрузка-конфигурации)
4. [Загрузка списка устройств](#4-загрузка-списка-устройств)
5. [Получение credentials](#5-получение-credentials)
6. [Создание коллектора](#6-создание-коллектора)
7. [Подключение к устройству (SSH)](#7-подключение-к-устройству-ssh)
8. [Выполнение команды](#8-выполнение-команды)
9. [Парсинг вывода (NTC Templates)](#9-парсинг-вывода-ntc-templates)
10. [Нормализация (Domain Layer)](#10-нормализация-domain-layer)
11. [Фильтрация полей (fields.yaml)](#11-фильтрация-полей-fieldsyaml)
12. [Экспорт (Excel/CSV/JSON)](#12-экспорт-excelcsvjson)
13. [Полная диаграмма вызовов](#13-полная-диаграмма-вызовов)

---

## 1. Что происходит при вводе команды

### Команда

```bash
python -m network_collector mac --format excel --with-descriptions
```

### Шаг 1: Python ищет пакет

```
python -m network_collector
         ↓
Ищет папку network_collector/
         ↓
Находит __main__.py
         ↓
Выполняет его
```

### Шаг 2: `__main__.py`

```python
# network_collector/__main__.py
"""Точка входа при запуске python -m network_collector."""
from .cli import main

if __name__ == "__main__":
    main()
```

**Что происходит:**
1. Импортирует функцию `main` из `cli.py`
2. Вызывает `main()`

---

## 2. Разбор команды (argparse)

### Функция: `main()` в `cli.py`

```python
def main() -> None:
    """Главная функция CLI."""
    from .config import load_config, config
    from .core.context import RunContext, set_current_context
    from .core.logging import LogConfig, setup_logging_from_config

    # 1. Создаём парсер аргументов
    parser = setup_parser()

    # 2. Парсим аргументы командной строки
    args = parser.parse_args()
    # args теперь содержит:
    #   args.command = "mac"
    #   args.format = "excel"
    #   args.with_descriptions = True
    #   args.devices = "devices_ips.py"
    #   args.output = "reports"
    #   args.transport = "ssh2"
    #   ...

    # 3. Загружаем конфигурацию из config.yaml
    load_config(args.config)

    # 4. Создаём контекст выполнения (для логов, dry-run)
    ctx = RunContext.create(
        dry_run=getattr(args, "dry_run", False),
        triggered_by="cli",
        command=args.command or "",
    )
    set_current_context(ctx)

    # 5. Настраиваем логирование
    setup_logging_from_config(log_config)

    # 6. Маршрутизация на обработчик команды
    if args.command == "mac":
        cmd_mac(args, ctx)
    elif args.command == "devices":
        cmd_devices(args, ctx)
    # ... другие команды
```

### Функция: `setup_parser()` — создание парсера

```python
def setup_parser() -> argparse.ArgumentParser:
    """Создаёт парсер аргументов командной строки."""

    # Главный парсер
    parser = argparse.ArgumentParser(
        prog="network_collector",
        description="Утилита для сбора данных с сетевых устройств",
    )

    # Общие аргументы (доступны для всех команд)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--devices", default="devices_ips.py")
    parser.add_argument("-o", "--output", default="reports")
    parser.add_argument("--transport", choices=["ssh2", "paramiko"], default="ssh2")

    # Подкоманды
    subparsers = parser.add_subparsers(dest="command")

    # Команда "mac"
    mac_parser = subparsers.add_parser("mac", help="Сбор MAC-адресов")
    mac_parser.add_argument("--format", choices=["excel", "csv", "json", "raw"])
    mac_parser.add_argument("--with-descriptions", action="store_true")
    mac_parser.add_argument("--mac-format", choices=["ieee", "cisco", "unix"])
    # ...

    return parser
```

**Как работает argparse:**

```
python -m network_collector mac --format excel --with-descriptions
                            │         │                │
                            │         │                └─ action="store_true" → True
                            │         └─ choices=["excel",...] → "excel"
                            └─ dest="command" → "mac"
```

---

## 3. Загрузка конфигурации

### Функция: `load_config()`

```python
# config.py
def load_config(config_path: Optional[str] = None) -> None:
    """Загружает конфигурацию из YAML файла."""

    global config

    # Путь по умолчанию
    if config_path is None:
        config_path = "config.yaml"

    path = Path(config_path)

    if not path.exists():
        # Используем дефолтные значения
        config = Config()
        return

    # Читаем YAML
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Создаём объект конфигурации
    config = Config.from_dict(data)
```

### Структура config.yaml

```yaml
# config.yaml
output:
  output_folder: "reports"
  default_format: "excel"
  mac_format: "ieee"

connection:
  conn_timeout: 10
  read_timeout: 30
  max_retries: 2
  retry_delay: 5

filters:
  exclude_interfaces:
    - "^Po.*"      # Port-channel
    - "^Vlan.*"    # SVI
  exclude_vlans:
    - 1
    - 1000

mac:
  collect_descriptions: true
  collect_trunk_ports: false

netbox:
  url: "https://netbox.example.com"
  token: "${NETBOX_TOKEN}"  # Из env
```

### Класс Config (dataclass)

```python
@dataclass
class Config:
    """Конфигурация приложения."""
    output: OutputConfig = field(default_factory=OutputConfig)
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    mac: MACConfig = field(default_factory=MACConfig)
    netbox: NetBoxConfig = field(default_factory=NetBoxConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Создаёт Config из словаря."""
        return cls(
            output=OutputConfig(**data.get("output", {})),
            connection=ConnectionConfig(**data.get("connection", {})),
            # ...
        )
```

---

## 4. Загрузка списка устройств

### Функция: `load_devices()` в `cli.py`

```python
def load_devices(devices_file: str) -> List[Device]:
    """
    Загружает список устройств из Python файла.

    Args:
        devices_file: Путь к файлу (например "devices_ips.py")

    Returns:
        List[Device]: Список объектов Device
    """
    from .core.device import Device

    devices_path = Path(devices_file)

    # Проверяем существование файла
    if not devices_path.exists():
        # Ищем в директории модуля
        module_dir = Path(__file__).parent
        devices_path = module_dir / devices_file

    if not devices_path.exists():
        logger.error(f"Файл не найден: {devices_file}")
        sys.exit(1)

    # Динамический импорт Python файла
    import importlib.util

    spec = importlib.util.spec_from_file_location("devices", devices_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Теперь module — это импортированный Python модуль

    # Получаем переменную devices_list из файла
    devices_list = getattr(module, "devices_list", None)
    # devices_list = [{"host": "10.0.0.1", "platform": "cisco_ios"}, ...]

    # Конвертируем dict → Device объекты
    devices = []
    for d in devices_list:
        device = Device(
            host=d["host"],
            platform=d.get("platform", "cisco_ios"),
            port=d.get("port", 22),
        )
        devices.append(device)

    logger.info(f"Загружено устройств: {len(devices)}")
    return devices
```

### Файл devices_ips.py (пользовательский)

```python
# devices_ips.py
devices_list = [
    {"host": "10.0.0.1", "platform": "cisco_iosxe"},
    {"host": "10.0.0.2", "platform": "cisco_nxos"},
    {"host": "10.0.0.3", "platform": "arista_eos"},
]
```

### Класс Device (dataclass)

```python
# core/device.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any

class DeviceStatus(Enum):
    """Статус устройства."""
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"

@dataclass
class Device:
    """Модель сетевого устройства."""

    host: str                                    # IP или hostname
    platform: str = "cisco_ios"                  # Платформа для Scrapli
    port: int = 22                               # SSH порт
    device_type: Optional[str] = None            # Тип устройства
    role: Optional[str] = None                   # Роль (switch, router)
    status: DeviceStatus = DeviceStatus.UNKNOWN  # Текущий статус
    hostname: Optional[str] = None               # Hostname (заполняется при подключении)
    last_error: Optional[str] = None             # Последняя ошибка
    metadata: Dict[str, Any] = field(default_factory=dict)  # Дополнительные данные

    def __post_init__(self):
        """Вызывается после создания объекта."""
        # Нормализация платформы
        if not self.platform and self.device_type:
            self.platform = self._convert_device_type(self.device_type)

    @property
    def display_name(self) -> str:
        """Отображаемое имя: hostname или IP."""
        return self.hostname or self.host
```

---

## 5. Получение credentials

### Функция: `get_credentials()` в `cli.py`

```python
def get_credentials():
    """
    Получает учётные данные для подключения.

    Приоритет:
    1. Переменные окружения (NET_USERNAME, NET_PASSWORD)
    2. Интерактивный ввод
    """
    from .core.credentials import CredentialsManager

    creds_manager = CredentialsManager()
    return creds_manager.get_credentials()
```

### Класс CredentialsManager

```python
# core/credentials.py
import os
import getpass
from dataclasses import dataclass
from typing import Optional

@dataclass
class Credentials:
    """Учётные данные для подключения."""
    username: str
    password: str
    secret: Optional[str] = None  # Enable password

class CredentialsManager:
    """Менеджер учётных данных."""

    def get_credentials(self) -> Credentials:
        """Получает credentials из env или интерактивно."""

        # Пробуем переменные окружения
        username = os.environ.get("NET_USERNAME")
        password = os.environ.get("NET_PASSWORD")
        secret = os.environ.get("NET_SECRET")

        # Если нет в env — спрашиваем интерактивно
        if not username:
            username = input("Username: ")

        if not password:
            password = getpass.getpass("Password: ")
            # getpass скрывает ввод пароля в консоли

        return Credentials(
            username=username,
            password=password,
            secret=secret,
        )
```

---

## 6. Создание коллектора

### Функция: `cmd_mac()` — обработчик команды mac

```python
def cmd_mac(args, ctx=None) -> None:
    """Обработчик команды mac."""
    from .collectors import MACCollector
    from .config import config as app_config
    from .fields_config import apply_fields_config

    # 1. Подготовка: загрузка устройств и credentials
    devices, credentials = prepare_collection(args)
    # devices = [Device(...), Device(...), ...]
    # credentials = Credentials(username="admin", password="***")

    # 2. Определяем параметры из args и config
    mac_format = args.mac_format or app_config.output.mac_format
    # mac_format = "ieee"

    collect_descriptions = args.with_descriptions or app_config.mac.collect_descriptions
    # collect_descriptions = True

    # 3. Создаём коллектор
    collector = MACCollector(
        credentials=credentials,
        mac_format=mac_format,
        collect_descriptions=collect_descriptions,
        transport=args.transport,
    )
    # collector — экземпляр MACCollector с настройками

    # 4. Собираем данные
    data = collector.collect_dicts(devices)
    # data = [{"hostname": "sw1", "mac": "AA:BB:CC:DD:EE:FF", ...}, ...]

    # 5. Применяем фильтр полей
    data = apply_fields_config(data, "mac")

    # 6. Экспортируем
    exporter = get_exporter(args.format, args.output, args.delimiter)
    file_path = exporter.export(data, "mac_addresses")
    # file_path = "reports/2026-01-12_mac_addresses.xlsx"

    if file_path:
        logger.info(f"Отчёт сохранён: {file_path}")
```

### Вспомогательная функция: `prepare_collection()`

```python
def prepare_collection(args):
    """
    Подготавливает устройства и credentials для сбора данных.

    Args:
        args: Аргументы командной строки

    Returns:
        tuple: (devices, credentials)
    """
    devices = load_devices(args.devices)
    # [Device(host="10.0.0.1", ...), Device(host="10.0.0.2", ...)]

    credentials = get_credentials()
    # Credentials(username="admin", password="***")

    return devices, credentials
```

---

## 7. Подключение к устройству (SSH)

### Класс: MACCollector (наследует BaseCollector)

```python
# collectors/mac.py
class MACCollector(BaseCollector):
    """Коллектор MAC-адресов."""

    # Типизированная модель для результатов
    model_class = MACEntry

    # Команды для разных платформ
    platform_commands = {
        "cisco_ios": "show mac address-table",
        "cisco_iosxe": "show mac address-table",
        "cisco_nxos": "show mac address-table",
        "arista_eos": "show mac address-table",
    }

    def __init__(
        self,
        mac_format: str = "ieee",
        collect_descriptions: bool = False,
        **kwargs,
    ):
        # Вызываем конструктор родителя
        super().__init__(**kwargs)

        self.mac_format = mac_format
        self.collect_descriptions = collect_descriptions

        # Domain Layer: нормализатор MAC-данных
        self._normalizer = MACNormalizer(
            mac_format=self.mac_format,
            exclude_interfaces=["^Po.*", "^Vlan.*"],
        )
```

### Класс: BaseCollector — базовый класс

```python
# collectors/base.py
class BaseCollector(ABC):
    """Абстрактный базовый класс для коллекторов."""

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        use_ntc: bool = True,
        max_workers: int = 10,
        transport: str = "ssh2",
        max_retries: int = 2,
        retry_delay: int = 5,
    ):
        self.credentials = credentials
        self.use_ntc = use_ntc
        self.max_workers = max_workers

        # Создаём менеджер подключений
        self._conn_manager = ConnectionManager(
            transport=transport,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        # Создаём NTC парсер
        if self.use_ntc:
            self._parser = NTCParser()
```

### Метод: `collect_dicts()` — точка входа для сбора

```python
def collect_dicts(
    self,
    devices: List[Device],
    parallel: bool = True,
) -> List[Dict[str, Any]]:
    """
    Собирает данные как словари.

    Args:
        devices: Список устройств
        parallel: Параллельный сбор

    Returns:
        List[Dict]: Собранные данные
    """
    all_data = []

    if parallel and len(devices) > 1:
        # Параллельный сбор через ThreadPoolExecutor
        all_data = self._collect_parallel(devices)
    else:
        # Последовательный сбор
        for device in devices:
            data = self._collect_from_device(device)
            all_data.extend(data)

    logger.info(f"Собрано записей: {len(all_data)}")
    return all_data
```

### Метод: `_collect_parallel()` — параллельный сбор

```python
def _collect_parallel(self, devices: List[Device]) -> List[Dict]:
    """Параллельный сбор данных."""
    all_data = []

    # ThreadPoolExecutor создаёт пул потоков
    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
        # Создаём задачи для каждого устройства
        futures = {
            executor.submit(self._collect_from_device, device): device
            for device in devices
        }
        # futures = {Future1: Device1, Future2: Device2, ...}

        # Обрабатываем результаты по мере готовности
        for future in as_completed(futures):
            device = futures[future]
            try:
                data = future.result()  # Получаем результат
                all_data.extend(data)
            except Exception as e:
                logger.error(f"Ошибка на {device.host}: {e}")

    return all_data
```

### Метод: `_collect_from_device()` — сбор с одного устройства

```python
# collectors/mac.py (переопределяет метод из BaseCollector)
def _collect_from_device(self, device: Device) -> List[Dict]:
    """Собирает MAC-адреса с одного устройства."""

    command = self._get_command(device)
    # command = "show mac address-table"

    try:
        # Контекстный менеджер: автоматическое закрытие соединения
        with self._conn_manager.connect(device, self.credentials) as conn:
            # conn — активное SSH соединение (Scrapli)

            # 1. Получаем hostname из prompt
            hostname = self._conn_manager.get_hostname(conn)
            # hostname = "switch1"

            # 2. Выполняем команду show mac address-table
            mac_response = conn.send_command(command)
            mac_output = mac_response.result
            # mac_output = "Vlan    Mac Address       Type        Ports\n..."

            # 3. Получаем статус интерфейсов
            status_response = conn.send_command("show interfaces status")
            interface_status = self._parse_interface_status(status_response.result)
            # interface_status = {"Gi0/1": "connected", "Gi0/2": "notconnect"}

            # 4. Получаем описания если нужно
            descriptions = {}
            if self.collect_descriptions:
                desc_response = conn.send_command("show interfaces description")
                descriptions = self._parse_interface_descriptions(desc_response.result)

            # 5. Парсим MAC-таблицу (сырые данные)
            raw_data = self._parse_raw(mac_output, device)
            # raw_data = [{"vlan": "10", "mac": "aabb.ccdd.eeff", ...}, ...]

            # 6. Domain Layer: нормализация
            data = self._normalizer.normalize_dicts(
                raw_data,
                interface_status=interface_status,
                hostname=hostname,
                device_ip=device.host,
            )

            # 7. Добавляем описания
            if self.collect_descriptions:
                for row in data:
                    iface = row.get("interface", "")
                    row["description"] = descriptions.get(iface, "")

            logger.info(f"{hostname}: собрано {len(data)} MAC-адресов")
            return data

    except Exception as e:
        logger.error(f"Ошибка с {device.host}: {e}")
        return []
```

### Класс: ConnectionManager — управление SSH

```python
# core/connection.py
class ConnectionManager:
    """Менеджер SSH подключений через Scrapli."""

    def __init__(
        self,
        timeout_socket: int = 15,
        timeout_transport: int = 30,
        transport: str = "ssh2",
        max_retries: int = 2,
        retry_delay: int = 5,
    ):
        self.timeout_socket = timeout_socket
        self.timeout_transport = timeout_transport
        self.transport = transport
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    @contextmanager
    def connect(
        self,
        device: Device,
        credentials: Credentials,
    ) -> Generator[Scrapli, None, None]:
        """
        Контекстный менеджер для подключения с retry.

        Использование:
            with manager.connect(device, creds) as conn:
                result = conn.send_command("show version")
        """
        connection = None
        last_error = None

        # Параметры для Scrapli
        params = {
            "host": device.host,
            "auth_username": credentials.username,
            "auth_password": credentials.password,
            "platform": get_scrapli_platform(device.platform),
            "transport": self.transport,
            "auth_strict_key": False,  # Не проверять ключи SSH
            "timeout_socket": self.timeout_socket,
            "timeout_transport": self.timeout_transport,
        }

        total_attempts = 1 + self.max_retries  # 1 + 2 = 3 попытки

        for attempt in range(1, total_attempts + 1):
            try:
                logger.info(f"Подключение к {device.host}...")

                # Создаём и открываем соединение
                connection = Scrapli(**params)
                connection.open()

                # Успешное подключение
                device.status = DeviceStatus.ONLINE
                device.hostname = self.get_hostname(connection)

                try:
                    yield connection  # Передаём соединение в with блок
                finally:
                    # Закрываем при выходе из with
                    if connection:
                        connection.close()
                return  # Успешно завершено

            except ScrapliAuthenticationFailed as e:
                # Ошибка пароля — НЕ повторяем
                raise AuthenticationError(f"Ошибка аутентификации: {e}")

            except ScrapliTimeout as e:
                # Таймаут — пробуем ещё раз
                last_error = e
                if attempt < total_attempts:
                    logger.warning(f"Таймаут, повтор через {self.retry_delay}с...")
                    time.sleep(self.retry_delay)

            except ScrapliConnectionError as e:
                # Ошибка подключения — пробуем ещё раз
                last_error = e
                if attempt < total_attempts:
                    logger.warning(f"Ошибка, повтор через {self.retry_delay}с...")
                    time.sleep(self.retry_delay)

        # Все попытки исчерпаны
        raise ConnectionError(f"Не удалось подключиться: {last_error}")

    @staticmethod
    def get_hostname(connection: Scrapli) -> str:
        """Получает hostname из prompt."""
        prompt = connection.get_prompt()
        # prompt = "switch1#" или "switch1>"
        hostname = re.sub(r"[#>$\s]+$", "", prompt).strip()
        # hostname = "switch1"
        return hostname
```

---

## 8. Выполнение команды

### Scrapli: отправка команды

```python
# Внутри with self._conn_manager.connect(...) as conn:

response = conn.send_command("show mac address-table")
# response — объект Response от Scrapli

output = response.result
# output — текстовый вывод команды
```

### Пример вывода команды

```
switch1#show mac address-table
          Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
   1    0011.2233.4455    DYNAMIC     Gi0/1
  10    aabb.ccdd.eeff    DYNAMIC     Gi0/2
  10    1122.3344.5566    STATIC      Gi0/3
  20    dead.beef.cafe    DYNAMIC     Gi0/4
```

---

## 9. Парсинг вывода (NTC Templates)

### Метод: `_parse_raw()` — парсинг MAC-таблицы

```python
def _parse_raw(self, output: str, device: Device) -> List[Dict]:
    """Парсит вывод show mac address-table."""

    # Пробуем NTC Templates
    if self.use_ntc:
        data = self._parse_with_ntc(output, device)
        if data:
            return data

    # Fallback на regex
    return self._parse_with_regex_raw(output, device)
```

### Метод: `_parse_with_ntc()` — NTC Templates парсинг

```python
def _parse_with_ntc(
    self,
    output: str,
    device: Device,
    command: Optional[str] = None,
) -> List[Dict]:
    """Парсит вывод через NTC Templates."""

    cmd = command or self._get_command(device)
    # cmd = "show mac address-table"

    # Конвертируем платформу в формат NTC
    ntc_platform = get_ntc_platform(device.platform)
    # device.platform = "cisco_iosxe" → ntc_platform = "cisco_ios"

    try:
        return self._parser.parse(
            output=output,
            platform=ntc_platform,
            command=cmd,
        )
    except Exception as e:
        logger.warning(f"NTC парсинг не удался: {e}")
        return []
```

### Класс: NTCParser

```python
# parsers/textfsm_parser.py
from ntc_templates.parse import parse_output

class NTCParser:
    """Парсер на базе NTC Templates."""

    def parse(
        self,
        output: str,
        platform: str,
        command: str,
        fields: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Парсит вывод команды через NTC Templates.

        Args:
            output: Сырой текст вывода
            platform: Платформа (cisco_ios, arista_eos, etc.)
            command: Команда (show mac address-table, etc.)
            fields: Поля для извлечения (опционально)

        Returns:
            List[Dict]: Распарсенные данные
        """
        # NTC Templates делает магию:
        # - Находит шаблон для platform + command
        # - Парсит текст по шаблону
        # - Возвращает список словарей

        parsed = parse_output(
            platform=platform,
            command=command,
            data=output,
        )
        # parsed = [
        #     {"destination_address": "0011.2233.4455", "destination_port": "Gi0/1", "vlan": "1", "type": "DYNAMIC"},
        #     {"destination_address": "aabb.ccdd.eeff", "destination_port": "Gi0/2", "vlan": "10", "type": "DYNAMIC"},
        #     ...
        # ]

        # Фильтруем поля если указаны
        if fields:
            parsed = [
                {k: v for k, v in row.items() if k in fields}
                for row in parsed
            ]

        return parsed
```

### Как работает NTC Templates внутри

```
Вход (текст):
"   1    0011.2233.4455    DYNAMIC     Gi0/1"

                    ↓

Шаблон TextFSM (cisco_ios_show_mac_address-table.textfsm):
Value DESTINATION_ADDRESS ([0-9a-fA-F.]+)
Value DESTINATION_PORT (\S+)
Value VLAN (\d+)
Value TYPE (\S+)

Start
  ^${VLAN}\s+${DESTINATION_ADDRESS}\s+${TYPE}\s+${DESTINATION_PORT} -> Record

                    ↓

Выход (словарь):
{"destination_address": "0011.2233.4455", "destination_port": "Gi0/1", "vlan": "1", "type": "DYNAMIC"}
```

---

## 10. Нормализация (Domain Layer)

### Зачем нормализация

**Проблема:** NTC Templates возвращает разные имена полей для разных платформ.

```python
# Cisco IOS (NTC)
{"destination_address": "0011.2233.4455", "destination_port": "Gi0/1"}

# Cisco NX-OS (NTC)
{"mac_address": "0011.2233.4455", "port": "Eth1/1"}

# Arista (NTC)
{"mac": "00:11:22:33:44:55", "interface": "Et1"}
```

**Решение:** MACNormalizer приводит к единому формату.

```python
# После нормализации — единый формат
{
    "hostname": "switch1",
    "device_ip": "10.0.0.1",
    "mac": "00:11:22:33:44:55",      # Единый формат MAC
    "interface": "Gi0/1",            # Короткое имя
    "vlan": "10",
    "type": "dynamic",
    "status": "online",              # Добавлен статус порта
}
```

### Класс: MACNormalizer (Domain Layer)

```python
# core/domain/mac.py
class MACNormalizer:
    """Нормализация MAC-таблицы."""

    def __init__(
        self,
        mac_format: str = "ieee",
        normalize_interfaces: bool = True,
        exclude_interfaces: Optional[List[str]] = None,
        exclude_vlans: Optional[List[int]] = None,
    ):
        self.mac_format = mac_format
        self.normalize_interfaces = normalize_interfaces
        self.exclude_interfaces = exclude_interfaces or []
        self.exclude_vlans = exclude_vlans or []

        # Компилируем regex паттерны для быстрой проверки
        self._exclude_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.exclude_interfaces
        ]

    def normalize_dicts(
        self,
        data: List[Dict],
        interface_status: Optional[Dict[str, str]] = None,
        hostname: str = "",
        device_ip: str = "",
    ) -> List[Dict]:
        """
        Нормализует список сырых данных.

        Args:
            data: Сырые данные от NTC
            interface_status: {interface: status} для определения online/offline
            hostname: Hostname устройства
            device_ip: IP устройства

        Returns:
            List[Dict]: Нормализованные данные
        """
        interface_status = interface_status or {}
        result = []
        seen_macs = set()  # Для дедупликации

        for row in data:
            # Нормализуем одну запись
            normalized = self._normalize_row(row, interface_status)

            if normalized is None:
                continue  # Отфильтрован (excluded interface/vlan)

            # Дедупликация по (mac, vlan, interface)
            mac_raw = normalize_mac_raw(normalized.get("mac", ""))
            key = (mac_raw, normalized.get("vlan"), normalized.get("interface"))
            if key in seen_macs:
                continue
            seen_macs.add(key)

            # Добавляем контекст
            if hostname:
                normalized["hostname"] = hostname
            if device_ip:
                normalized["device_ip"] = device_ip

            result.append(normalized)

        return result

    def _normalize_row(
        self,
        row: Dict,
        interface_status: Dict[str, str],
    ) -> Optional[Dict]:
        """
        Нормализует одну запись.

        Args:
            row: Сырые данные от NTC
            interface_status: Статусы интерфейсов

        Returns:
            Dict или None если отфильтрован
        """
        result = dict(row)

        # 1. Нормализуем интерфейс
        # NTC может вернуть: destination_port, port, interface
        interface = row.get("interface", row.get("destination_port", row.get("port", "")))

        if self.normalize_interfaces:
            interface = normalize_interface_short(interface)
            # "GigabitEthernet0/1" → "Gi0/1"

        result["interface"] = interface

        # 2. Проверяем исключения по интерфейсу
        if self._should_exclude_interface(interface):
            return None  # Исключаем Po, Vlan, etc.

        # 3. Нормализуем VLAN
        vlan = str(row.get("vlan", row.get("vlan_id", "")))

        try:
            if int(vlan) in self.exclude_vlans:
                return None  # Исключаем VLAN 1, 1000, etc.
        except ValueError:
            pass

        result["vlan"] = vlan

        # 4. Нормализуем MAC
        mac = row.get("mac", row.get("destination_address", ""))
        normalized_mac = normalize_mac(mac, format=self.mac_format)
        # "aabb.ccdd.eeff" → "AA:BB:CC:DD:EE:FF" (ieee)
        result["mac"] = normalized_mac if normalized_mac else mac

        # 5. Нормализуем тип
        raw_type = str(row.get("type", "")).lower()
        result["type"] = "dynamic" if "dynamic" in raw_type else "static"

        # 6. Определяем статус порта
        port_status = interface_status.get(interface, "")
        if port_status.lower() in ["connected", "up"]:
            result["status"] = "online"
        elif port_status:
            result["status"] = "offline"
        else:
            result["status"] = "unknown"

        return result

    def _should_exclude_interface(self, interface: str) -> bool:
        """Проверяет, нужно ли исключить интерфейс."""
        for pattern in self._exclude_patterns:
            if pattern.match(interface):
                return True  # ^Po.*, ^Vlan.*
        return False
```

### Вспомогательные функции нормализации

```python
# core/constants.py

def normalize_interface_short(interface: str) -> str:
    """
    Сокращает имя интерфейса.

    Examples:
        "GigabitEthernet0/1" → "Gi0/1"
        "FastEthernet0/24" → "Fa0/24"
        "TenGigabitEthernet1/0/1" → "Te1/0/1"
    """
    replacements = [
        ("GigabitEthernet", "Gi"),
        ("FastEthernet", "Fa"),
        ("TenGigabitEthernet", "Te"),
        ("TwentyFiveGigE", "Twe"),
        ("FortyGigabitEthernet", "Fo"),
        ("HundredGigE", "Hu"),
        ("Ethernet", "Eth"),
        ("Port-channel", "Po"),
    ]

    result = interface
    for long_name, short_name in replacements:
        if result.startswith(long_name):
            result = result.replace(long_name, short_name, 1)
            break

    return result


def normalize_mac(mac: str, format: str = "ieee") -> str:
    """
    Нормализует MAC-адрес в указанный формат.

    Args:
        mac: MAC-адрес в любом формате
        format: Целевой формат (ieee, cisco, unix)

    Returns:
        str: Нормализованный MAC

    Examples:
        "aabb.ccdd.eeff" → "AA:BB:CC:DD:EE:FF" (ieee)
        "AA:BB:CC:DD:EE:FF" → "aabb.ccdd.eeff" (cisco)
        "AA:BB:CC:DD:EE:FF" → "aa:bb:cc:dd:ee:ff" (unix)
    """
    # Убираем все разделители
    mac_clean = mac.replace(".", "").replace(":", "").replace("-", "").upper()

    if len(mac_clean) != 12:
        return mac  # Некорректный MAC

    if format == "ieee":
        # AA:BB:CC:DD:EE:FF
        return ":".join(mac_clean[i:i+2] for i in range(0, 12, 2))

    elif format == "cisco":
        # aabb.ccdd.eeff
        mac_lower = mac_clean.lower()
        return ".".join(mac_lower[i:i+4] for i in range(0, 12, 4))

    elif format == "unix":
        # aa:bb:cc:dd:ee:ff
        return ":".join(mac_clean[i:i+2].lower() for i in range(0, 12, 2))

    return mac
```

---

## 11. Фильтрация полей (fields.yaml)

### Функция: `apply_fields_config()`

```python
# fields_config.py
def apply_fields_config(data: List[Dict], data_type: str) -> List[Dict]:
    """
    Применяет конфигурацию полей из fields.yaml.

    Args:
        data: Исходные данные
        data_type: Тип данных (mac, lldp, devices, etc.)

    Returns:
        List[Dict]: Данные с отфильтрованными/переименованными полями
    """
    config = load_fields_config()
    # config = {"mac": {"hostname": {...}, "mac": {...}, ...}, ...}

    if data_type not in config:
        return data  # Нет конфига для этого типа

    field_config = config[data_type]
    # field_config = {
    #     "hostname": {"enabled": true, "name": "DEVICE", "order": 1},
    #     "mac": {"enabled": true, "name": "MAC", "order": 2},
    #     "vlan": {"enabled": false},
    #     ...
    # }

    # Фильтруем и переименовываем
    result = []

    for row in data:
        new_row = {}

        for field, settings in sorted(field_config.items(), key=lambda x: x[1].get("order", 999)):
            if not settings.get("enabled", True):
                continue  # Поле отключено

            if field not in row:
                continue  # Поля нет в данных

            # Переименовываем если указано
            output_name = settings.get("name", field)
            new_row[output_name] = row[field]

        result.append(new_row)

    return result
```

### Файл fields.yaml

```yaml
# fields.yaml
mac:
  hostname:
    enabled: true
    name: "DEVICE"
    order: 1
  device_ip:
    enabled: true
    name: "IP"
    order: 2
  interface:
    enabled: true
    name: "PORT"
    order: 3
  mac:
    enabled: true
    name: "MAC"
    order: 4
  vlan:
    enabled: false  # Не включать в экспорт
  status:
    enabled: true
    name: "STATUS"
    order: 5
  description:
    enabled: true
    name: "DESCRIPTION"
    order: 6
```

### Результат фильтрации

```python
# До apply_fields_config:
{"hostname": "sw1", "device_ip": "10.0.0.1", "interface": "Gi0/1", "mac": "AA:BB:CC:DD:EE:FF", "vlan": "10", "status": "online"}

# После apply_fields_config:
{"DEVICE": "sw1", "IP": "10.0.0.1", "PORT": "Gi0/1", "MAC": "AA:BB:CC:DD:EE:FF", "STATUS": "online"}
# vlan убран (enabled: false)
# Поля переименованы согласно "name"
# Порядок согласно "order"
```

---

## 12. Экспорт (Excel/CSV/JSON)

### Функция: `get_exporter()` — фабрика экспортеров

```python
def get_exporter(format_type: str, output_folder: str, delimiter: str = ","):
    """
    Возвращает экспортер по типу формата.

    Паттерн "Фабрика" — создаёт объекты без указания конкретного класса.
    """
    from .exporters import CSVExporter, JSONExporter, ExcelExporter, RawExporter

    if format_type == "csv":
        return CSVExporter(output_folder=output_folder, delimiter=delimiter)
    elif format_type == "json":
        return JSONExporter(output_folder=output_folder)
    elif format_type == "raw":
        return RawExporter()  # Вывод в stdout
    else:
        return ExcelExporter(output_folder=output_folder)
```

### Класс: BaseExporter — базовый класс

```python
# exporters/base.py
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

class BaseExporter(ABC):
    """Абстрактный базовый класс для экспортеров."""

    file_extension = ""  # Переопределяется в наследниках

    def __init__(
        self,
        output_folder: str = "reports",
        encoding: str = "utf-8",
    ):
        self.output_folder = Path(output_folder)
        self.encoding = encoding

    def export(
        self,
        data: List[Dict[str, Any]],
        filename: str,
    ) -> Optional[str]:
        """
        Экспортирует данные в файл.

        Args:
            data: Данные для экспорта
            filename: Имя файла (без расширения)

        Returns:
            str: Путь к созданному файлу или None
        """
        if not data:
            return None

        # Создаём папку
        self.output_folder.mkdir(parents=True, exist_ok=True)

        # Формируем путь: reports/2026-01-12_mac_addresses.xlsx
        timestamp = datetime.now().strftime("%Y-%m-%d")
        file_path = self.output_folder / f"{timestamp}_{filename}{self.file_extension}"

        # Вызываем абстрактный метод записи
        self._write(data, file_path)

        return str(file_path)

    @abstractmethod
    def _write(self, data: List[Dict], file_path: Path) -> None:
        """Записывает данные в файл. Реализуется в наследниках."""
        pass

    def _get_all_columns(self, data: List[Dict]) -> List[str]:
        """Получает все уникальные колонки из данных."""
        columns = []
        seen = set()

        for row in data:
            for key in row.keys():
                if key not in seen:
                    columns.append(key)
                    seen.add(key)

        return columns
```

### Класс: ExcelExporter

```python
# exporters/excel.py
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

class ExcelExporter(BaseExporter):
    """Экспортер в Excel с форматированием."""

    file_extension = ".xlsx"

    def __init__(
        self,
        output_folder: str = "reports",
        autofilter: bool = True,
        freeze_header: bool = True,
        auto_width: bool = True,
    ):
        super().__init__(output_folder)
        self.autofilter = autofilter
        self.freeze_header = freeze_header
        self.auto_width = auto_width

        # Стили
        self.header_font = Font(bold=True, color="FFFFFF")
        self.header_fill = PatternFill(start_color="4472C4", fill_type="solid")

    def _write(self, data: List[Dict], file_path: Path) -> None:
        """Записывает данные в Excel файл."""

        # Создаём книгу и лист
        wb = Workbook()
        ws = wb.active
        ws.title = "Data"

        # Получаем колонки
        columns = self._get_all_columns(data)
        # columns = ["DEVICE", "IP", "PORT", "MAC", "STATUS"]

        # Заголовок (строка 1)
        for col_idx, column in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=column.upper())
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.alignment = Alignment(horizontal="center")

        # Данные (строки 2+)
        for row_idx, row in enumerate(data, start=2):
            for col_idx, column in enumerate(columns, start=1):
                value = row.get(column, "")
                cell = ws.cell(row=row_idx, column=col_idx, value=value)

                # Цветовая индикация для status
                if column.lower() == "status":
                    if str(value).lower() == "online":
                        cell.fill = PatternFill(start_color="C6EFCE", fill_type="solid")
                    elif str(value).lower() == "offline":
                        cell.fill = PatternFill(start_color="FFC7CE", fill_type="solid")

        # Автофильтр
        if self.autofilter:
            ws.auto_filter.ref = ws.dimensions

        # Закрепить заголовок
        if self.freeze_header:
            ws.freeze_panes = "A2"

        # Автоширина колонок
        if self.auto_width:
            for col_idx, column in enumerate(columns, start=1):
                max_length = max(
                    len(str(row.get(column, ""))) for row in data
                )
                max_length = max(max_length, len(column))
                ws.column_dimensions[get_column_letter(col_idx)].width = min(max_length + 2, 50)

        # Сохраняем
        wb.save(file_path)
```

### Результат экспорта

```
reports/2026-01-12_mac_addresses.xlsx

┌────────┬───────────┬────────┬───────────────────┬────────┐
│ DEVICE │ IP        │ PORT   │ MAC               │ STATUS │
├────────┼───────────┼────────┼───────────────────┼────────┤
│ sw1    │ 10.0.0.1  │ Gi0/1  │ AA:BB:CC:DD:EE:FF │ online │  (зелёный)
│ sw1    │ 10.0.0.1  │ Gi0/2  │ 11:22:33:44:55:66 │ offline│  (красный)
│ sw2    │ 10.0.0.2  │ Eth1/1 │ DE:AD:BE:EF:CA:FE │ online │  (зелёный)
└────────┴───────────┴────────┴───────────────────┴────────┘
```

---

## 13. Полная диаграмма вызовов

```
python -m network_collector mac --format excel --with-descriptions
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  __main__.py                                                         │
│    from .cli import main                                             │
│    main()                                                            │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  cli.main()                                                          │
│    1. parser = setup_parser()                                        │
│    2. args = parser.parse_args()                                     │
│    3. load_config(args.config)                                       │
│    4. ctx = RunContext.create(...)                                   │
│    5. setup_logging_from_config(...)                                 │
│    6. cmd_mac(args, ctx)  ──────────────────────────────────────────┼───┐
└─────────────────────────────────────────────────────────────────────┘   │
                                                                          │
┌─────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────┐
│  cmd_mac(args, ctx)                                                  │
│    1. devices, credentials = prepare_collection(args)                │
│       ├── load_devices("devices_ips.py")                             │
│       │     └── [Device(host="10.0.0.1", ...), ...]                  │
│       └── get_credentials()                                          │
│             └── Credentials(username="admin", password="***")        │
│                                                                      │
│    2. collector = MACCollector(                                      │
│           credentials=credentials,                                   │
│           mac_format="ieee",                                         │
│           collect_descriptions=True,                                 │
│       )                                                              │
│                                                                      │
│    3. data = collector.collect_dicts(devices) ──────────────────────┼───┐
│                                                                      │   │
│    4. data = apply_fields_config(data, "mac")                        │   │
│                                                                      │   │
│    5. exporter = get_exporter("excel", "reports", ",")               │   │
│    6. file_path = exporter.export(data, "mac_addresses")             │   │
└─────────────────────────────────────────────────────────────────────┘   │
                                                                          │
┌─────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────┐
│  MACCollector.collect_dicts(devices)                                 │
│    1. all_data = []                                                  │
│    2. for device in devices:                                         │
│           data = self._collect_from_device(device) ─────────────────┼───┐
│           all_data.extend(data)                                      │   │
│    3. return all_data                                                │   │
└─────────────────────────────────────────────────────────────────────┘   │
                                                                          │
┌─────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────┐
│  MACCollector._collect_from_device(device)                           │
│                                                                      │
│    with self._conn_manager.connect(device, credentials) as conn:     │
│    ┌────────────────────────────────────────────────────────────────┼───┐
│    │  ConnectionManager.connect()                                    │   │
│    │    1. params = _build_connection_params(device, credentials)    │   │
│    │    2. connection = Scrapli(**params)                            │   │
│    │    3. connection.open()  # SSH подключение                      │   │
│    │    4. yield connection                                          │   │
│    │    5. connection.close()  # Автоматически при выходе            │   │
│    └────────────────────────────────────────────────────────────────┼───┘
│                                                                      │
│        hostname = self._conn_manager.get_hostname(conn)              │
│        # hostname = "switch1"                                        │
│                                                                      │
│        mac_response = conn.send_command("show mac address-table")    │
│        # mac_output = "Vlan    Mac Address       Type        Ports..." │
│                                                                      │
│        raw_data = self._parse_raw(mac_output, device) ──────────────┼───┐
│                                                                      │   │
│        data = self._normalizer.normalize_dicts(raw_data, ...) ──────┼───┼───┐
│                                                                      │   │   │
│        return data                                                   │   │   │
└─────────────────────────────────────────────────────────────────────┘   │   │
                                                                          │   │
┌─────────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
▼                                                                             │
┌─────────────────────────────────────────────────────────────────────┐       │
│  MACCollector._parse_raw(output, device)                             │       │
│                                                                      │       │
│    if self.use_ntc:                                                  │       │
│        data = self._parse_with_ntc(output, device)                   │       │
│        ┌────────────────────────────────────────────────────────┐    │       │
│        │  NTCParser.parse(output, platform, command)             │    │       │
│        │    parsed = parse_output(platform, command, data=output)│    │       │
│        │    # NTC Templates: текст → список словарей              │    │       │
│        │    return parsed                                         │    │       │
│        └────────────────────────────────────────────────────────┘    │       │
│                                                                      │       │
│    return data  # [{"destination_address": "aabb.ccdd...", ...}]     │       │
└─────────────────────────────────────────────────────────────────────┘       │
                                                                              │
┌─────────────────────────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────────────────┐
│  MACNormalizer.normalize_dicts(data, interface_status, hostname)     │
│                                                                      │
│    result = []                                                       │
│    for row in data:                                                  │
│        normalized = self._normalize_row(row, interface_status)       │
│        ┌────────────────────────────────────────────────────────┐    │
│        │  _normalize_row(row):                                   │    │
│        │    1. interface = normalize_interface_short(...)        │    │
│        │       # "GigabitEthernet0/1" → "Gi0/1"                  │    │
│        │                                                         │    │
│        │    2. mac = normalize_mac(row["mac"], format="ieee")    │    │
│        │       # "aabb.ccdd.eeff" → "AA:BB:CC:DD:EE:FF"          │    │
│        │                                                         │    │
│        │    3. status = "online" if port connected else "offline"│    │
│        │                                                         │    │
│        │    4. return {                                          │    │
│        │         "interface": "Gi0/1",                           │    │
│        │         "mac": "AA:BB:CC:DD:EE:FF",                     │    │
│        │         "vlan": "10",                                   │    │
│        │         "status": "online",                             │    │
│        │         ...                                             │    │
│        │       }                                                 │    │
│        └────────────────────────────────────────────────────────┘    │
│                                                                      │
│        normalized["hostname"] = hostname  # "switch1"                │
│        normalized["device_ip"] = device_ip  # "10.0.0.1"             │
│        result.append(normalized)                                     │
│                                                                      │
│    return result                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Итоговый поток данных

```
Вход: python -m network_collector mac --format excel

    ┌─────────────────┐
    │  devices_ips.py │  ← Пользовательский файл
    │  [{"host": ...}]│
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ List[Device]    │  ← Python объекты
    │ Device(host=..) │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │    SSH/Scrapli  │  ← Подключение
    │  connect(device)│
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ send_command()  │  ← Выполнение
    │ "show mac..."   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  Сырой текст    │  ← Текст от устройства
    │  "Vlan  Mac..." │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │  NTC Templates  │  ← Парсинг
    │  parse_output() │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ [{"dest_addr":  │  ← Сырые данные
    │    "aabb..."    │     (разные имена полей)
    │  }]             │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ MACNormalizer   │  ← Domain Layer
    │ normalize_dicts │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ [{"mac":        │  ← Нормализованные
    │   "AA:BB:...",  │     данные (единый формат)
    │   "status":...  │
    │  }]             │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │apply_fields_cfg │  ← Фильтр полей
    │ fields.yaml     │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ [{"DEVICE":..., │  ← Финальные данные
    │   "MAC":...,    │     (переименованные)
    │   "STATUS":...  │
    │  }]             │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ ExcelExporter   │  ← Экспорт
    │ export()        │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ .xlsx файл      │  ← Результат
    │ с форматами     │
    └─────────────────┘
```

---

## Заключение

Теперь ты понимаешь каждый шаг:

| Шаг | Класс/Функция | Что делает |
|-----|---------------|------------|
| 1 | `__main__.py` | Вызывает `cli.main()` |
| 2 | `setup_parser()` | Создаёт argparse парсер |
| 3 | `load_config()` | Читает config.yaml |
| 4 | `load_devices()` | Импортирует devices_ips.py |
| 5 | `get_credentials()` | Получает username/password |
| 6 | `MACCollector()` | Создаёт коллектор с настройками |
| 7 | `ConnectionManager.connect()` | SSH подключение через Scrapli |
| 8 | `conn.send_command()` | Выполняет команду |
| 9 | `NTCParser.parse()` | Парсит текст в словари |
| 10 | `MACNormalizer.normalize_dicts()` | Приводит к единому формату |
| 11 | `apply_fields_config()` | Фильтрует и переименовывает поля |
| 12 | `ExcelExporter.export()` | Создаёт .xlsx файл |

**Ключевые паттерны:**
- **Контекстный менеджер** (`with ... as conn`) — автоматическое закрытие ресурсов
- **Абстрактный класс** (`BaseCollector`, `BaseExporter`) — единый интерфейс
- **Фабрика** (`get_exporter()`) — создание объектов по типу
- **Domain Layer** (`MACNormalizer`) — бизнес-логика отдельно от инфраструктуры
- **Dataclass** (`Device`, `Credentials`) — структуры данных с типизацией
