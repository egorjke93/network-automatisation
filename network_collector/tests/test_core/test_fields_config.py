"""
Tests for fields_config.py.

Тестирует загрузку и применение конфигурации полей.
"""

import pytest
from unittest.mock import patch, mock_open
import yaml

from network_collector import fields_config
from network_collector.fields_config import (
    get_export_fields,
    get_enabled_fields,
    apply_fields_config,
    get_column_order,
    get_reverse_mapping,
    get_sync_config,
    reload_config,
    validate_config,
    validate_on_load,
    SyncFieldConfig,
    SyncEntityConfig,
)


class TestLoadYaml:
    """Тесты загрузки YAML."""

    def setup_method(self):
        """Сбрасываем кэш перед каждым тестом."""
        fields_config._config_cache = None

    def test_load_yaml_caches_result(self):
        """Результат кэшируется."""
        fields_config._load_yaml()
        first_cache = fields_config._config_cache
        fields_config._load_yaml()
        assert fields_config._config_cache is first_cache

    def test_load_yaml_missing_file(self):
        """Если файл не найден - возвращает пустой dict."""
        with patch("os.path.exists", return_value=False):
            fields_config._config_cache = None
            result = fields_config._load_yaml()
            assert result == {}

    def test_config_error_handling(self):
        """При ошибке чтения файла возвращает пустой dict."""
        fields_config._config_cache = None

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", side_effect=Exception("Read error")):
                result = fields_config._load_yaml()
                assert result == {}


class TestGetExportFields:
    """Тесты get_export_fields."""

    def setup_method(self):
        fields_config._config_cache = None

    def test_returns_fields_for_data_type(self):
        """Возвращает поля для типа данных."""
        mock_config = {
            "devices": {
                "hostname": {"enabled": True, "name": "Hostname", "order": 1},
                "ip": {"enabled": True, "name": "IP Address", "order": 2},
            }
        }
        fields_config._config_cache = mock_config

        result = get_export_fields("devices")
        assert "hostname" in result
        assert "ip" in result

    def test_returns_empty_for_unknown_type(self):
        """Для неизвестного типа возвращает пустой dict."""
        fields_config._config_cache = {}

        result = get_export_fields("unknown")
        assert result == {}


class TestGetEnabledFields:
    """Тесты get_enabled_fields."""

    def setup_method(self):
        fields_config._config_cache = None

    def test_returns_only_enabled(self):
        """Возвращает только включённые поля."""
        mock_config = {
            "devices": {
                "hostname": {"enabled": True, "name": "Hostname", "order": 1},
                "secret": {"enabled": False, "name": "Secret", "order": 2},
                "ip": {"enabled": True, "name": "IP", "order": 3},
            }
        }
        fields_config._config_cache = mock_config

        result = get_enabled_fields("devices")
        field_names = [f[0] for f in result]

        assert "hostname" in field_names
        assert "ip" in field_names
        assert "secret" not in field_names

    def test_sorted_by_order(self):
        """Результат отсортирован по order."""
        mock_config = {
            "devices": {
                "model": {"enabled": True, "name": "Model", "order": 3},
                "hostname": {"enabled": True, "name": "Hostname", "order": 1},
                "version": {"enabled": True, "name": "Version", "order": 2},
            }
        }
        fields_config._config_cache = mock_config

        result = get_enabled_fields("devices")
        orders = [f[2] for f in result]

        assert orders == sorted(orders)

    def test_default_values(self):
        """Default значения включаются в результат."""
        mock_config = {
            "devices": {
                "status": {"enabled": True, "name": "Status", "order": 1, "default": "unknown"},
            }
        }
        fields_config._config_cache = mock_config

        result = get_enabled_fields("devices")
        assert result[0][3] == "unknown"

    def test_handles_non_dict_values(self):
        """Игнорирует не-dict значения."""
        mock_config = {
            "devices": {
                "hostname": {"enabled": True, "name": "Hostname", "order": 1},
                "_comment": "This is a comment",  # Строка, не dict
            }
        }
        fields_config._config_cache = mock_config

        result = get_enabled_fields("devices")
        assert len(result) == 1


class TestApplyFieldsConfig:
    """Тесты apply_fields_config."""

    def setup_method(self):
        fields_config._config_cache = None

    def test_empty_data_returns_empty(self):
        """Пустые данные возвращаются как есть."""
        result = apply_fields_config([], "devices")
        assert result == []

    def test_no_config_returns_data_as_is(self):
        """Без конфигурации данные возвращаются как есть."""
        fields_config._config_cache = {}
        data = [{"hostname": "switch1"}]

        result = apply_fields_config(data, "unknown_type")
        assert result == data

    def test_filters_and_renames_fields(self):
        """Фильтрует и переименовывает поля."""
        mock_config = {
            "devices": {
                "hostname": {"enabled": True, "name": "Device Name", "order": 1},
                "ip": {"enabled": True, "name": "IP Address", "order": 2},
            }
        }
        fields_config._config_cache = mock_config

        data = [{"hostname": "switch1", "ip": "10.0.0.1", "extra": "ignored"}]
        result = apply_fields_config(data, "devices")

        assert len(result) == 1
        assert "Device Name" in result[0]
        assert "IP Address" in result[0]
        assert "extra" not in result[0]
        assert result[0]["Device Name"] == "switch1"

    def test_applies_default_values(self):
        """Применяет default для пустых значений."""
        mock_config = {
            "devices": {
                "status": {"enabled": True, "name": "Status", "order": 1, "default": "unknown"},
            }
        }
        fields_config._config_cache = mock_config

        data = [{"status": None}, {"status": ""}, {"status": "active"}]
        result = apply_fields_config(data, "devices")

        assert result[0]["Status"] == "unknown"
        assert result[1]["Status"] == "unknown"
        assert result[2]["Status"] == "active"

    def test_case_insensitive_field_match(self):
        """Поля матчатся без учёта регистра."""
        mock_config = {
            "devices": {
                "hostname": {"enabled": True, "name": "Hostname", "order": 1},
            }
        }
        fields_config._config_cache = mock_config

        data = [{"HOSTNAME": "SWITCH1"}]
        result = apply_fields_config(data, "devices")

        assert result[0]["Hostname"] == "SWITCH1"


class TestGetColumnOrder:
    """Тесты get_column_order."""

    def setup_method(self):
        fields_config._config_cache = None

    def test_returns_display_names_in_order(self):
        """Возвращает display names в порядке."""
        mock_config = {
            "devices": {
                "model": {"enabled": True, "name": "Model", "order": 3},
                "hostname": {"enabled": True, "name": "Hostname", "order": 1},
                "version": {"enabled": True, "name": "Version", "order": 2},
            }
        }
        fields_config._config_cache = mock_config

        result = get_column_order("devices")
        assert result == ["Hostname", "Version", "Model"]


class TestGetReverseMapping:
    """Тесты get_reverse_mapping."""

    def setup_method(self):
        fields_config._config_cache = None

    def test_returns_display_to_field_mapping(self):
        """Возвращает маппинг display_name → field_name."""
        mock_config = {
            "mac": {
                "hostname": {"enabled": True, "name": "Device", "order": 1},
                "interface": {"enabled": True, "name": "Port", "order": 2},
                "mac": {"enabled": True, "name": "MAC Address", "order": 3},
            }
        }
        fields_config._config_cache = mock_config

        result = get_reverse_mapping("mac")

        assert result["device"] == "hostname"
        assert result["port"] == "interface"
        assert result["mac address"] == "mac"

    def test_keys_are_lowercase(self):
        """Ключи приведены к lowercase."""
        mock_config = {
            "mac": {
                "hostname": {"enabled": True, "name": "Device", "order": 1},
                "mac": {"enabled": True, "name": "MAC Address", "order": 2},
            }
        }
        fields_config._config_cache = mock_config

        result = get_reverse_mapping("mac")

        # Все ключи должны быть lowercase
        for key in result.keys():
            assert key == key.lower()

    def test_includes_disabled_fields(self):
        """Включает disabled поля в маппинг."""
        mock_config = {
            "mac": {
                "hostname": {"enabled": True, "name": "Device", "order": 1},
                "secret": {"enabled": False, "name": "Secret Field", "order": 2},
            }
        }
        fields_config._config_cache = mock_config

        result = get_reverse_mapping("mac")

        assert "device" in result
        assert "secret field" in result

    def test_returns_empty_for_unknown_type(self):
        """Возвращает пустой dict для неизвестного типа."""
        fields_config._config_cache = {"mac": {}}

        result = get_reverse_mapping("unknown")

        assert result == {}

    def test_field_without_name_uses_field_name(self):
        """Если name не указан, используется имя поля."""
        mock_config = {
            "mac": {
                "vlan": {"enabled": True, "order": 1},  # No "name"
            }
        }
        fields_config._config_cache = mock_config

        result = get_reverse_mapping("mac")

        assert result["vlan"] == "vlan"

    def test_skips_non_dict_values(self):
        """Пропускает значения, которые не являются словарями."""
        mock_config = {
            "mac": {
                "hostname": {"enabled": True, "name": "Device", "order": 1},
                "invalid": "not a dict",
                "another_invalid": 123,
            }
        }
        fields_config._config_cache = mock_config

        result = get_reverse_mapping("mac")

        assert "device" in result
        assert "not a dict" not in result
        assert 123 not in result.values()


class TestSyncFieldConfig:
    """Тесты SyncFieldConfig dataclass."""

    def test_defaults(self):
        """Проверяем значения по умолчанию."""
        config = SyncFieldConfig()
        assert config.enabled is True
        assert config.source == ""

    def test_custom_values(self):
        """Можно задать кастомные значения."""
        config = SyncFieldConfig(enabled=False, source="my_field")
        assert config.enabled is False
        assert config.source == "my_field"


class TestSyncEntityConfig:
    """Тесты SyncEntityConfig dataclass."""

    def test_is_field_enabled(self):
        """Проверка включённости поля."""
        config = SyncEntityConfig()
        config.fields["name"] = SyncFieldConfig(enabled=True)
        config.fields["secret"] = SyncFieldConfig(enabled=False)

        assert config.is_field_enabled("name") is True
        assert config.is_field_enabled("secret") is False
        assert config.is_field_enabled("unknown") is False

    def test_get_source(self):
        """Получение source поля."""
        config = SyncEntityConfig()
        config.fields["display_name"] = SyncFieldConfig(source="name")
        config.fields["ip"] = SyncFieldConfig(source="")  # Пустой source

        assert config.get_source("display_name") == "name"
        assert config.get_source("ip") == "ip"  # Возвращает имя поля
        assert config.get_source("unknown") == "unknown"

    def test_get_default(self):
        """Получение значения по умолчанию."""
        config = SyncEntityConfig()
        config.defaults = {"status": "active", "role": "switch"}

        assert config.get_default("status") == "active"
        assert config.get_default("unknown") is None
        assert config.get_default("unknown", "default_value") == "default_value"

    def test_get_option(self):
        """Получение опции."""
        config = SyncEntityConfig()
        config.options = {"cleanup": True, "batch_size": 100}

        assert config.get_option("cleanup") is True
        assert config.get_option("batch_size") == 100
        assert config.get_option("unknown") is None


class TestGetSyncConfig:
    """Тесты get_sync_config."""

    def setup_method(self):
        fields_config._config_cache = None

    def test_loads_sync_config(self):
        """Загружает конфигурацию синхронизации."""
        mock_config = {
            "sync": {
                "devices": {
                    "fields": {
                        "name": {"enabled": True, "source": "hostname"},
                        "serial": {"enabled": False},
                    },
                    "defaults": {"status": "active"},
                    "options": {"create_only": False},
                }
            }
        }
        fields_config._config_cache = mock_config

        result = get_sync_config("devices")

        assert result.is_field_enabled("name") is True
        assert result.is_field_enabled("serial") is False
        assert result.get_source("name") == "hostname"
        assert result.get_default("status") == "active"
        assert result.get_option("create_only") is False

    def test_returns_empty_for_unknown_entity(self):
        """Для неизвестной сущности возвращает пустую конфигурацию."""
        fields_config._config_cache = {"sync": {}}

        result = get_sync_config("unknown")

        assert result.fields == {}
        assert result.defaults == {}


class TestReloadConfig:
    """Тесты reload_config."""

    def test_clears_cache(self):
        """Сбрасывает кэш."""
        fields_config._config_cache = {"test": "data"}
        reload_config()
        # Кэш должен быть перезагружен из файла
        # (не None, а новые данные из fields.yaml)


class TestValidateConfig:
    """Тесты validate_config."""

    def test_returns_errors_list(self):
        """Возвращает список ошибок."""
        # Должен возвращать список (может быть пустой)
        result = validate_config()
        assert isinstance(result, list)


class TestValidateOnLoad:
    """Тесты validate_on_load."""

    def test_validates_when_debug(self):
        """Валидирует при LOG_LEVEL=DEBUG."""
        with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}):
            with patch.object(fields_config, "validate_config", return_value=[]) as mock:
                validate_on_load()
                mock.assert_called_once()

    def test_validates_when_flag_set(self):
        """Валидирует при VALIDATE_FIELDS=1."""
        with patch.dict("os.environ", {"VALIDATE_FIELDS": "1", "LOG_LEVEL": ""}):
            with patch.object(fields_config, "validate_config", return_value=[]) as mock:
                validate_on_load()
                mock.assert_called_once()

    def test_skips_validation_by_default(self):
        """По умолчанию не валидирует."""
        with patch.dict("os.environ", {"VALIDATE_FIELDS": "", "LOG_LEVEL": ""}):
            with patch.object(fields_config, "validate_config", return_value=[]) as mock:
                validate_on_load()
                mock.assert_not_called()
