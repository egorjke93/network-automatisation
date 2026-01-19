"""Schemas для credentials и конфигурации."""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class Credentials(BaseModel):
    """Учётные данные для подключения к устройствам."""

    username: str = Field(..., description="SSH username")
    password: str = Field(..., description="SSH password")
    secret: Optional[str] = Field(None, description="Enable password (опционально)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "admin",
                "password": "secret123",
            }
        }
    )


class NetBoxConfig(BaseModel):
    """Конфигурация NetBox."""

    url: str = Field(..., description="NetBox URL (например: http://netbox.local:8000)")
    token: str = Field(..., description="NetBox API Token")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "http://localhost:8000",
                "token": "0123456789abcdef...",
            }
        }
    )


class FullConfig(BaseModel):
    """Полная конфигурация для выполнения задач."""

    credentials: Credentials
    netbox: Optional[NetBoxConfig] = None
