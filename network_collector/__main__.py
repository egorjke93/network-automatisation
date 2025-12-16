"""
Точка входа для запуска модуля.

Позволяет запускать утилиту как:
    python -m network_collector [команда] [опции]

Примеры:
    python -m network_collector mac --format excel
    python -m network_collector lldp --format csv
    python -m network_collector interfaces
    python -m network_collector run "show version"
    python -m network_collector sync-netbox --interfaces
"""

from .cli import main

if __name__ == "__main__":
    main()

