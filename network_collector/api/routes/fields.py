"""
Fields API - конфигурация полей из fields.yaml.

Предоставляет единый источник правды для UI и экспорта.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/fields", tags=["fields"])


@router.post(
    "/reload",
    summary="Перезагрузить конфигурацию",
)
async def reload_fields_config():
    """
    Перезагружает fields.yaml без рестарта бэкенда.

    Используйте после изменения fields.yaml.
    """
    from network_collector.fields_config import reload_config

    reload_config()
    return {"success": True, "message": "Конфигурация перезагружена"}


class FieldColumn(BaseModel):
    """Колонка для отображения в UI."""
    key: str        # Имя поля в данных (hostname, mac, etc.)
    label: str      # Display name для UI (Hostname, MAC Address, etc.)
    order: int      # Порядок колонки


class FieldsResponse(BaseModel):
    """Ответ с конфигурацией полей."""
    data_type: str
    columns: List[FieldColumn]


@router.get(
    "/{data_type}",
    response_model=FieldsResponse,
    summary="Получить конфигурацию полей",
)
async def get_fields(data_type: str):
    """
    Возвращает конфигурацию полей для указанного типа данных.

    Используется для динамической генерации колонок в UI.

    Args:
        data_type: Тип данных (devices, mac, lldp, interfaces, inventory)

    Returns:
        FieldsResponse: Список колонок с key, label и order

    Example:
        GET /api/fields/devices
        {
            "data_type": "devices",
            "columns": [
                {"key": "hostname", "label": "Hostname", "order": 1},
                {"key": "model", "label": "Model", "order": 3},
                ...
            ]
        }
    """
    from network_collector.fields_config import get_enabled_fields

    # Допустимые типы данных
    valid_types = ["devices", "mac", "lldp", "interfaces", "inventory"]

    if data_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid data_type: {data_type}. Valid types: {valid_types}"
        )

    fields = get_enabled_fields(data_type)

    if not fields:
        raise HTTPException(
            status_code=404,
            detail=f"No fields configuration found for: {data_type}"
        )

    columns = [
        FieldColumn(key=field_name, label=display_name, order=order)
        for field_name, display_name, order, _ in fields
    ]

    return FieldsResponse(data_type=data_type, columns=columns)


@router.get(
    "",
    summary="Получить все доступные типы данных",
)
async def get_available_types():
    """
    Возвращает список доступных типов данных с конфигурацией полей.
    """
    return {
        "types": [
            {"key": "devices", "label": "Устройства", "description": "Информация об устройствах (show version)"},
            {"key": "mac", "label": "MAC-адреса", "description": "Таблица MAC-адресов"},
            {"key": "lldp", "label": "LLDP/CDP", "description": "Соседи по LLDP/CDP"},
            {"key": "interfaces", "label": "Интерфейсы", "description": "Информация об интерфейсах"},
            {"key": "inventory", "label": "Inventory", "description": "Компоненты (модули, SFP, PSU)"},
        ]
    }
