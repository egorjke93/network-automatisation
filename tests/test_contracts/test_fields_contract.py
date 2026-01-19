"""
Contract tests для fields.yaml ↔ Models.

Проверяет что все поля указанные в fields.yaml
существуют в соответствующих моделях (to_dict()).

Это гарантирует что:
- fields.yaml не содержит несуществующих полей
- При добавлении полей в fields.yaml нужно добавить их в модель
- При удалении полей из модели нужно убрать их из fields.yaml
"""

import pytest
import yaml
from pathlib import Path
from dataclasses import fields as dataclass_fields

from network_collector.core.models import (
    Interface,
    MACEntry,
    LLDPNeighbor,
    InventoryItem,
    DeviceInfo,
    IPAddressEntry,
)


# Маппинг секций fields.yaml → модели
SECTION_TO_MODEL = {
    "lldp": LLDPNeighbor,
    "mac": MACEntry,
    "devices": DeviceInfo,
    "interfaces": Interface,
    "inventory": InventoryItem,
}

# Маппинг полей fields.yaml → поля модели (если имена отличаются)
FIELD_MAPPING = {
    "mac": {
        "type": "mac_type",  # type в fields.yaml это mac_type в модели
    },
    "interfaces": {
        "interface": "name",  # interface в fields.yaml это name в модели
    },
    "lldp": {
        # remote_platform теперь напрямую в модели
    },
}

# Поля которые добавляются при экспорте/нормализации (не в модели)
EXPORT_ONLY_FIELDS = {
    "mac": {"description", "status"},  # status добавляется MACNormalizer
    "lldp": set(),
    "interfaces": {"protocol"},  # protocol (link protocol) не хранится в модели
    "devices": set(),
    "inventory": set(),
}


@pytest.fixture(scope="module")
def fields_config():
    """Загружает fields.yaml."""
    config_path = Path(__file__).parent.parent.parent / "fields.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def model_fields():
    """Получает поля каждой модели через dataclass introspection."""
    return {
        name: {f.name for f in dataclass_fields(model)}
        for name, model in SECTION_TO_MODEL.items()
    }


class TestFieldsContract:
    """Контрактные тесты для fields.yaml."""

    @pytest.mark.unit
    def test_all_sections_have_models(self, fields_config):
        """Все секции в fields.yaml имеют соответствующие модели."""
        for section in ["lldp", "mac", "devices", "interfaces", "inventory"]:
            assert section in fields_config, f"Секция {section} не найдена в fields.yaml"
            assert section in SECTION_TO_MODEL, f"Модель для {section} не определена"

    @pytest.mark.unit
    @pytest.mark.parametrize("section", ["lldp", "mac", "devices", "interfaces", "inventory"])
    def test_enabled_fields_exist_in_model(self, fields_config, model_fields, section):
        """Все enabled поля из fields.yaml существуют в модели."""
        config = fields_config[section]
        model_field_names = model_fields[section]
        export_only = EXPORT_ONLY_FIELDS.get(section, set())
        field_mapping = FIELD_MAPPING.get(section, {})

        missing_fields = []
        for field_name, field_config in config.items():
            if isinstance(field_config, dict) and field_config.get("enabled", False):
                # Поле включено, проверяем что оно есть в модели
                # Учитываем маппинг имён (например type → mac_type)
                mapped_name = field_mapping.get(field_name, field_name)
                if mapped_name not in model_field_names:
                    if field_name not in export_only:
                        missing_fields.append(f"{field_name} (→{mapped_name})")

        assert not missing_fields, (
            f"Секция '{section}': поля {missing_fields} включены в fields.yaml "
            f"но отсутствуют в модели {SECTION_TO_MODEL[section].__name__}. "
            f"Доступные поля модели: {sorted(model_field_names)}"
        )

    @pytest.mark.unit
    def test_lldp_fields_contract(self, fields_config, model_fields):
        """LLDP: все ключевые поля присутствуют."""
        required_fields = {"hostname", "device_ip", "local_interface", "remote_hostname", "remote_port"}
        model_field_names = model_fields["lldp"]

        for field in required_fields:
            assert field in model_field_names, f"LLDP: обязательное поле {field} отсутствует в модели"
            assert field in fields_config["lldp"], f"LLDP: обязательное поле {field} отсутствует в fields.yaml"

    @pytest.mark.unit
    def test_mac_fields_contract(self, fields_config, model_fields):
        """MAC: все ключевые поля присутствуют."""
        required_fields = {"hostname", "device_ip", "interface", "mac", "vlan"}
        model_field_names = model_fields["mac"]

        for field in required_fields:
            assert field in model_field_names, f"MAC: обязательное поле {field} отсутствует в модели"
            assert field in fields_config["mac"], f"MAC: обязательное поле {field} отсутствует в fields.yaml"

    @pytest.mark.unit
    def test_devices_fields_contract(self, fields_config, model_fields):
        """Devices: все ключевые поля присутствуют."""
        required_fields = {"hostname", "ip_address", "model", "serial", "version"}
        model_field_names = model_fields["devices"]

        for field in required_fields:
            assert field in model_field_names, f"Devices: обязательное поле {field} отсутствует в модели"
            assert field in fields_config["devices"], f"Devices: обязательное поле {field} отсутствует в fields.yaml"

    @pytest.mark.unit
    def test_interfaces_fields_contract(self, fields_config, model_fields):
        """Interfaces: все ключевые поля присутствуют."""
        # 'interface' в fields.yaml соответствует 'name' в модели Interface
        model_field_names = model_fields["interfaces"]

        # Базовые поля
        assert "name" in model_field_names, "Interface: поле 'name' отсутствует в модели"
        assert "interface" in fields_config["interfaces"], "Interface: поле 'interface' отсутствует в fields.yaml"

        # Остальные обязательные
        for field in ["status", "description", "ip_address", "mac"]:
            assert field in model_field_names, f"Interface: поле {field} отсутствует в модели"
            assert field in fields_config["interfaces"], f"Interface: поле {field} отсутствует в fields.yaml"

    @pytest.mark.unit
    def test_inventory_fields_contract(self, fields_config, model_fields):
        """Inventory: все ключевые поля присутствуют."""
        required_fields = {"hostname", "name", "pid", "serial", "description"}
        model_field_names = model_fields["inventory"]

        for field in required_fields:
            assert field in model_field_names, f"Inventory: обязательное поле {field} отсутствует в модели"
            assert field in fields_config["inventory"], f"Inventory: обязательное поле {field} отсутствует в fields.yaml"


class TestFieldsToDict:
    """Тесты что to_dict() возвращает все поля из fields.yaml."""

    @pytest.mark.unit
    def test_lldp_to_dict_has_all_enabled_fields(self, fields_config):
        """LLDPNeighbor.to_dict() содержит все enabled поля."""
        neighbor = LLDPNeighbor(
            local_interface="Gi0/1",
            remote_hostname="switch-02",
            remote_port="Gi0/1",
            remote_mac="00:11:22:33:44:55",
            remote_ip="10.0.0.2",
            protocol="lldp",
            hostname="switch-01",
            device_ip="10.0.0.1",
            capabilities="Switch",
            remote_platform="Cisco IOS",
        )
        result = neighbor.to_dict()

        for field_name, field_config in fields_config["lldp"].items():
            if isinstance(field_config, dict) and field_config.get("enabled", False):
                if field_name == "remote_platform":
                    # remote_platform напрямую в модели
                    assert "remote_platform" in result, f"LLDP: поле remote_platform отсутствует в to_dict()"
                else:
                    assert field_name in result, f"LLDP: поле {field_name} отсутствует в to_dict()"

    @pytest.mark.unit
    def test_mac_to_dict_has_all_enabled_fields(self, fields_config):
        """MACEntry.to_dict() содержит все enabled поля (кроме description)."""
        entry = MACEntry(
            mac="00:11:22:33:44:55",
            interface="Gi0/1",
            vlan="10",
            mac_type="dynamic",
            hostname="switch-01",
            device_ip="10.0.0.1",
        )
        result = entry.to_dict()

        for field_name, field_config in fields_config["mac"].items():
            if isinstance(field_config, dict) and field_config.get("enabled", False):
                if field_name == "description":
                    # description добавляется отдельно при экспорте
                    continue
                if field_name == "type":
                    # type в модели это mac_type
                    assert "mac_type" in result, f"MAC: поле mac_type (→type) отсутствует в to_dict()"
                elif field_name == "status":
                    # status добавляется normalizer'ом, не частью MACEntry
                    continue
                else:
                    assert field_name in result, f"MAC: поле {field_name} отсутствует в to_dict()"

    @pytest.mark.unit
    def test_devices_to_dict_has_all_enabled_fields(self, fields_config):
        """DeviceInfo.to_dict() содержит все enabled поля."""
        device = DeviceInfo(
            hostname="switch-01",
            ip_address="10.0.0.1",
            model="C9200L-24P-4X",
            serial="JAE12345678",
            version="17.3.4",
            uptime="5 weeks",
            platform="cisco_ios",
            manufacturer="Cisco",
        )
        result = device.to_dict()

        for field_name, field_config in fields_config["devices"].items():
            if isinstance(field_config, dict) and field_config.get("enabled", False):
                assert field_name in result, f"Devices: поле {field_name} отсутствует в to_dict()"

    @pytest.mark.unit
    def test_interfaces_to_dict_has_all_enabled_fields(self, fields_config):
        """Interface.to_dict() содержит все enabled поля."""
        interface = Interface(
            name="GigabitEthernet0/1",
            description="Uplink",
            status="up",
            ip_address="10.0.0.1",
            mac="00:11:22:33:44:55",
            speed="1 Gbit",
            duplex="full",
            mtu=1500,
            vlan="100",
            mode="access",
            port_type="1g-rj45",
            media_type="RJ45",
            hardware_type="Gigabit Ethernet",
            lag="",
            hostname="switch-01",
            device_ip="10.0.0.1",
        )
        result = interface.to_dict()

        for field_name, field_config in fields_config["interfaces"].items():
            if isinstance(field_config, dict) and field_config.get("enabled", False):
                if field_name == "interface":
                    # interface в fields.yaml это name в модели
                    assert "name" in result, f"Interface: поле name (→interface) отсутствует в to_dict()"
                elif field_name == "protocol":
                    # protocol не хранится в Interface (это link protocol)
                    continue
                else:
                    assert field_name in result, f"Interface: поле {field_name} отсутствует в to_dict()"

    @pytest.mark.unit
    def test_inventory_to_dict_has_all_enabled_fields(self, fields_config):
        """InventoryItem.to_dict() содержит все enabled поля."""
        item = InventoryItem(
            name="Switch 1",
            pid="C9200L-24P-4X",
            serial="JAE12345678",
            description="24-port switch",
            vid="V02",
            hostname="switch-01",
            manufacturer="Cisco",
        )
        result = item.to_dict()

        for field_name, field_config in fields_config["inventory"].items():
            if isinstance(field_config, dict) and field_config.get("enabled", False):
                assert field_name in result, f"Inventory: поле {field_name} отсутствует в to_dict()"


class TestIPAddressSyncContract:
    """Контрактные тесты для синхронизации IP-адресов.

    Проверяет что Interface.prefix_length корректно передаётся в IPAddressEntry.mask
    для правильного формирования IP с маской при синхронизации с NetBox.

    Эти тесты предотвращают баг когда IP создаются с /32 вместо правильной маски.
    """

    @pytest.mark.unit
    def test_interface_has_prefix_length_field(self):
        """Interface модель имеет поле prefix_length."""
        interface_fields = {f.name for f in dataclass_fields(Interface)}
        assert "prefix_length" in interface_fields, (
            "Interface должен иметь поле prefix_length для передачи маски в IPAddressEntry"
        )

    @pytest.mark.unit
    def test_interface_from_dict_extracts_prefix_length(self):
        """Interface.from_dict() корректно извлекает prefix_length."""
        # Данные как из парсера show interfaces
        data = {
            "interface": "Vlan30",
            "ip_address": "10.177.30.213",
            "prefix_length": "24",
            "status": "up",
        }
        intf = Interface.from_dict(data)

        assert intf.prefix_length == "24", (
            "Interface.from_dict() должен извлекать prefix_length из данных парсера"
        )

    @pytest.mark.unit
    def test_interface_prefix_length_to_ip_address_entry(self):
        """Interface.prefix_length передаётся в IPAddressEntry.mask."""
        # Создаём Interface как из парсера
        intf = Interface(
            name="Vlan30",
            ip_address="10.177.30.213",
            prefix_length="24",
            status="up",
        )

        # Создаём IPAddressEntry как в CLI (cli.py)
        ip_entry = IPAddressEntry(
            ip_address=intf.ip_address,
            interface=intf.name,
            mask=intf.prefix_length,  # Критично: должен использовать prefix_length!
        )

        assert ip_entry.mask == "24", "IPAddressEntry.mask должен получить prefix_length из Interface"
        assert ip_entry.with_prefix == "10.177.30.213/24", (
            "IPAddressEntry.with_prefix должен формировать IP с правильной маской"
        )

    @pytest.mark.unit
    def test_ip_address_entry_with_prefix_not_32_when_mask_provided(self):
        """IPAddressEntry.with_prefix НЕ возвращает /32 если mask задана."""
        # Тест на регрессию бага с /32
        ip_entry = IPAddressEntry(
            ip_address="10.177.30.213",
            interface="Vlan30",
            mask="24",
        )

        assert ip_entry.with_prefix != "10.177.30.213/32", (
            "with_prefix не должен возвращать /32 если mask задана"
        )
        assert ip_entry.with_prefix == "10.177.30.213/24"

    @pytest.mark.unit
    def test_ip_address_entry_from_dict_uses_prefix_length(self):
        """IPAddressEntry.from_dict() использует prefix_length как альтернативу mask."""
        data = {
            "ip_address": "192.168.1.1",
            "interface": "Vlan100",
            "prefix_length": "24",  # prefix_length вместо mask
        }
        ip_entry = IPAddressEntry.from_dict(data)

        assert ip_entry.mask == "24", (
            "IPAddressEntry.from_dict() должен брать prefix_length если mask не задан"
        )
        assert ip_entry.with_prefix == "192.168.1.1/24"

    @pytest.mark.unit
    def test_fields_yaml_has_prefix_length_in_interfaces(self, fields_config):
        """fields.yaml содержит prefix_length в секции interfaces."""
        assert "prefix_length" in fields_config["interfaces"], (
            "fields.yaml должен содержать prefix_length в секции interfaces"
        )

    @pytest.mark.unit
    def test_fields_yaml_sync_ip_addresses_config(self, fields_config):
        """fields.yaml содержит конфигурацию sync.ip_addresses."""
        assert "sync" in fields_config, "fields.yaml должен содержать секцию sync"
        assert "ip_addresses" in fields_config["sync"], (
            "fields.yaml sync должен содержать секцию ip_addresses"
        )


class TestSyncOptionsContract:
    """Контрактные тесты для опций синхронизации в fields.yaml."""

    @pytest.mark.unit
    def test_enabled_mode_option_exists_in_config(self, fields_config):
        """fields.yaml содержит опцию enabled_mode в sync.interfaces.options."""
        assert "sync" in fields_config, "fields.yaml должен содержать секцию sync"
        assert "interfaces" in fields_config["sync"], (
            "fields.yaml sync должен содержать секцию interfaces"
        )
        assert "options" in fields_config["sync"]["interfaces"], (
            "fields.yaml sync.interfaces должен содержать секцию options"
        )
        assert "enabled_mode" in fields_config["sync"]["interfaces"]["options"], (
            "fields.yaml sync.interfaces.options должен содержать enabled_mode"
        )

    @pytest.mark.unit
    def test_enabled_mode_valid_values(self, fields_config):
        """enabled_mode должен иметь допустимое значение (admin или link)."""
        enabled_mode = fields_config["sync"]["interfaces"]["options"]["enabled_mode"]
        valid_values = ("admin", "link")
        assert enabled_mode in valid_values, (
            f"enabled_mode должен быть одним из {valid_values}, "
            f"получено: {enabled_mode}"
        )

    @pytest.mark.unit
    def test_get_sync_config_reads_enabled_mode(self):
        """get_sync_config() корректно читает enabled_mode из файла."""
        from network_collector.fields_config import get_sync_config

        sync_cfg = get_sync_config("interfaces")
        enabled_mode = sync_cfg.get_option("enabled_mode")

        assert enabled_mode is not None, (
            "get_sync_config('interfaces').get_option('enabled_mode') "
            "должен вернуть значение, не None"
        )
        assert enabled_mode in ("admin", "link"), (
            f"enabled_mode должен быть 'admin' или 'link', получено: {enabled_mode}"
        )

    @pytest.mark.unit
    def test_get_sync_config_default_for_missing_option(self):
        """get_option() возвращает default для несуществующей опции."""
        from network_collector.fields_config import get_sync_config

        sync_cfg = get_sync_config("interfaces")
        result = sync_cfg.get_option("nonexistent_option", "default_value")

        assert result == "default_value", (
            "get_option() должен вернуть default для несуществующей опции"
        )

    @pytest.mark.unit
    def test_sync_interfaces_options_structure(self, fields_config):
        """sync.interfaces.options содержит все необходимые опции."""
        options = fields_config["sync"]["interfaces"]["options"]

        # Проверяем базовые опции
        expected_options = ["create_missing", "update_existing", "auto_detect_type", "enabled_mode"]
        for opt in expected_options:
            assert opt in options, (
                f"sync.interfaces.options должен содержать '{opt}'"
            )
