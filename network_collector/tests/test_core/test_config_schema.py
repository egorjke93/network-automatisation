"""
Тесты для валидации конфигурации через Pydantic.
"""

import pytest

from network_collector.core.config_schema import (
    validate_config,
    AppConfig,
    OutputConfig,
    NetBoxConfig,
    LoggingConfig,
    get_default_config,
)
from network_collector.core.exceptions import ConfigError


class TestDefaultConfig:
    """Тесты конфигурации по умолчанию."""

    def test_get_default_config(self):
        """Дефолтная конфигурация валидна."""
        config = get_default_config()
        assert isinstance(config, AppConfig)

    def test_default_output_format(self):
        config = get_default_config()
        assert config.output.default_format == "excel"
        assert config.output.mac_format == "ieee"

    def test_default_netbox_url(self):
        config = get_default_config()
        assert config.netbox.url == "http://localhost:8000/"

    def test_default_logging(self):
        config = get_default_config()
        assert config.logging.level == "INFO"
        assert config.logging.json_format is False


class TestValidateConfig:
    """Тесты валидации словаря конфигурации."""

    def test_empty_dict_uses_defaults(self):
        """Пустой словарь использует дефолты."""
        config = validate_config({})
        assert config.output.default_format == "excel"

    def test_partial_config(self):
        """Частичная конфигурация дополняется дефолтами."""
        config = validate_config({
            "output": {"mac_format": "cisco"}
        })
        assert config.output.mac_format == "cisco"
        assert config.output.default_format == "excel"  # дефолт

    def test_full_netbox_config(self):
        """Полная NetBox конфигурация."""
        config = validate_config({
            "netbox": {
                "url": "https://netbox.example.com/",
                "token": "abc123",
                "verify_ssl": False,
                "timeout": 60,
            }
        })
        assert config.netbox.url == "https://netbox.example.com/"
        assert config.netbox.token == "abc123"
        assert config.netbox.verify_ssl is False
        assert config.netbox.timeout == 60


class TestOutputConfigValidation:
    """Тесты валидации секции output."""

    @pytest.mark.parametrize("format_value", ["excel", "csv", "json"])
    def test_valid_formats(self, format_value: str):
        config = validate_config({"output": {"default_format": format_value}})
        assert config.output.default_format == format_value

    def test_invalid_format_raises_error(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_config({"output": {"default_format": "xml"}})
        assert "default_format" in str(exc_info.value)

    @pytest.mark.parametrize("mac_format", ["ieee", "cisco", "unix"])
    def test_valid_mac_formats(self, mac_format: str):
        config = validate_config({"output": {"mac_format": mac_format}})
        assert config.output.mac_format == mac_format

    def test_invalid_mac_format_raises_error(self):
        with pytest.raises(ConfigError):
            validate_config({"output": {"mac_format": "invalid"}})


class TestNetBoxConfigValidation:
    """Тесты валидации секции netbox."""

    def test_url_with_trailing_slash(self):
        """URL нормализуется с trailing slash."""
        config = validate_config({"netbox": {"url": "http://netbox.local"}})
        assert config.netbox.url == "http://netbox.local/"

    def test_url_already_has_trailing_slash(self):
        config = validate_config({"netbox": {"url": "http://netbox.local/"}})
        assert config.netbox.url == "http://netbox.local/"

    def test_invalid_url_raises_error(self):
        """URL без схемы вызывает ошибку."""
        with pytest.raises(ConfigError):
            validate_config({"netbox": {"url": "netbox.local"}})

    def test_timeout_range(self):
        """Timeout в допустимом диапазоне."""
        config = validate_config({"netbox": {"timeout": 1}})
        assert config.netbox.timeout == 1

        config = validate_config({"netbox": {"timeout": 300}})
        assert config.netbox.timeout == 300

    def test_timeout_too_small_raises_error(self):
        with pytest.raises(ConfigError):
            validate_config({"netbox": {"timeout": 0}})


class TestConnectionConfigValidation:
    """Тесты валидации секции connection."""

    def test_valid_workers(self):
        config = validate_config({"connection": {"max_workers": 10}})
        assert config.connection.max_workers == 10

    def test_workers_too_many_raises_error(self):
        with pytest.raises(ConfigError):
            validate_config({"connection": {"max_workers": 100}})

    def test_workers_too_few_raises_error(self):
        with pytest.raises(ConfigError):
            validate_config({"connection": {"max_workers": 0}})


class TestLoggingConfigValidation:
    """Тесты валидации секции logging."""

    @pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_valid_log_levels(self, level: str):
        config = validate_config({"logging": {"level": level}})
        assert config.logging.level == level

    def test_invalid_log_level_raises_error(self):
        with pytest.raises(ConfigError):
            validate_config({"logging": {"level": "TRACE"}})

    @pytest.mark.parametrize("rotation", ["size", "time"])
    def test_valid_rotation_types(self, rotation: str):
        config = validate_config({"logging": {"rotation": rotation}})
        assert config.logging.rotation == rotation

    def test_invalid_rotation_raises_error(self):
        with pytest.raises(ConfigError):
            validate_config({"logging": {"rotation": "daily"}})


class TestFiltersConfigValidation:
    """Тесты валидации секции filters."""

    def test_exclude_vlans_list(self):
        config = validate_config({"filters": {"exclude_vlans": [1, 100, 200]}})
        assert config.filters.exclude_vlans == [1, 100, 200]

    def test_exclude_interfaces_list(self):
        config = validate_config({"filters": {"exclude_interfaces": ["^Vlan\\d+"]}})
        assert config.filters.exclude_interfaces == ["^Vlan\\d+"]

    def test_default_exclude_interfaces(self):
        """По умолчанию есть паттерны исключения."""
        config = get_default_config()
        assert len(config.filters.exclude_interfaces) > 0
        assert "^Vlan\\d+" in config.filters.exclude_interfaces
