"""
Загрузчик конфигурации из config.yaml.

Предоставляет доступ к настройкам через точку:
    config.output.mac_format
    config.netbox.url
    config.filters.exclude_vlans
"""

import os
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Путь к файлу конфигурации
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.yaml")


class ConfigSection:
    """Секция конфигурации с доступом через точку."""

    def __init__(self, data: dict = None):
        self._data = data or {}

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return super().__getattribute__(name)
        value = self._data.get(name)
        if isinstance(value, dict):
            return ConfigSection(value)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение с дефолтом."""
        return self._data.get(key, default)

    def __repr__(self) -> str:
        return f"ConfigSection({self._data})"


class Config:
    """
    Главный класс конфигурации.

    Загружает настройки из config.yaml и предоставляет доступ через точку.

    Пример:
        config.output.mac_format  # "ieee"
        config.netbox.url         # "http://localhost:8000/"
        config.filters.exclude_vlans  # []
    """

    def __init__(self):
        self._data = self._get_defaults()
        self._load_yaml()
        self._load_env()

    def _get_defaults(self) -> dict:
        """Значения по умолчанию."""
        return {
            "output": {
                "output_folder": "reports",
                "default_format": "excel",
                "mac_format": "ieee",
                "per_device": False,
                "csv_delimiter": ",",
                "csv_quotechar": '"',
                "csv_encoding": "utf-8",
                "excel_autofilter": True,
                "excel_freeze_header": True,
            },
            "connection": {
                "conn_timeout": 10,
                "read_timeout": 30,
                "max_workers": 5,
                "max_retries": 2,
                "retry_delay": 5,
            },
            "parser": {
                "use_ntc_templates": True,
                "custom_templates_path": None,
            },
            "netbox": {
                "url": os.getenv("NETBOX_URL", "http://localhost:8000/"),
                "token": os.getenv("NETBOX_TOKEN", ""),
                "verify_ssl": True,
                "timeout": 30,
                "create_missing": True,
                "update_existing": True,
            },
            "mac": {
                "collect_descriptions": True,
                "collect_trunk_ports": False,
                "collect_port_security": False,
            },
            "filters": {
                "exclude_vlans": [],
                "exclude_interfaces": [
                    r"^Vlan\d+",
                    r"^Vl\d+",
                    r"^Loopback\d+",
                    r"^Lo\d+",
                    r"^Null\d+",
                    r"^Port-channel\d+",
                    r"^Po\d+",
                    r"^mgmt\d*",
                    r"^CPU$",
                    r"^Switch$",
                    r"^Router$",
                    r"^Sup-eth",
                ],
            },
            "debug": False,
            "devices_file": "devices_ips.py",
        }

    def _load_yaml(self, config_file: Optional[str] = None) -> None:
        """Загружает настройки из YAML файла."""
        if not config_file:
            # Ищем config.yaml
            search_paths = [
                CONFIG_FILE,
                "config.yaml",
                "config.yml",
                ".network_collector.yaml",
            ]
            for path in search_paths:
                if os.path.exists(path):
                    config_file = path
                    break

        if not config_file or not os.path.exists(config_file):
            return

        try:
            import yaml
            with open(config_file, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}

            # Мержим с дефолтами
            self._merge_dict(self._data, yaml_data)
            logger.debug(f"Конфигурация загружена из {config_file}")

        except ImportError:
            logger.warning("PyYAML не установлен, используем настройки по умолчанию")
        except Exception as e:
            logger.warning(f"Ошибка чтения {config_file}: {e}")

    def _load_env(self) -> None:
        """Загружает настройки из переменных окружения."""
        # NetBox
        if os.getenv("NETBOX_URL"):
            self._data["netbox"]["url"] = os.getenv("NETBOX_URL")
        if os.getenv("NETBOX_TOKEN"):
            self._data["netbox"]["token"] = os.getenv("NETBOX_TOKEN")

    def _merge_dict(self, base: dict, override: dict) -> None:
        """Рекурсивно мержит словари."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_dict(base[key], value)
            else:
                base[key] = value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            return super().__getattribute__(name)
        value = self._data.get(name)
        if isinstance(value, dict):
            return ConfigSection(value)
        return value

    def reload(self, config_file: Optional[str] = None) -> None:
        """Перезагружает конфигурацию."""
        self._data = self._get_defaults()
        self._load_yaml(config_file)
        self._load_env()


# Глобальный экземпляр
config = Config()


def load_config(config_file: Optional[str] = None) -> Config:
    """
    Загружает конфигурацию из файла.

    Args:
        config_file: Путь к YAML файлу (опционально)

    Returns:
        Config: Объект конфигурации
    """
    config.reload(config_file)
    return config
