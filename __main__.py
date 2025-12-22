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

# Подключаем Windows Certificate Store для SSL (если установлено)
# Это позволяет использовать корпоративные CA без ручного добавления
try:
    import certifi_win32
    # Автоматически патчит certifi для использования Windows Certificate Store
    certifi_win32.wincerts.where()
except ImportError:
    # python-certifi-win32 не установлен, используем стандартный certifi
    pass

from .cli import main

if __name__ == "__main__":
    main()

