"""
Network Collector - Утилита для сбора данных с сетевого оборудования.

Модуль предоставляет гибкий инструментарий для:
- Сбора MAC-адресов, LLDP/CDP соседей, информации об интерфейсах
- Парсинга вывода команд с помощью TextFSM и NTC-templates
- Экспорта данных в различные форматы (Excel, CSV, JSON)
- Интеграции с NetBox API для синхронизации данных

Примеры использования:
    # CLI
    python -m network_collector mac --format excel
    python -m network_collector lldp --format csv --delimiter ";"
    python -m network_collector run "show version" --fields hostname,version

    # Python API
    from network_collector import NetworkCollector

    collector = NetworkCollector(devices_file="devices_ips.py")
    data = collector.collect_mac()
    collector.export(data, format="csv")

Автор: Network Automation Team
Версия: 2.0.0
"""

__version__ = "2.0.0"
__author__ = "Network Automation Team"

# Основные классы для импорта
from .core.device import Device
from .core.connection import ConnectionManager
from .core.credentials import CredentialsManager

# Коллекторы данных
from .collectors.mac import MACCollector
from .collectors.lldp import LLDPCollector
from .collectors.interfaces import InterfaceCollector

# Парсеры
from .parsers.textfsm_parser import TextFSMParser

# Экспортеры
from .exporters.excel import ExcelExporter
from .exporters.csv_exporter import CSVExporter
from .exporters.json_exporter import JSONExporter

# NetBox
from .netbox.client import NetBoxClient

__all__ = [
    # Версия
    "__version__",
    # Core
    "Device",
    "ConnectionManager",
    "CredentialsManager",
    # Collectors
    "MACCollector",
    "LLDPCollector",
    "InterfaceCollector",
    # Parsers
    "TextFSMParser",
    # Exporters
    "ExcelExporter",
    "CSVExporter",
    "JSONExporter",
    # NetBox
    "NetBoxClient",
]
