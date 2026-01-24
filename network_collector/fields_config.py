"""
Конфигурация полей для экспорта и синхронизации.

Загружает настройки из fields.yaml:
- Секции lldp, mac, devices, interfaces, inventory — поля для экспорта
- Секция sync — поля для синхронизации с NetBox
"""

import os
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Путь к файлу fields.yaml
FIELDS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "fields.yaml")

# Глобальный кэш конфигурации
_config_cache: Optional[Dict[str, Any]] = None


def _load_yaml() -> Dict[str, Any]:
    """Загружает YAML файл (с кэшированием)."""
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    if not os.path.exists(FIELDS_CONFIG_FILE):
        logger.warning(f"Файл конфигурации полей не найден: {FIELDS_CONFIG_FILE}")
        _config_cache = {}
        return _config_cache

    try:
        import yaml
        with open(FIELDS_CONFIG_FILE, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    except ImportError:
        logger.warning("PyYAML не установлен, используем настройки по умолчанию")
        _config_cache = {}
    except Exception as e:
        logger.warning(f"Ошибка чтения {FIELDS_CONFIG_FILE}: {e}")
        _config_cache = {}

    return _config_cache


def get_export_fields(data_type: str) -> Dict[str, Dict[str, Any]]:
    """
    Возвращает конфигурацию полей для экспорта.

    Args:
        data_type: Тип данных (lldp, mac, devices, interfaces, inventory)

    Returns:
        Dict: {field_name: {enabled, name, order}}
    """
    config = _load_yaml()
    return config.get(data_type, {})


def get_enabled_fields(data_type: str) -> List[Tuple[str, str, int, Any]]:
    """
    Возвращает список включённых полей с их display name, порядком и default.

    Args:
        data_type: Тип данных

    Returns:
        List[Tuple]: [(field_name, display_name, order, default), ...] отсортированный по order
    """
    fields_config = get_export_fields(data_type)
    enabled = []

    for field_name, cfg in fields_config.items():
        if isinstance(cfg, dict) and cfg.get("enabled", True):
            display_name = cfg.get("name", field_name)
            order = cfg.get("order", 99)
            default_value = cfg.get("default", None)
            enabled.append((field_name, display_name, order, default_value))

    # Сортируем по order
    enabled.sort(key=lambda x: x[2])
    return enabled


def apply_fields_config(data: List[Dict[str, Any]], data_type: str) -> List[Dict[str, Any]]:
    """
    Применяет конфигурацию полей к данным:
    - Оставляет только включённые поля
    - Переименовывает поля в display names
    - Сортирует по order
    - Применяет default если значение пустое

    Args:
        data: Исходные данные
        data_type: Тип данных (lldp, mac, devices, interfaces, inventory)

    Returns:
        List[Dict]: Данные с применённой конфигурацией
    """
    if not data:
        return data

    enabled_fields = get_enabled_fields(data_type)
    if not enabled_fields:
        # Если конфиг не найден, возвращаем как есть
        return data

    result = []
    for row in data:
        new_row = {}
        for field_name, display_name, _, default_value in enabled_fields:
            # Ищем поле (учитываем разный регистр)
            value = None
            for key in row.keys():
                if key.lower() == field_name.lower():
                    value = row[key]
                    break

            # Применяем default если значение пустое/None
            if value is None or value == "":
                if default_value is not None:
                    value = default_value

            if value is not None:
                new_row[display_name] = value

        if new_row:
            result.append(new_row)

    return result


def get_column_order(data_type: str) -> List[str]:
    """
    Возвращает порядок колонок (display names) для экспорта.

    Args:
        data_type: Тип данных

    Returns:
        List[str]: Список display names в правильном порядке
    """
    enabled_fields = get_enabled_fields(data_type)
    return [display for _, display, _, _ in enabled_fields]


def get_reverse_mapping(data_type: str) -> Dict[str, str]:
    """
    Возвращает обратный маппинг: display_name → field_name.

    Используется для преобразования колонок Excel обратно в имена полей модели.
    Маппинг НЕчувствителен к регистру (ключи приводятся к lowercase).

    Args:
        data_type: Тип данных (lldp, mac, devices, interfaces, inventory)

    Returns:
        Dict[str, str]: {display_name.lower(): field_name}

    Пример для mac:
        {"device": "hostname", "port": "interface", "mac address": "mac", ...}
    """
    fields_config = get_export_fields(data_type)
    result = {}

    for field_name, cfg in fields_config.items():
        if isinstance(cfg, dict):
            display_name = cfg.get("name", field_name)
            # Ключ в lowercase для case-insensitive lookup
            result[display_name.lower()] = field_name

    return result


# =============================================================================
# SYNC CONFIG (для NetBox)
# =============================================================================

@dataclass
class SyncFieldConfig:
    """Конфигурация одного поля для синхронизации."""
    enabled: bool = True
    source: str = ""


@dataclass
class SyncEntityConfig:
    """Конфигурация синхронизации для типа данных."""
    fields: Dict[str, SyncFieldConfig] = field(default_factory=dict)
    defaults: Dict[str, Any] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)

    def is_field_enabled(self, field_name: str) -> bool:
        """Проверяет, включено ли поле для синхронизации."""
        if field_name in self.fields:
            return self.fields[field_name].enabled
        return False

    def get_source(self, field_name: str) -> str:
        """Возвращает исходное поле для данных."""
        if field_name in self.fields:
            return self.fields[field_name].source or field_name
        return field_name

    def get_default(self, key: str, default: Any = None) -> Any:
        """Возвращает значение по умолчанию."""
        return self.defaults.get(key, default)

    def get_option(self, key: str, default: Any = None) -> Any:
        """Возвращает опцию."""
        return self.options.get(key, default)


def get_sync_config(entity_type: str) -> SyncEntityConfig:
    """
    Возвращает конфигурацию синхронизации для типа сущности.

    Args:
        entity_type: Тип (devices, interfaces, ip_addresses, vlans, cables, inventory)

    Returns:
        SyncEntityConfig
    """
    config = _load_yaml()
    sync_data = config.get("sync", {}).get(entity_type, {})

    result = SyncEntityConfig()

    # Загружаем поля
    if "fields" in sync_data:
        for field_name, field_data in sync_data["fields"].items():
            if isinstance(field_data, dict):
                result.fields[field_name] = SyncFieldConfig(
                    enabled=field_data.get("enabled", True),
                    source=field_data.get("source", field_name),
                )

    # Загружаем defaults
    if "defaults" in sync_data:
        result.defaults = sync_data["defaults"]

    # Загружаем options
    if "options" in sync_data:
        result.options = sync_data["options"]

    return result


def reload_config() -> None:
    """Перезагружает конфигурацию из файла."""
    global _config_cache
    _config_cache = None
    _load_yaml()


# =============================================================================
# VALIDATION (использует field_registry)
# =============================================================================

def validate_config(verbose: bool = False) -> List[str]:
    """
    Валидирует fields.yaml против моделей и реестра.

    Проверяет:
    - Все enabled поля существуют в моделях
    - Sync source поля существуют в моделях
    - Предупреждает о неизвестных полях

    Args:
        verbose: Выводить подробности

    Returns:
        List[str]: Список ошибок и предупреждений
    """
    try:
        from .core.field_registry import validate_fields_config
        return validate_fields_config()
    except ImportError as e:
        logger.warning(f"Cannot import field_registry: {e}")
        return []


def validate_on_load() -> None:
    """
    Валидирует конфигурацию при первой загрузке.

    Вызывается автоматически если LOG_LEVEL=DEBUG или VALIDATE_FIELDS=1.
    """
    import os

    # Проверяем нужна ли валидация
    validate = os.environ.get("VALIDATE_FIELDS", "").lower() in ("1", "true", "yes")
    debug = os.environ.get("LOG_LEVEL", "").upper() == "DEBUG"

    if validate or debug:
        errors = validate_config()
        for err in errors:
            logger.warning(f"fields.yaml: {err}")
