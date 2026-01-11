"""
Тесты для field_registry.

Проверяет:
- Получение канонических имён полей
- Маппинг алиасов
- Валидацию fields.yaml
- Работу с NetBox полями
"""

import pytest
from typing import Dict, Set

from network_collector.core.field_registry import (
    FieldDefinition,
    FIELD_REGISTRY,
    SYNC_ONLY_FIELDS,
    EXPORT_ONLY_FIELDS,
    get_canonical_name,
    get_all_aliases,
    get_netbox_field,
    get_display_name,
    validate_fields_config,
    get_field_definition,
    print_field_registry,
)


class TestFieldDefinition:
    """Тесты dataclass FieldDefinition."""

    def test_create_minimal(self):
        """Создание с минимальными параметрами."""
        field = FieldDefinition(canonical="hostname")
        assert field.canonical == "hostname"
        assert field.aliases == []
        # display генерируется автоматически: hostname → "Hostname"
        assert field.display == "Hostname"
        # netbox_field по умолчанию пустая строка
        assert field.netbox_field == ""

    def test_create_full(self):
        """Создание со всеми параметрами."""
        field = FieldDefinition(
            canonical="local_interface",
            aliases=["local_port", "local_intf"],
            display="Local Interface",
            netbox_field="name",
            description="Локальный интерфейс",
        )
        assert field.canonical == "local_interface"
        assert "local_port" in field.aliases
        assert field.display == "Local Interface"
        assert field.netbox_field == "name"

    def test_display_auto_generated(self):
        """Display name генерируется из canonical: snake_case → Title Case."""
        field = FieldDefinition(canonical="test_field")
        # test_field → "Test Field"
        assert field.display == "Test Field"


class TestFieldRegistry:
    """Тесты структуры FIELD_REGISTRY."""

    def test_registry_has_required_types(self):
        """Реестр содержит все основные типы данных."""
        required_types = ["lldp", "mac", "interfaces", "inventory", "devices"]
        for data_type in required_types:
            assert data_type in FIELD_REGISTRY, f"Missing type: {data_type}"

    def test_registry_fields_are_field_definitions(self):
        """Все элементы реестра - FieldDefinition."""
        for data_type, fields in FIELD_REGISTRY.items():
            for field_name, field_def in fields.items():
                assert isinstance(
                    field_def, FieldDefinition
                ), f"{data_type}.{field_name} is not FieldDefinition"

    def test_canonical_matches_key(self):
        """Canonical name совпадает с ключом в реестре."""
        for data_type, fields in FIELD_REGISTRY.items():
            for field_name, field_def in fields.items():
                assert (
                    field_def.canonical == field_name
                ), f"{data_type}: key={field_name}, canonical={field_def.canonical}"


class TestGetCanonicalName:
    """Тесты get_canonical_name()."""

    def test_canonical_returns_itself(self):
        """Каноническое имя возвращается как есть."""
        assert get_canonical_name("lldp", "local_interface") == "local_interface"
        assert get_canonical_name("mac", "mac") == "mac"

    def test_alias_returns_canonical(self):
        """Алиас возвращает каноническое имя."""
        # local_port -> local_interface
        result = get_canonical_name("lldp", "local_port")
        assert result == "local_interface"

    def test_unknown_field_returns_original(self):
        """Неизвестное поле возвращается как есть."""
        assert get_canonical_name("lldp", "unknown_field") == "unknown_field"

    def test_unknown_type_returns_original(self):
        """Неизвестный тип возвращает оригинальное имя."""
        assert get_canonical_name("unknown_type", "field") == "field"

    def test_case_insensitive(self):
        """Поиск нечувствителен к регистру."""
        assert get_canonical_name("lldp", "LOCAL_INTERFACE") == "local_interface"
        assert get_canonical_name("mac", "MAC") == "mac"


class TestGetAllAliases:
    """Тесты get_all_aliases()."""

    def test_returns_all_aliases_with_canonical(self):
        """Возвращает все алиасы включая каноническое имя."""
        aliases = get_all_aliases("lldp", "local_interface")
        assert "local_interface" in aliases
        assert "local_port" in aliases

    def test_unknown_field_returns_singleton(self):
        """Для неизвестного поля возвращает только его имя."""
        aliases = get_all_aliases("lldp", "unknown")
        assert aliases == {"unknown"}

    def test_returns_set(self):
        """Результат - множество."""
        aliases = get_all_aliases("mac", "mac")
        assert isinstance(aliases, set)


class TestGetNetboxField:
    """Тесты get_netbox_field()."""

    def test_returns_netbox_mapping(self):
        """Возвращает имя поля NetBox."""
        # hostname -> name в NetBox
        result = get_netbox_field("devices", "hostname")
        assert result == "name"

    def test_returns_canonical_if_no_mapping(self):
        """Возвращает каноническое имя если нет специального маппинга."""
        result = get_netbox_field("lldp", "local_interface")
        # Возвращает само поле если netbox_field пустой
        assert result == "local_interface"

    def test_unknown_field_returns_itself(self):
        """Неизвестное поле возвращает само себя."""
        result = get_netbox_field("devices", "unknown_xyz")
        assert result == "unknown_xyz"


class TestGetDisplayName:
    """Тесты get_display_name()."""

    def test_returns_display_name(self):
        """Возвращает display name."""
        display = get_display_name("lldp", "local_interface")
        assert display is not None
        assert isinstance(display, str)
        assert display == "Local Port"

    def test_unknown_field_returns_titlecase(self):
        """Неизвестное поле возвращает Title Case."""
        display = get_display_name("lldp", "unknown_field")
        # unknown_field → "Unknown Field"
        assert display == "Unknown Field"


class TestSyncOnlyFields:
    """Тесты SYNC_ONLY_FIELDS."""

    def test_sync_only_has_devices(self):
        """devices содержит asset_tag, comments."""
        assert "devices" in SYNC_ONLY_FIELDS
        assert "asset_tag" in SYNC_ONLY_FIELDS["devices"]
        assert "comments" in SYNC_ONLY_FIELDS["devices"]

    def test_sync_only_excluded_from_validation(self):
        """Sync-only поля не вызывают ошибок валидации."""
        errors = validate_fields_config()
        # Не должно быть ошибок про asset_tag/comments
        for error in errors:
            assert "asset_tag" not in error.lower()
            assert "comments" not in error.lower()


class TestExportOnlyFields:
    """Тесты EXPORT_ONLY_FIELDS."""

    def test_export_only_structure(self):
        """EXPORT_ONLY_FIELDS содержит словарь типов данных."""
        assert isinstance(EXPORT_ONLY_FIELDS, dict)
        # Проверяем что есть хотя бы основные типы
        for data_type in EXPORT_ONLY_FIELDS:
            assert isinstance(EXPORT_ONLY_FIELDS[data_type], set)


class TestValidateFieldsConfig:
    """Тесты validate_fields_config()."""

    def test_returns_list(self):
        """Возвращает список."""
        result = validate_fields_config()
        assert isinstance(result, list)

    def test_no_critical_errors(self):
        """Нет критических ошибок в текущем fields.yaml."""
        errors = validate_fields_config()
        # Допустимы только warnings (неизвестные поля)
        critical = [e for e in errors if "NOT IN MODEL" in e.upper()]
        assert len(critical) == 0, f"Critical errors: {critical}"


class TestFieldRegistryAccess:
    """Тесты доступа к FIELD_REGISTRY."""

    def test_get_returns_dict(self):
        """FIELD_REGISTRY.get() возвращает словарь."""
        fields = FIELD_REGISTRY.get("lldp", {})
        assert isinstance(fields, dict)

    def test_contains_field_definitions(self):
        """Содержит FieldDefinition объекты."""
        fields = FIELD_REGISTRY.get("devices", {})
        for name, field_def in fields.items():
            assert isinstance(field_def, FieldDefinition)

    def test_unknown_type_returns_empty(self):
        """Неизвестный тип возвращает пустой словарь."""
        fields = FIELD_REGISTRY.get("unknown_type", {})
        assert fields == {}


class TestPrintFieldRegistry:
    """Тесты print_field_registry()."""

    def test_prints_without_error(self, capsys):
        """Печатает без ошибок."""
        print_field_registry()
        captured = capsys.readouterr()
        assert "FIELD REGISTRY" in captured.out or len(captured.out) > 0


class TestIntegration:
    """Интеграционные тесты."""

    def test_lldp_fields_complete(self):
        """LLDP содержит основные поля."""
        fields = FIELD_REGISTRY.get("lldp", {})
        required = ["local_interface", "remote_hostname", "remote_port"]
        for field_name in required:
            assert field_name in fields, f"Missing lldp.{field_name}"

    def test_mac_fields_complete(self):
        """MAC содержит основные поля."""
        fields = FIELD_REGISTRY.get("mac", {})
        # mac_type - каноническое имя для type
        required = ["mac", "vlan", "interface", "mac_type"]
        for field_name in required:
            assert field_name in fields, f"Missing mac.{field_name}"

    def test_interfaces_fields_complete(self):
        """Interfaces содержит основные поля."""
        fields = FIELD_REGISTRY.get("interfaces", {})
        required = ["name", "status", "description"]
        for field_name in required:
            assert field_name in fields, f"Missing interfaces.{field_name}"

    def test_devices_fields_complete(self):
        """Devices содержит основные поля."""
        fields = FIELD_REGISTRY.get("devices", {})
        # hostname - каноническое имя для device_name
        required = ["hostname", "serial"]
        for field_name in required:
            assert field_name in fields, f"Missing devices.{field_name}"

    def test_inventory_fields_complete(self):
        """Inventory содержит основные поля."""
        fields = FIELD_REGISTRY.get("inventory", {})
        # pid - каноническое имя для part_id
        required = ["name", "pid", "serial"]
        for field_name in required:
            assert field_name in fields, f"Missing inventory.{field_name}"
