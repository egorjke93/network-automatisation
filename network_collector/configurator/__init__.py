"""
Модуль для внесения изменений в конфигурацию устройств.

Использует Netmiko для надёжного применения конфигурационных изменений.
Scrapli хорош для сбора данных, но Netmiko более проверен для конфигурации.

Модули:
- DescriptionPusher: Установка описаний интерфейсов
- ConfigPusher: Базовый класс для применения конфигураций
"""

from .base import ConfigPusher
from .description import DescriptionPusher, DescriptionMatcher

__all__ = [
    "ConfigPusher",
    "DescriptionPusher",
    "DescriptionMatcher",
]
