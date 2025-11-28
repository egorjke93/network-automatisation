# MAC Collector

Модуль для сбора MAC-адресов с сетевого оборудования разных вендоров.

## Возможности

- 📡 Сбор MAC-адресов из таблицы MAC и sticky port-security
- 🏭 Поддержка нескольких вендоров (Cisco, Arista, Juniper, Eltex)
- 📊 Экспорт в Excel с форматированием и цветовой индикацией
- 🔍 Фильтрация trunk портов и системных интерфейсов
- 📱 Определение статуса устройств (online/offline)
- ⚙️ Гибкие настройки формата MAC-адресов

## Установка

```bash
# Клонируем репозиторий
git clone https://github.com/your-username/mac-collector.git
cd mac-collector

# Устанавливаем зависимости
pip install -r requirements.txt
```

## Быстрый старт

### 1. Создайте файл devices_ips.py

Создайте файл `devices_ips.py` в корне проекта:

```python
# devices_ips.py
devices_list = [
    {
        "device_type": "cisco_ios",
        "host": "192.168.1.1",
    },
    {
        "device_type": "cisco_ios",
        "host": "192.168.1.2",
    },
    {
        "device_type": "arista_eos",
        "host": "192.168.1.10",
    },
]
```

> ⚠️ **Важно:** Логин и пароль запрашиваются при запуске скрипта, не храните их в файле!

### 2. Запустите сбор

```bash
python -m mac_collector.main
```

Скрипт запросит:
- Имя пользователя
- Пароль
- Enable пароль (опционально)

### 3. Результат

Файлы Excel сохраняются в папке `mac_reports/`:
```
mac_reports/
├── SW-CORE-01_2025-11-28.xlsx
├── SW-ACCESS-02_2025-11-28.xlsx
└── ...
```

## Настройки

Все настройки находятся в файле `mac_collector/config.py`:

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `EXCLUDE_TRUNK_PORTS` | Исключать trunk порты | `True` |
| `EXCLUDE_BY_NAME` | Исключать по имени интерфейса | `True` |
| `EXCLUDE_INTERFACE_PATTERNS` | Паттерны для исключения | `["CPU", "Po", "Vl"]` |
| `COLLECT_STICKY_MAC` | Собирать sticky MAC | `True` |
| `COLLECT_DYNAMIC_MAC` | Собирать dynamic MAC | `True` |
| `SAVE_PER_DEVICE` | Отдельный файл для каждого устройства | `True` |
| `OUTPUT_FOLDER` | Папка для Excel файлов | `"mac_reports"` |
| `MAC_FORMAT` | Формат MAC-адреса | `"colon"` |
| `SHOW_DEVICE_STATUS` | Показывать статус online/offline | `True` |

### Форматы MAC-адреса

| Значение | Пример |
|----------|--------|
| `colon` | `00:11:22:33:44:55` |
| `dash` | `00-11-22-33-44-55` |
| `cisco` | `0011.2233.4455` |
| `none` | `001122334455` |
| `original` | как получено с устройства |

## Поддерживаемые вендоры

| Вендор | device_type | Статус |
|--------|-------------|--------|
| Cisco IOS | `cisco_ios` | ✅ Полная поддержка |
| Cisco IOS-XE | `cisco_xe` | ✅ Полная поддержка |
| Cisco NX-OS | `cisco_nxos` | ✅ Полная поддержка |
| Arista EOS | `arista_eos` | ⚠️ Базовая поддержка |
| Juniper | `juniper` | ⚠️ Базовая поддержка |
| Eltex | `eltex` | ⚠️ Базовая поддержка |

## Добавление нового вендора

### 1. Создайте файл парсера

`mac_collector/parsers/huawei.py`:

```python
from .base import BaseParser

class HuaweiParser(BaseParser):
    """Парсер для Huawei устройств."""

    vendor_name = "Huawei"

    def _get_interfaces_command(self) -> str:
        return "display interface description"

    def _get_trunk_command(self) -> str:
        return "display port trunk"

    def _get_mac_table_command(self) -> str:
        return "display mac-address"

    def _get_running_config_command(self) -> str:
        return "display current-configuration"

    def parse_interfaces_description(self, output: str) -> dict:
        # Реализация парсинга
        pass

    # ... остальные методы
```

### 2. Зарегистрируйте парсер

В `mac_collector/parsers/__init__.py` добавьте:

```python
from .huawei import HuaweiParser

PARSER_MAP = {
    # ... существующие
    "huawei": HuaweiParser,
    "huawei_vrp": HuaweiParser,
}
```

### 3. Используйте

```python
# devices_ips.py
devices_list = [
    {
        "device_type": "huawei",
        "host": "192.168.1.100",
    },
]
```

## Структура Excel файла

| Столбец | Описание |
|---------|----------|
| Device | Hostname устройства |
| Interface | Имя интерфейса (короткое: Gi0/1) |
| Description | Описание интерфейса |
| MAC | MAC-адрес в выбранном формате |
| Type | Тип: `dynamic`, `static`, `sticky` |
| VLAN | Номер VLAN |
| Status | `online` / `offline` (если включено) |

### Цветовая индикация

| Цвет | Значение |
|------|----------|
| 🔴 Красный | Устройство offline (только в sticky) |
| 🟢 Зелёный | Sticky MAC + online |
| ⚪ Белый | Dynamic/Static MAC |

## Структура проекта

```
project/
├── devices_ips.py          # Список устройств (создаёте вы)
├── requirements.txt        # Зависимости
├── mac_collector/          # Модуль
│   ├── __init__.py
│   ├── config.py           # Настройки
│   ├── collector.py        # Логика сбора
│   ├── excel_writer.py     # Запись в Excel
│   ├── main.py             # Точка входа
│   ├── utils.py            # Утилиты
│   └── parsers/            # Парсеры вендоров
│       ├── base.py         # Базовый класс
│       ├── cisco.py        # Cisco
│       ├── arista.py       # Arista
│       ├── juniper.py      # Juniper
│       └── eltex.py        # Eltex
└── mac_reports/            # Результаты (создаётся автоматически)
```

## Логирование

Логи сохраняются в файл `mac_collector.log`.

## Требования

- Python 3.8+
- netmiko >= 4.0.0
- openpyxl >= 3.0.0

## Лицензия

MIT License

