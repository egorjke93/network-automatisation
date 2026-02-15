"""Device Management routes - CRUD для устройств."""

import logging
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from ...core.constants.platforms import DEFAULT_PLATFORM
from ..services.device_service import (
    get_device_service,
    get_device_types,
    get_device_roles,
    migrate_from_devices_ips,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_device_defaults() -> Dict[str, str]:
    """Загружает defaults для устройств из fields.yaml."""
    try:
        import yaml
        fields_path = Path(__file__).parent.parent.parent / "fields.yaml"
        if fields_path.exists():
            with open(fields_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("sync", {}).get("devices", {}).get("defaults", {})
    except Exception as e:
        logger.warning(f"Не удалось загрузить defaults из fields.yaml: {e}")
    return {}


# =============================================================================
# Schemas
# =============================================================================

class DeviceCreate(BaseModel):
    """Схема создания устройства."""
    host: str = Field(..., description="IP адрес или hostname")
    device_type: str = Field(default=DEFAULT_PLATFORM, description="Платформа (cisco_ios, cisco_nxos, etc.)")
    name: Optional[str] = Field(None, description="Имя устройства")
    site: Optional[str] = Field(None, description="Сайт NetBox")
    role: Optional[str] = Field(None, description="Роль устройства (switch, router, etc.)")
    tenant: Optional[str] = Field(None, description="Tenant NetBox")
    description: Optional[str] = Field(None, description="Описание")
    enabled: bool = Field(default=True, description="Активно")
    tags: Optional[List[str]] = Field(default=[], description="Теги")


class DeviceUpdate(BaseModel):
    """Схема обновления устройства."""
    host: Optional[str] = None
    device_type: Optional[str] = None
    name: Optional[str] = None
    site: Optional[str] = None
    role: Optional[str] = None
    tenant: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None


class DeviceResponse(BaseModel):
    """Ответ с устройством."""
    id: str
    host: str
    device_type: str
    name: Optional[str]
    site: Optional[str]
    role: Optional[str]
    tenant: Optional[str]
    description: Optional[str]
    enabled: bool
    tags: List[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class DevicesListResponse(BaseModel):
    """Список устройств."""
    devices: List[DeviceResponse]
    total: int


class BulkImportRequest(BaseModel):
    """Запрос на массовый импорт."""
    devices: List[DeviceCreate]
    replace: bool = Field(default=False, description="Заменить все существующие")


class BulkImportResponse(BaseModel):
    """Результат импорта."""
    added: int
    skipped: int
    errors: int


class ToggleRequest(BaseModel):
    """Запрос на включение/выключение."""
    enabled: bool


class NetBoxImportRequest(BaseModel):
    """Запрос на импорт из NetBox."""
    netbox_url: str = Field(..., description="URL NetBox API")
    netbox_token: str = Field(..., description="API токен NetBox")
    site: Optional[str] = Field(None, description="Фильтр по сайту")
    role: Optional[str] = Field(None, description="Фильтр по роли")
    status: Optional[str] = Field(default="active", description="Фильтр по статусу")
    replace: bool = Field(default=False, description="Заменить все существующие")


class NetBoxImportResponse(BaseModel):
    """Результат импорта из NetBox."""
    success: bool
    fetched: int
    added: int
    skipped: int
    errors: int
    message: str


# =============================================================================
# Routes
# =============================================================================

@router.get(
    "/",
    response_model=DevicesListResponse,
    summary="Список устройств",
)
async def list_devices(
    enabled_only: bool = False,
    site: Optional[str] = None,
    device_type: Optional[str] = None,
):
    """
    Возвращает список устройств с фильтрацией.

    - **enabled_only** - только активные устройства
    - **site** - фильтр по сайту
    - **device_type** - фильтр по типу
    """
    service = get_device_service()

    if enabled_only:
        devices = service.get_enabled_devices()
    else:
        devices = service.get_all_devices()

    # Фильтрация
    if site:
        devices = [d for d in devices if d.get("site") == site]
    if device_type:
        devices = [d for d in devices if d.get("device_type") == device_type]

    return DevicesListResponse(devices=devices, total=len(devices))


@router.get(
    "/stats",
    summary="Статистика по устройствам",
)
async def get_stats():
    """Возвращает статистику по устройствам."""
    service = get_device_service()
    return service.get_stats()


@router.get(
    "/types",
    summary="Поддерживаемые типы устройств (платформы)",
)
async def list_device_types():
    """Возвращает список поддерживаемых платформ (для SSH подключения)."""
    return {"types": get_device_types()}


@router.get(
    "/roles",
    summary="Роли устройств для NetBox",
)
async def list_device_roles():
    """Возвращает список ролей устройств для NetBox."""
    return {"roles": get_device_roles()}


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Получить устройство по ID",
)
async def get_device(device_id: str):
    """Возвращает устройство по ID."""
    service = get_device_service()
    device = service.get_device(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.post(
    "/",
    response_model=DeviceResponse,
    summary="Создать устройство",
    status_code=201,
)
async def create_device(data: DeviceCreate):
    """Создаёт новое устройство."""
    service = get_device_service()

    try:
        device = service.create_device(
            host=data.host,
            device_type=data.device_type,
            name=data.name,
            site=data.site,
            role=data.role,
            tenant=data.tenant,
            description=data.description,
            enabled=data.enabled,
            tags=data.tags,
        )
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Обновить устройство",
)
async def update_device(device_id: str, data: DeviceUpdate):
    """Обновляет устройство."""
    service = get_device_service()

    updates = data.model_dump(exclude_unset=True)

    try:
        device = service.update_device(device_id, updates)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return device
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{device_id}",
    summary="Удалить устройство",
)
async def delete_device(device_id: str):
    """Удаляет устройство."""
    service = get_device_service()

    if not service.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")

    return {"success": True, "message": "Device deleted"}


@router.post(
    "/{device_id}/toggle",
    response_model=DeviceResponse,
    summary="Включить/выключить устройство",
)
async def toggle_device(device_id: str, data: ToggleRequest):
    """Включает или выключает устройство."""
    service = get_device_service()

    device = service.toggle_device(device_id, data.enabled)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    return device


@router.post(
    "/bulk",
    response_model=BulkImportResponse,
    summary="Массовый импорт устройств",
)
async def bulk_import(data: BulkImportRequest):
    """
    Массовый импорт устройств.

    - **replace** = true - заменяет все существующие устройства
    - **replace** = false - добавляет только новые (дубликаты пропускаются)
    """
    service = get_device_service()

    devices_data = [d.model_dump() for d in data.devices]
    result = service.bulk_import(devices_data, replace=data.replace)

    return BulkImportResponse(**result)


@router.post(
    "/migrate",
    summary="Миграция из devices_ips.py",
)
async def migrate_devices():
    """
    Мигрирует устройства из devices_ips.py в JSON хранилище.

    Выполняется только если хранилище пустое.
    """
    count = migrate_from_devices_ips()
    return {
        "success": True,
        "migrated": count,
        "message": f"Migrated {count} devices" if count else "No devices to migrate or storage not empty",
    }


@router.post(
    "/import-from-netbox",
    response_model=NetBoxImportResponse,
    summary="Импорт устройств из NetBox",
)
async def import_from_netbox(data: NetBoxImportRequest):
    """
    Импортирует устройства из NetBox.

    - Подключается к NetBox по указанному URL и токену
    - Получает список устройств с фильтрацией
    - Конвертирует в локальный формат
    - Импортирует в хранилище

    **Поля из NetBox:**
    - name → name
    - primary_ip → host (IP-адрес)
    - platform → device_type
    - site → site
    - role → role
    - tenant → tenant
    - comments → description
    """
    from ...netbox.client import NetBoxClient
    from ...core.constants import NETBOX_TO_SCRAPLI_PLATFORM

    try:
        # Подключаемся к NetBox
        client = NetBoxClient(url=data.netbox_url, token=data.netbox_token)

        # Получаем устройства (site и role могут быть именем или slug)
        filters = {}
        if data.site:
            filters["site"] = data.site
        if data.role:
            filters["role"] = data.role
        if data.status:
            filters["status"] = data.status

        nb_devices = client.get_devices(**filters)

        # Проверяем что фильтры сработали
        if not nb_devices and (data.site or data.role):
            filter_info = []
            if data.site:
                filter_info.append(f"site='{data.site}'")
            if data.role:
                filter_info.append(f"role='{data.role}'")
            return NetBoxImportResponse(
                success=True,
                fetched=0,
                added=0,
                skipped=0,
                errors=0,
                message=f"Устройства не найдены с фильтрами: {', '.join(filter_info)}. "
                        "Проверьте правильность имени/slug сайта и роли.",
            )
        logger.info(f"Fetched {len(nb_devices)} devices from NetBox")

        # Конвертируем в наш формат
        devices_data = []
        skipped = 0

        for nb_dev in nb_devices:
            # Получаем IP-адрес
            primary_ip = None
            if nb_dev.primary_ip4:
                # primary_ip4 возвращает объект с address в формате "10.0.0.1/24"
                ip_str = str(nb_dev.primary_ip4.address) if nb_dev.primary_ip4.address else ""
                primary_ip = ip_str.split("/")[0] if ip_str else None
            elif nb_dev.primary_ip6:
                ip_str = str(nb_dev.primary_ip6.address) if nb_dev.primary_ip6.address else ""
                primary_ip = ip_str.split("/")[0] if ip_str else None

            # Без IP пропускаем
            if not primary_ip:
                logger.debug(f"Skipping {nb_dev.name}: no primary IP")
                skipped += 1
                continue

            # Определяем платформу
            platform = DEFAULT_PLATFORM
            if nb_dev.platform:
                platform_slug = str(nb_dev.platform.slug) if hasattr(nb_dev.platform, 'slug') else str(nb_dev.platform)
                # Маппинг NetBox platform → Scrapli platform
                platform = NETBOX_TO_SCRAPLI_PLATFORM.get(platform_slug, platform_slug)

            # Формируем устройство
            device_data = {
                "host": primary_ip,
                "device_type": platform,
                "name": nb_dev.name,
                "site": str(nb_dev.site.name) if nb_dev.site else None,
                "role": str(nb_dev.role.slug) if nb_dev.role else None,
                "tenant": str(nb_dev.tenant.name) if nb_dev.tenant else None,
                "description": nb_dev.comments or "",
                "enabled": nb_dev.status.value == "active" if nb_dev.status else True,
                "tags": [str(t.name) for t in nb_dev.tags] if nb_dev.tags else [],
            }
            devices_data.append(device_data)

        if not devices_data:
            return NetBoxImportResponse(
                success=True,
                fetched=len(nb_devices),
                added=0,
                skipped=skipped,
                errors=0,
                message=f"No devices with primary IP found. Fetched: {len(nb_devices)}, skipped: {skipped}",
            )

        # Импортируем
        service = get_device_service()
        result = service.bulk_import(devices_data, replace=data.replace)

        return NetBoxImportResponse(
            success=True,
            fetched=len(nb_devices),
            added=result.get("added", 0),
            skipped=result.get("skipped", 0) + skipped,
            errors=result.get("errors", 0),
            message=f"Successfully imported {result.get('added', 0)} devices from NetBox",
        )

    except Exception as e:
        logger.exception(f"Failed to import from NetBox: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import from NetBox: {str(e)}"
        )


@router.get(
    "/hosts/list",
    summary="Список IP-адресов для сбора",
)
async def get_device_hosts():
    """
    Возвращает список IP-адресов активных устройств.

    Используется для запуска сбора данных.
    """
    service = get_device_service()
    hosts = service.get_device_hosts()
    return {"hosts": hosts, "count": len(hosts)}


class FileImportResponse(BaseModel):
    """Результат импорта из файла."""
    success: bool
    added: int
    skipped: int
    errors: int
    message: str


@router.post(
    "/import-from-file",
    response_model=FileImportResponse,
    summary="Импорт устройств из файла (JSON/Excel)",
)
async def import_from_file(
    file: UploadFile = File(...),
    replace: bool = Form(default=False),
):
    """
    Импортирует устройства из файла.

    Поддерживаемые форматы:
    - **JSON** — список объектов с полями host, device_type, name, site, role, tenant
    - **Excel (.xlsx)** — таблица с колонками host, device_type, name, site, role, tenant

    Пример JSON:
    ```json
    [
        {"host": "192.168.1.1", "device_type": "cisco_ios", "role": "switch"},
        {"host": "192.168.1.2", "device_type": "cisco_nxos", "site": "DC-1"}
    ]
    ```

    **Параметры:**
    - **file** — файл для импорта (.json или .xlsx)
    - **replace** — заменить все существующие устройства (по умолчанию false)
    """
    filename = file.filename.lower() if file.filename else ""

    try:
        content = await file.read()
        devices_data = []

        # Определяем формат по расширению
        if filename.endswith(".json"):
            # JSON формат
            try:
                data = json.loads(content.decode("utf-8"))
                if isinstance(data, list):
                    devices_data = data
                elif isinstance(data, dict) and "devices" in data:
                    devices_data = data["devices"]
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="JSON должен содержать список устройств или объект с полем 'devices'"
                    )
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка парсинга JSON: {str(e)}"
                )

        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            # Excel формат
            try:
                import pandas as pd
                import io

                df = pd.read_excel(io.BytesIO(content))

                # Проверяем обязательную колонку
                if "host" not in df.columns:
                    raise HTTPException(
                        status_code=400,
                        detail="Excel файл должен содержать колонку 'host'"
                    )

                # Конвертируем в список словарей
                for _, row in df.iterrows():
                    device = {}
                    for col in df.columns:
                        val = row[col]
                        # Пропускаем NaN значения
                        if pd.notna(val):
                            device[col] = str(val) if not isinstance(val, bool) else val
                    if device.get("host"):
                        devices_data.append(device)

            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="Для импорта Excel требуется pandas и openpyxl"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка чтения Excel: {str(e)}"
                )

        elif filename.endswith(".csv"):
            # CSV формат
            try:
                import pandas as pd
                import io

                df = pd.read_csv(io.BytesIO(content))

                if "host" not in df.columns:
                    raise HTTPException(
                        status_code=400,
                        detail="CSV файл должен содержать колонку 'host'"
                    )

                for _, row in df.iterrows():
                    device = {}
                    for col in df.columns:
                        val = row[col]
                        if pd.notna(val):
                            device[col] = str(val) if not isinstance(val, bool) else val
                    if device.get("host"):
                        devices_data.append(device)

            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="Для импорта CSV требуется pandas"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка чтения CSV: {str(e)}"
                )

        elif filename.endswith(".py"):
            # Python формат (devices_ips.py style)
            try:
                import ast

                code = content.decode("utf-8")
                tree = ast.parse(code)

                # Ищем переменные devices_list или DEVICES
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id in ("devices_list", "DEVICES"):
                                # Безопасно извлекаем значение
                                if isinstance(node.value, ast.List):
                                    devices_data = ast.literal_eval(ast.unparse(node.value))
                                    break

                if not devices_data:
                    raise HTTPException(
                        status_code=400,
                        detail="Python файл должен содержать переменную 'devices_list' или 'DEVICES'"
                    )

            except SyntaxError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка синтаксиса Python: {str(e)}"
                )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ошибка чтения Python файла: {str(e)}"
                )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла. Используйте .json, .xlsx, .csv или .py"
            )

        if not devices_data:
            return FileImportResponse(
                success=True,
                added=0,
                skipped=0,
                errors=0,
                message="Файл пустой или не содержит устройств"
            )

        # Применяем defaults из fields.yaml для пустых полей
        defaults = get_device_defaults()
        if defaults:
            for device in devices_data:
                for field in ("site", "role", "tenant"):
                    if not device.get(field) and field in defaults:
                        device[field] = defaults[field]

        # Импортируем
        service = get_device_service()
        result = service.bulk_import(devices_data, replace=replace)

        return FileImportResponse(
            success=True,
            added=result.get("added", 0),
            skipped=result.get("skipped", 0),
            errors=result.get("errors", 0),
            message=f"Импортировано {result.get('added', 0)} устройств из файла"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to import from file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка импорта: {str(e)}"
        )
