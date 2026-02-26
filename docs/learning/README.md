# Обучающая документация Network Collector

## Для кого

Ты -- сетевой инженер, который знает основы Python на уровне книги Мэтью Мэтиза (или аналогичной). Ты уже умеешь:

- Создавать переменные и работать с типами данных (строки, числа, списки, словари)
- Писать циклы `for` и `while`
- Создавать функции с `def`
- Создавать простые классы с `__init__` и методами

Этого достаточно, чтобы читать код проекта. Но в Network Collector используются продвинутые возможности Python, которые в базовых книгах обычно не разбирают. Эта серия документов объяснит их простым языком, с примерами прямо из кода проекта.

## Что нужно знать заранее

Убедись, что ты понимаешь:

| Тема | Пример | Где из книги |
|------|--------|--------------|
| Переменные | `name = "switch-01"` | Глава 2-3 |
| Списки | `devices = ["sw1", "sw2", "sw3"]` | Глава 4-5 |
| Словари | `device = {"name": "sw1", "ip": "10.0.0.1"}` | Глава 5-6 |
| Циклы for | `for d in devices: print(d)` | Глава 4-5 |
| Функции | `def connect(host): ...` | Глава 7-8 |
| Классы | `class Switch: def __init__(self): ...` | Глава 9-10 |

Если что-то из этого непонятно -- сначала повтори по книге, потом возвращайся.

## Порядок чтения

Документы пронумерованы. Читай последовательно -- каждый следующий опирается на предыдущие.

| # | Документ | Что узнаешь | Время |
|---|----------|-------------|-------|
| 01 | [Python-концепции в проекте](01_PYTHON_BASICS.md) | Словари, comprehensions, dataclass, type hints, наследование, mixin-классы, менеджеры контекста, обработка ошибок, модули, полезные паттерны | ~45 мин |
| 02 | [Обзор проекта](02_PROJECT_OVERVIEW.md) | Зачем нужен проект, что такое NetBox, архитектура и слои, структура папок, быстрый старт | ~20 мин |
| 03 | [CLI изнутри](03_CLI_INTERNALS.md) | Как работает CLI: argparse, маршрутизация команд, путь от ввода до результата, как добавить свою команду | ~30 мин |
| 04 | [Сбор данных](04_DATA_COLLECTION.md) | SSH-подключение (Scrapli), команды, TextFSM-парсинг, нормализация, модели данных | ~20 мин |
| 05 | [Синхронизация с NetBox](05_SYNC_NETBOX.md) | Mixin-архитектура, batch API, кэширование, dry_run, domain layer | ~35 мин |
| 06 | [Pipeline -- автоматизация](06_PIPELINE.md) | Pipeline: executor, auto-collect, cleanup, YAML конфиги | ~25 мин |
| 07 | [Потоки данных](07_DATA_FLOWS.md) | Полный путь данных: LLDP, MAC match, interfaces, IP, inventory | ~25 мин |
| 08 | [Web-архитектура](08_WEB_ARCHITECTURE.md) | FastAPI backend, Vue.js frontend, REST API, async mode | ~30 мин |
| 09 | [Mixins и архитектурные паттерны](09_MIXINS_PATTERNS.md) | Mixin-паттерн, composition vs DI, self: SyncBase, MRO, вопросы для собеседования | ~25 мин |

**Итого:** примерно 4-4.5 часа на всю серию.

## Глубокое изучение кода (Deep Dive)

После прочтения серии 01-09 ты понимаешь архитектуру и концепции. Документы 10-12 — это следующий уровень: разбор **каждого модуля строка за строкой**, с реальным кодом и трансформациями данных на каждом шаге.

| # | Документ | Что узнаешь | Время |
|---|----------|-------------|-------|
| 10 | [Collectors Deep Dive](10_COLLECTORS_DEEP_DIVE.md) | Полная цепочка сбора: CLI → BaseCollector → SSH → TextFSM → Normalizer → Exporter. Каждый коллектор, каждый нормализатор, каждый экспортер | ~60 мин |
| 11 | [Sync Deep Dive](11_SYNC_DEEP_DIVE.md) | Полная цепочка синхронизации: SyncComparator → SyncDiff → все 6 миксинов → batch API → NetBox. Все 11 _check_*() хелперов | ~60 мин |
| 12 | [Internals и Testing](12_INTERNALS_AND_TESTING.md) | Инфраструктура: Config система, constants пакет, иерархия исключений, RunContext, паттерны тестирования с MagicMock и pytest | ~45 мин |
| 13 | [Switchport Flow](13_SWITCHPORT_FLOW.md) | Полная цепочка определения switchport mode: SSH → TextFSM → нормализация → enrichment → NetBox sync. Три платформы (IOS, NX-OS, QTech), различия форматов, история бага | ~40 мин |
| 14 | [Маппинг имён интерфейсов](14_INTERFACE_NAME_MAPPINGS.md) | Проблема разных форматов имён (Gi0/1 vs GigabitEthernet0/1), два маппинга + три функции, как алиасы связывают данные из разных команд, использование на всех слоях | ~35 мин |
| 15 | [Push Config](15_PUSH_CONFIG.md) | Полная цепочка push-config: YAML с командами → маппинг платформ → backward compatibility → ConfigPusher → Netmiko → retry. Сравнение с push-descriptions | ~35 мин |
| 16 | [NetBox Client Deep Dive](16_NETBOX_CLIENT_DEEP_DIVE.md) | Клиентский слой NetBox API: pynetbox, все 6 миксинов (Devices, Interfaces, IP, VLAN, Inventory, DCIM), bulk операции, slug generation, lazy loading, связь sync→client→API | ~40 мин |
| 18 | [Port Type и Speed](18_PORT_TYPE_AND_SPEED.md) | Полная цепочка определения типа порта и скорости: TextFSM → UNIVERSAL_FIELD_MAP → detect_port_type → номинальная скорость → get_netbox_interface_type. Все маппинги, порядок паттернов, добавление нового типа | ~35 мин |
| 19 | [Git Backup](19_GIT_BACKUP.md) | Полная цепочка бэкапа конфигов в Git: CLI → SSH → .cfg → GitBackupPusher → Gitea REST API. Группировка по сайтам, site_map, SSL, тестирование | ~30 мин |

**Итого deep dive:** примерно 5 часов.

**Рекомендуемый порядок:** 10 → 11 → 12 → 13 → 14 → 15 → 16 → 18 → 19 (doc 10 вводит паттерны, которые используются в doc 11; doc 12 независимый, но ссылается на оба; doc 13 — глубокий разбор конкретного flow с историей бага; doc 14 — сквозной механизм нормализации имён; doc 15 — конфигурирование устройств через YAML и Netmiko; doc 16 — клиентский слой NetBox API, дополняет doc 11; doc 18 — полная цепочка определения типа порта и скорости, все маппинги; doc 19 — бэкап конфигов в Git через REST API).

## Практика: пиши код сам

После чтения документации — переходи к практике. Workbook — это ~60 задач возрастающей сложности, все на примерах реального кода проекта.

| # | Документ | Что тренируешь | Время |
|---|----------|----------------|-------|
| 17 | [Python Workbook](17_PYTHON_WORKBOOK.md) | 15 блоков: строки, словари, списки, функции, регулярки, файлы, классы, ошибки, SyncComparator, batch, CLI, 3 мини-проекта | ~20-30 часов |

**Как работать с Workbook:**
1. Закрой ChatGPT/Claude — только docs.python.org
2. По 30-40 минут в день
3. Сначала попробуй сам, потом сверь с эталоном
4. Блоки 1-6 (базовые) → Блоки 7-12 (продвинутые) → Блоки 13-15 (мини-проекты)

## Как связана обучающая документация с официальной

В папке `docs/` есть основная документация проекта. Она написана для тех, кто уже понимает код и хочет быстро найти нужную информацию:

| Обучающий документ | Связанная документация |
|--------------------|----------------------|
| 01 Python-концепции | -- (базовые знания) |
| 02 Обзор проекта | [ARCHITECTURE.md](../ARCHITECTURE.md) -- полная архитектура |
| 03 CLI изнутри | [MANUAL.md](../MANUAL.md) -- полное руководство по CLI и командам |
| 04 Сбор данных | [PLATFORM_GUIDE.md](../PLATFORM_GUIDE.md) -- платформы, шаблоны, парсинг |
| 05 Синхронизация с NetBox | [ARCHITECTURE.md](../ARCHITECTURE.md) -- архитектура sync слоя |
| 06 Pipeline | [MANUAL.md](../MANUAL.md) -- руководство по использованию |
| 07 Потоки данных | [ARCHITECTURE.md](../ARCHITECTURE.md) -- поток данных между слоями |
| 08 Web-архитектура | [WEB_API.md](../WEB_API.md) -- REST API документация |
| 09 Mixins и паттерны | [TESTING.md](../TESTING.md) -- тестирование mixin-классов |
| 10 Collectors Deep Dive | [PLATFORM_GUIDE.md](../PLATFORM_GUIDE.md), [ARCHITECTURE.md](../ARCHITECTURE.md) |
| 11 Sync Deep Dive | [ARCHITECTURE.md](../ARCHITECTURE.md), [DEVELOPMENT.md](../DEVELOPMENT.md) |
| 12 Internals и Testing | [TESTING.md](../TESTING.md), [DEVELOPMENT.md](../DEVELOPMENT.md) |
| 13 Switchport Flow | [PLATFORM_GUIDE.md](../PLATFORM_GUIDE.md), [ARCHITECTURE.md](../ARCHITECTURE.md) |
| 14 Маппинг имён интерфейсов | [PLATFORM_GUIDE.md](../PLATFORM_GUIDE.md), [ARCHITECTURE.md](../ARCHITECTURE.md) |
| 15 Push Config | [MANUAL.md](../MANUAL.md), [DEVELOPMENT.md](../DEVELOPMENT.md), [ARCHITECTURE.md](../ARCHITECTURE.md) |
| 16 NetBox Client Deep Dive | [ARCHITECTURE.md](../ARCHITECTURE.md), [DEVELOPMENT.md](../DEVELOPMENT.md) |
| 19 Git Backup | [MANUAL.md](../MANUAL.md), [TODO.md](../TODO.md) |

**Рекомендация:** сначала прочитай обучающий документ, чтобы понять концепцию. Потом загляни в связанный документ из основной документации для полной картины.
