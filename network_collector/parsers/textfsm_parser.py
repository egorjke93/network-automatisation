"""
Парсер с поддержкой NTC-templates и кастомных TextFSM шаблонов.

Использует ntc_templates.parse.parse_output для парсинга вывода
сетевых команд. Для платформ с нестандартным выводом (QTech, Eltex)
поддерживает кастомные TextFSM шаблоны.

Возможности:
- Автоматический выбор шаблона по platform + command
- Кастомные шаблоны для нестандартных платформ (templates/)
- Универсальный маппинг полей для разных платформ
- Фильтрация полей — выбор только нужных данных
- Нормализация данных

Приоритет шаблонов:
1. Кастомный шаблон из templates/ (если есть в CUSTOM_TEXTFSM_TEMPLATES)
2. NTC Templates (fallback на cisco_ios для qtech/eltex)

Пример использования:
    parser = NTCParser()

    # Парсинг show version
    result = parser.parse(
        output=raw_output,
        platform="cisco_ios",
        command="show version"
    )

    # С фильтрацией полей
    result = parser.parse(
        output=raw_output,
        platform="cisco_ios",
        command="show version",
        fields=["hostname", "version", "serial"]
    )

Добавление кастомного шаблона:
    1. Добавь маппинг в core/constants.py: CUSTOM_TEXTFSM_TEMPLATES
    2. Создай шаблон в network_collector/templates/
    3. Готово! Парсер автоматически найдёт и использует его
"""

import os
import logging
from typing import List, Dict, Any, Optional
from io import StringIO

logger = logging.getLogger(__name__)

# Путь к папке с кастомными шаблонами
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

# Проверяем доступность ntc_templates
try:
    from ntc_templates.parse import parse_output
    NTC_AVAILABLE = True
except ImportError:
    NTC_AVAILABLE = False
    logger.warning("ntc-templates не установлен. pip install ntc-templates")

# Проверяем доступность textfsm (для кастомных шаблонов)
try:
    import textfsm
    TEXTFSM_AVAILABLE = True
except ImportError:
    TEXTFSM_AVAILABLE = False
    logger.debug("textfsm не установлен, кастомные шаблоны недоступны")

# Импортируем маппинги
from ..core.constants import CUSTOM_TEXTFSM_TEMPLATES, NTC_PLATFORM_MAP


# Универсальный маппинг полей для разных платформ
# Ключ - стандартное имя поля, значение - список возможных названий
UNIVERSAL_FIELD_MAP = {
    "hostname": ["hostname", "host", "switchname", "device_id"],
    # chassis_id - это MAC в LLDP, не hostname!
    "hardware": ["hardware", "platform", "model", "chassis", "device_model"],
    "serial": ["serial", "serial_number", "sn", "chassis_sn", "serialnum"],
    "version": ["version", "software_version", "os", "kickstart_ver", "sys_ver", "os_version"],
    "uptime": ["uptime", "uptime_string", "system_uptime"],
    "rommon": ["rommon", "boot_version", "bootrom"],
    "config_register": ["config_register", "config_reg"],
    # MAC table fields
    "mac": ["mac", "mac_address", "destination_address"],
    "vlan": ["vlan", "vlan_id"],
    "interface": ["interface", "port", "destination_port"],
    "type": ["type", "mac_type", "entry_type"],
    # Interface fields
    "status": ["status", "link_status", "link"],
    "protocol": ["protocol", "protocol_status"],
    "description": ["description", "desc"],
    "speed": ["speed", "bandwidth"],
    "duplex": ["duplex"],
    "mtu": ["mtu"],
    # LLDP/CDP fields
    "neighbor": ["neighbor", "neighbor_id", "device_id", "remote_system_name"],
    "local_interface": ["local_interface", "local_port"],
    "remote_interface": ["remote_interface", "remote_port", "port_id"],
    "capabilities": ["capabilities", "capability"],
    "platform": ["platform", "remote_platform"],
}


class NTCParser:
    """
    Парсер вывода сетевых команд через NTC Templates.

    Использует ntc_templates.parse.parse_output для автоматического
    определения и применения шаблона TextFSM.

    Example:
        parser = NTCParser()

        # Парсинг команды
        data = parser.parse(output, "cisco_ios", "show version")

        # С выбором полей
        data = parser.parse(
            output, "cisco_ios", "show version",
            fields=["hostname", "version"]
        )
    """

    def __init__(self):
        """Инициализация парсера."""
        if not NTC_AVAILABLE:
            raise ImportError(
                "ntc-templates не установлен. Установите: pip install ntc-templates"
            )

    def parse(
        self,
        output: str,
        platform: str,
        command: str,
        fields: Optional[List[str]] = None,
        normalize: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод команды через кастомный шаблон или NTC Templates.

        Приоритет:
        1. Кастомный шаблон из templates/ (если есть в CUSTOM_TEXTFSM_TEMPLATES)
        2. NTC Templates (с маппингом платформы через NTC_PLATFORM_MAP)

        Args:
            output: Сырой вывод команды
            platform: Платформа устройства (cisco_ios, qtech, etc.)
            command: Выполненная команда
            fields: Список полей для извлечения (None = все поля)
            normalize: Нормализовать имена полей

        Returns:
            List[Dict]: Список словарей с распарсенными данными

        Example:
            result = parser.parse(output, "qtech", "show mac address-table")
            # Использует кастомный шаблон если есть, иначе NTC с cisco_ios
        """
        if not output or not output.strip():
            logger.warning("Пустой вывод для парсинга")
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
                    logger.debug(f"Используем кастомный шаблон: {template_file}")
                    parsed_data = self._parse_with_textfsm(output, template_path)
                    used_custom_template = True  # Не fallback на NTC для виртуальных команд
                else:
                    logger.warning(f"Кастомный шаблон не найден: {template_path}")

            # 2. Fallback на NTC Templates (только если не использовали кастомный шаблон)
            if not parsed_data and not used_custom_template:
                # Маппинг платформы (qtech → cisco_ios)
                ntc_platform = NTC_PLATFORM_MAP.get(platform, platform)
                logger.debug(f"Используем NTC Templates: {ntc_platform}/{command}")

                parsed_data = parse_output(
                    platform=ntc_platform,
                    command=command,
                    data=output
                )

            # Если результат пустой
            if not parsed_data:
                logger.debug(f"Парсер вернул пустой результат для {platform}/{command}")
                return []

            # Нормализуем структуру (всегда список)
            if isinstance(parsed_data, dict):
                parsed_data = [parsed_data]

            # Нормализуем имена полей если нужно
            if normalize:
                parsed_data = self._normalize_fields(parsed_data)

            # Фильтруем поля если указаны
            if fields:
                parsed_data = self._filter_fields(parsed_data, fields)

            logger.debug(f"Распарсено записей: {len(parsed_data)}")
            return parsed_data

        except Exception as e:
            logger.error(f"Ошибка парсинга {platform}/{command}: {e}")
            return []

    def _parse_with_textfsm(
        self,
        output: str,
        template_path: str,
    ) -> List[Dict[str, Any]]:
        """
        Парсит вывод с помощью кастомного TextFSM шаблона.

        Args:
            output: Сырой вывод команды
            template_path: Путь к файлу шаблона .textfsm

        Returns:
            List[Dict]: Распарсенные данные
        """
        try:
            # Читаем шаблон с utf-8-sig (автоматически убирает BOM)
            with open(template_path, "r", encoding="utf-8-sig") as f:
                template_content = f.read()

            # Debug: показываем первые символы шаблона
            logger.debug(f"Template first 100 chars: {repr(template_content[:100])}")

            # StringIO для кроссплатформенной совместимости
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

    def _normalize_fields(
        self,
        data: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Нормализует имена полей в данных.

        Приводит различные варианты названий полей к стандартным.

        Args:
            data: Данные для нормализации

        Returns:
            List[Dict]: Нормализованные данные
        """
        normalized = []

        for row in data:
            new_row = {}
            for key, value in row.items():
                # Приводим ключ к нижнему регистру
                key_lower = key.lower()

                # Ищем стандартное имя для этого ключа
                standard_key = key_lower
                for std_name, aliases in UNIVERSAL_FIELD_MAP.items():
                    if key_lower in aliases:
                        standard_key = std_name
                        break

                # Обрабатываем значение
                if isinstance(value, list) and len(value) == 1:
                    value = value[0]
                elif isinstance(value, list) and len(value) == 0:
                    value = ""

                new_row[standard_key] = value

            normalized.append(new_row)

        return normalized

    def _filter_fields(
        self,
        data: List[Dict[str, Any]],
        fields: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Фильтрует данные, оставляя только указанные поля.

        Args:
            data: Полные данные
            fields: Список нужных полей

        Returns:
            List[Dict]: Отфильтрованные данные
        """
        fields_lower = [f.lower() for f in fields]

        filtered = []
        for row in data:
            filtered_row = {}
            for k, v in row.items():
                if k.lower() in fields_lower:
                    filtered_row[k] = v
            if filtered_row:
                filtered.append(filtered_row)

        return filtered

    def get_value(
        self,
        parsed: Dict[str, Any],
        key: str,
        default: Any = "",
    ) -> Any:
        """
        Извлекает значение по ключу с учётом алиасов.

        Args:
            parsed: Распарсенные данные
            key: Ключ для поиска
            default: Значение по умолчанию

        Returns:
            Найденное значение или default
        """
        # Прямой поиск
        if key in parsed:
            return self._clean_value(parsed[key])

        # Поиск по алиасам
        aliases = UNIVERSAL_FIELD_MAP.get(key.lower(), [key])
        for alias in aliases:
            for parsed_key in parsed:
                if parsed_key.lower() == alias.lower():
                    return self._clean_value(parsed[parsed_key])

        return default

    def _clean_value(self, value: Any) -> Any:
        """
        Очищает значение от лишних символов.

        Args:
            value: Исходное значение

        Returns:
            Очищенное значение
        """
        if isinstance(value, list):
            if len(value) == 1:
                return self._clean_value(value[0])
            elif len(value) == 0:
                return ""
            return value

        if isinstance(value, str):
            return value.strip("[]'\"").strip()

        return value

# Алиас для обратной совместимости
TextFSMParser = NTCParser
TEXTFSM_AVAILABLE = NTC_AVAILABLE
