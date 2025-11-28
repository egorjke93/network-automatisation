"""
Конфигурация для сбора MAC-адресов.
Все настройки в одном месте для удобного управления.
"""

# ===========================================================
# НАСТРОЙКИ ФИЛЬТРОВ
# ===========================================================

# Исключать trunk порты из результатов
EXCLUDE_TRUNK_PORTS = True

# Исключать интерфейсы по паттерну имени
EXCLUDE_BY_NAME = True

# Паттерны интерфейсов для исключения (если EXCLUDE_BY_NAME = True)
# CPU - системные MAC
# Po - Port-channel (агрегированные каналы)
# Vl - VLAN интерфейсы
EXCLUDE_INTERFACE_PATTERNS = ["CPU", "Po", "Vl"]

# Собирать sticky MAC из running-config
COLLECT_STICKY_MAC = True

# Собирать dynamic MAC из таблицы MAC-адресов
COLLECT_DYNAMIC_MAC = True

# Сохранять отдельный файл для каждого устройства
# True - отдельный файл для каждого (hostname_YYYY-MM-DD.xlsx)
# False - один общий файл (mac_tables_YYYY-MM-DD.xlsx)
SAVE_PER_DEVICE = True

# Папка для сохранения Excel файлов (создаётся автоматически)
# Если пустая строка "" - сохраняет в текущую директорию
OUTPUT_FOLDER = "mac_reports"

# Формат вывода MAC-адреса в Excel
# Варианты:
#   "colon"      -> 00:00:00:00:00:00 (Linux/Unix)
#   "dash"       -> 00-00-00-00-00-00 (Windows)
#   "cisco"      -> 0000.0000.0000 (Cisco)
#   "none"       -> 000000000000 (без разделителей)
#   "original"   -> оставить как есть (не менять)
MAC_FORMAT = "colon"

# Показывать статус устройства (online/offline)
# online  - MAC есть в таблице MAC-адресов (устройство активно)
# offline - MAC только в sticky (устройство выключено)
SHOW_DEVICE_STATUS = True


# ===========================================================
# ПОДДЕРЖИВАЕМЫЕ ТИПЫ УСТРОЙСТВ
# ===========================================================

# Маппинг device_type -> класс парсера
# Используется для автоматического выбора парсера
SUPPORTED_DEVICE_TYPES = {
    "cisco_ios": "cisco",
    "cisco_xe": "cisco",
    "cisco_nxos": "cisco",
    "arista_eos": "arista",
    "juniper": "juniper",
    "juniper_junos": "juniper",
    "eltex": "eltex",
    "eltex_esr": "eltex",
}

