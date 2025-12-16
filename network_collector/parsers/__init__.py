"""
Парсеры для обработки вывода сетевых устройств.

Модуль предоставляет:
- NTCParser: Универсальный парсер на базе NTC Templates
- TextFSMParser: Алиас для NTCParser (обратная совместимость)

Пример использования:
    from network_collector.parsers import NTCParser

    parser = NTCParser()

    # Парсинг с автоопределением шаблона
    result = parser.parse(
        output=raw_output,
        platform="cisco_ios",
        command="show version"
    )

    # Парсинг с выбором полей
    result = parser.parse(
        output=raw_output,
        platform="cisco_ios",
        command="show version",
        fields=["hostname", "version", "serial"]
    )
"""

from .textfsm_parser import NTCParser, TextFSMParser, NTC_AVAILABLE

__all__ = ["NTCParser", "TextFSMParser", "NTC_AVAILABLE"]

