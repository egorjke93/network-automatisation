"""
Pydantic схемы для валидации config.yaml.

Валидация происходит при загрузке конфигурации.
Ошибки валидации выбрасывают ConfigError.

Пример использования:
    from network_collector.core.config_schema import validate_config

    config_dict = yaml.safe_load(open("config.yaml"))
    validated = validate_config(config_dict)  # raises ConfigError on failure
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, HttpUrl
from pydantic_core import PydanticCustomError

from .exceptions import ConfigError


class OutputConfig(BaseModel):
    """Настройки вывода."""
    output_folder: str = "reports"
    default_format: str = Field(default="excel", pattern="^(excel|csv|json)$")
    mac_format: str = Field(default="ieee", pattern="^(ieee|cisco|unix)$")
    per_device: bool = False
    csv_delimiter: str = ","
    csv_quotechar: str = '"'
    csv_encoding: str = "utf-8"
    excel_autofilter: bool = True
    excel_freeze_header: bool = True


class ConnectionConfig(BaseModel):
    """Настройки подключения."""
    conn_timeout: int = Field(default=10, ge=1, le=300)
    read_timeout: int = Field(default=30, ge=1, le=600)
    max_workers: int = Field(default=5, ge=1, le=50)
    max_retries: int = Field(default=2, ge=0, le=10)
    retry_delay: int = Field(default=5, ge=0, le=60)


class ParserConfig(BaseModel):
    """Настройки парсера."""
    use_ntc_templates: bool = True
    custom_templates_path: Optional[str] = None


class NetBoxConfig(BaseModel):
    """Настройки NetBox."""
    url: str = "http://localhost:8000/"
    token: str = ""
    verify_ssl: bool = True
    timeout: int = Field(default=30, ge=1, le=300)
    create_missing: bool = True
    update_existing: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Проверяет что URL валидный."""
        if v and not v.startswith(("http://", "https://")):
            raise PydanticCustomError(
                "invalid_url",
                "NetBox URL должен начинаться с http:// или https://",
            )
        return v.rstrip("/") + "/"


class MACConfig(BaseModel):
    """Настройки сбора MAC."""
    collect_descriptions: bool = True
    collect_trunk_ports: bool = False
    collect_port_security: bool = False


class FiltersConfig(BaseModel):
    """Настройки фильтрации."""
    exclude_vlans: List[int] = Field(default_factory=list)
    exclude_interfaces: List[str] = Field(default_factory=lambda: [
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
    ])


class LoggingConfig(BaseModel):
    """Настройки логирования."""
    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    json_format: bool = False
    console: bool = True
    file_path: Optional[str] = None
    rotation: str = Field(default="size", pattern="^(size|time)$")
    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)  # min 1KB
    backup_count: int = Field(default=5, ge=1, le=100)
    when: str = "midnight"
    interval: int = Field(default=1, ge=1)


class AppConfig(BaseModel):
    """Полная конфигурация приложения."""
    output: OutputConfig = Field(default_factory=OutputConfig)
    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    parser: ParserConfig = Field(default_factory=ParserConfig)
    netbox: NetBoxConfig = Field(default_factory=NetBoxConfig)
    mac: MACConfig = Field(default_factory=MACConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    debug: bool = False
    devices_file: str = "devices_ips.py"


def validate_config(config_dict: dict) -> AppConfig:
    """
    Валидирует словарь конфигурации.

    Args:
        config_dict: Словарь из YAML

    Returns:
        AppConfig: Валидированная конфигурация

    Raises:
        ConfigError: При ошибке валидации
    """
    try:
        return AppConfig(**config_dict)
    except Exception as e:
        # Форматируем ошибку Pydantic в читаемый вид
        error_msg = str(e)
        if hasattr(e, "errors"):
            errors = e.errors()
            if errors:
                first_error = errors[0]
                loc = ".".join(str(x) for x in first_error.get("loc", []))
                msg = first_error.get("msg", "Unknown error")
                error_msg = f"{loc}: {msg}"

        raise ConfigError(
            message=f"Ошибка валидации конфигурации: {error_msg}",
            config_file="config.yaml",
        )


def get_default_config() -> AppConfig:
    """Возвращает конфигурацию по умолчанию."""
    return AppConfig()
