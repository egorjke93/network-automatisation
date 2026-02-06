"""
Синхронизация устройств с NetBox.

Mixin класс для create_device, sync_devices_from_inventory и связанных методов.
"""

import logging
from typing import List, Dict, Any, Optional

from .base import (
    SyncBase, DeviceInfo, get_sync_config, normalize_device_model,
    NetBoxError, NetBoxConnectionError, NetBoxValidationError, format_error_for_log, logger,
)

logger = logging.getLogger(__name__)


class DevicesSyncMixin:
    """Mixin для синхронизации устройств."""

    def create_device(
        self: SyncBase,
        name: str,
        device_type: str,
        site: Optional[str] = None,
        role: Optional[str] = None,
        manufacturer: Optional[str] = None,
        serial: str = "",
        status: Optional[str] = None,
        platform: str = "",
        tenant: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Создаёт устройство в NetBox.

        Args:
            name: Имя устройства (hostname)
            device_type: Тип/модель устройства
            site: Название сайта
            role: Роль устройства
            manufacturer: Производитель
            serial: Серийный номер
            status: Статус
            platform: Платформа
            tenant: Арендатор

        Returns:
            Device или None при ошибке
        """
        sync_cfg = get_sync_config("devices")

        if site is None:
            site = sync_cfg.get_default("site", "Main")
        if role is None:
            role = sync_cfg.get_default("role", "switch")
        if manufacturer is None:
            manufacturer = sync_cfg.get_default("manufacturer", "Cisco")
        if status is None:
            status = sync_cfg.get_default("status", "active")
        if tenant is None:
            tenant = sync_cfg.get_default("tenant", None)

        existing = self.client.get_device_by_name(name)
        if existing:
            logger.info(f"Устройство {name} уже существует в NetBox")
            return existing

        if self.dry_run:
            tenant_info = f", tenant={tenant}" if tenant else ""
            logger.info(
                f"[DRY-RUN] Создание устройства: {name} "
                f"(type={device_type}, site={site}, role={role}{tenant_info})"
            )
            return None

        try:
            mfr = self._get_or_create_manufacturer(manufacturer)
            if not mfr:
                logger.error(f"Не удалось создать производителя: {manufacturer}")
                return None

            dtype = self._get_or_create_device_type(device_type, mfr.id)
            if not dtype:
                logger.error(f"Не удалось создать тип устройства: {device_type}")
                return None

            site_obj = self._get_or_create_site(site)
            if not site_obj:
                logger.error(f"Не удалось создать сайт: {site}")
                return None

            role_obj = self._get_or_create_role(role)
            if not role_obj:
                logger.error(f"Не удалось создать роль: {role}")
                return None

            tenant_obj = None
            if tenant:
                tenant_obj = self._get_or_create_tenant(tenant)
                if not tenant_obj:
                    logger.warning(f"Не удалось создать tenant: {tenant}")

            device_data = {
                "name": name,
                "device_type": dtype.id,
                "site": site_obj.id,
                "role": role_obj.id,
                "status": status,
            }

            if serial:
                device_data["serial"] = serial

            if tenant_obj:
                device_data["tenant"] = tenant_obj.id

            if platform:
                platform_obj = self._get_or_create_platform(platform)
                if platform_obj:
                    device_data["platform"] = platform_obj.id

            device = self.client.api.dcim.devices.create(device_data)
            logger.info(f"Создано устройство: {name}")
            return device

        except NetBoxValidationError as e:
            logger.error(f"Ошибка валидации устройства {name}: {format_error_for_log(e)}")
            return None
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox создания устройства {name}: {format_error_for_log(e)}")
            return None
        except Exception as e:
            logger.error(f"Неизвестная ошибка создания устройства {name}: {e}")
            return None

    def sync_devices_from_inventory(
        self: SyncBase,
        inventory_data: List[DeviceInfo],
        site: str = "Main",
        role: str = "switch",
        update_existing: bool = True,
        cleanup: bool = False,
        tenant: Optional[str] = None,
        set_primary_ip: bool = False,
    ) -> Dict[str, Any]:
        """
        Синхронизирует устройства в NetBox из инвентаризационных данных.

        Args:
            inventory_data: Список DeviceInfo
            site: Сайт по умолчанию
            role: Роль по умолчанию
            update_existing: Обновлять существующие устройства
            cleanup: Удалять устройства не из списка
            tenant: Арендатор
            set_primary_ip: Устанавливать primary IP

        Returns:
            Dict: Статистика {created, updated, skipped, deleted, failed, details}
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "deleted": 0, "failed": 0}
        details = {"create": [], "update": [], "skip": [], "delete": []}

        devices = DeviceInfo.ensure_list(inventory_data)
        inventory_names = set()

        for entry in devices:
            name = entry.name or entry.hostname
            model = entry.model or "Unknown"
            serial = entry.serial or ""
            manufacturer = entry.manufacturer or "Cisco"
            ip_address = entry.ip_address or ""
            platform = entry.platform or ""

            if not name:
                logger.warning("Пропущена запись без имени устройства")
                stats["failed"] += 1
                continue

            inventory_names.add(name)

            # Ищем устройство сначала по имени, потом по IP
            existing = self.client.get_device_by_name(name)
            if not existing and ip_address:
                # Fallback: ищем по IP если имя похоже на IP-адрес
                existing = self.client.get_device_by_ip(ip_address)
                if existing:
                    logger.info(f"Устройство найдено по IP {ip_address}: {existing.name}")
                    # Используем имя из NetBox для дальнейшей работы
                    name = existing.name
            if existing:
                if update_existing:
                    updated = self._update_device(
                        existing,
                        model=model,
                        serial=serial,
                        manufacturer=manufacturer,
                        platform=platform,
                        tenant=tenant,
                        site=site,
                        role=role,
                        primary_ip=ip_address if set_primary_ip else "",
                    )
                    if updated:
                        stats["updated"] += 1
                        details["update"].append({"name": name, "model": model, "ip": ip_address})
                    else:
                        stats["skipped"] += 1
                        details["skip"].append({"name": name, "reason": "no changes"})
                else:
                    logger.debug(f"Устройство {name} уже существует")
                    stats["skipped"] += 1
                    details["skip"].append({"name": name, "reason": "already exists"})
                continue

            result = self.create_device(
                name=name,
                device_type=model,
                site=site,
                role=role,
                manufacturer=manufacturer,
                serial=serial,
                platform=platform,
                tenant=tenant,
            )

            if result:
                stats["created"] += 1
                details["create"].append({"name": name, "model": model, "ip": ip_address})
            else:
                if not self.dry_run:
                    stats["failed"] += 1
                else:
                    stats["created"] += 1
                    details["create"].append({"name": name, "model": model, "ip": ip_address})

        if cleanup and tenant:
            deleted = self._cleanup_devices(inventory_names, site, tenant)
            stats["deleted"] = deleted

        logger.info(
            f"Синхронизация устройств: создано={stats['created']}, "
            f"обновлено={stats['updated']}, пропущено={stats['skipped']}, "
            f"удалено={stats['deleted']}, ошибок={stats['failed']}"
        )

        stats["details"] = details
        return stats

    def _update_device(
        self: SyncBase,
        device,
        model: str = "",
        serial: str = "",
        manufacturer: str = "",
        platform: str = "",
        tenant: Optional[str] = None,
        site: Optional[str] = None,
        role: Optional[str] = None,
        primary_ip: str = "",
    ) -> bool:
        """Обновляет существующее устройство в NetBox."""
        updates = {}

        serial = (serial or "").strip()
        model = (model or "").strip()
        platform = (platform or "").strip()
        tenant = (tenant or "").strip() if tenant else None
        site = (site or "").strip() if site else None
        role = (role or "").strip() if role else None
        primary_ip = (primary_ip or "").strip()

        current_serial = (device.serial or "").strip()
        current_model = (device.device_type.model if device.device_type else "").strip()
        current_platform = (device.platform.name if device.platform else "").strip()
        current_tenant = (device.tenant.name if device.tenant else "").strip()
        current_site = (device.site.name if device.site else "").strip()
        current_role = (device.role.name if device.role else "").strip()

        logger.debug(
            f"Сравнение устройства {device.name}: "
            f"serial=[{serial!r}] vs [{current_serial!r}], "
            f"model=[{model!r}→{normalize_device_model(model)!r}] vs [{current_model!r}]"
        )

        if serial and serial != current_serial:
            updates["serial"] = serial

        if model and model != "Unknown":
            normalized_model = normalize_device_model(model)
            if normalized_model != current_model:
                mfr = self._get_or_create_manufacturer(manufacturer or "Cisco")
                if mfr:
                    dtype = self._get_or_create_device_type(model, mfr.id)
                    if dtype:
                        updates["device_type"] = dtype.id

        if platform and platform != current_platform:
            platform_obj = self._get_or_create_platform(platform)
            if platform_obj:
                updates["platform"] = platform_obj.id

        if tenant and tenant != current_tenant:
            tenant_obj = self._get_or_create_tenant(tenant)
            if tenant_obj:
                updates["tenant"] = tenant_obj.id

        if site and site != current_site:
            site_obj = self._get_or_create_site(site)
            if site_obj:
                updates["site"] = site_obj.id

        if role and role != current_role:
            role_obj = self._get_or_create_role(role)
            if role_obj:
                updates["role"] = role_obj.id

        need_primary_ip = False
        if primary_ip:
            primary_ip_only = primary_ip.split("/")[0]
            current_primary = ""
            if device.primary_ip4:
                current_primary = str(device.primary_ip4.address).split("/")[0]
            if primary_ip_only != current_primary:
                need_primary_ip = True

        if not updates and not need_primary_ip:
            logger.debug(f"  → нет изменений для {device.name}")
            return False

        if self.dry_run:
            if updates:
                logger.info(f"[DRY-RUN] Обновление устройства {device.name}: {updates}")
            if need_primary_ip:
                logger.info(f"[DRY-RUN] Установка primary IP {primary_ip} для {device.name}")
            return True

        try:
            if updates:
                device.update(updates)
                logger.info(f"Обновлено устройство: {device.name}")

            if need_primary_ip:
                ip_set = self._set_primary_ip(device, primary_ip)
                if not ip_set:
                    logger.warning(f"Primary IP {primary_ip} не установлен для {device.name}")

            return True
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox обновления устройства {device.name}: {format_error_for_log(e)}")
            return False
        except Exception as e:
            logger.error(f"Неизвестная ошибка обновления устройства {device.name}: {e}")
            return False

    def _cleanup_devices(
        self: SyncBase,
        inventory_names: set,
        site: str,
        tenant: str,
    ) -> int:
        """Удаляет устройства из NetBox которых нет в списке."""
        deleted = 0

        try:
            site_slug = site.lower().replace(" ", "-")
            tenant_slug = tenant.lower().replace(" ", "-")

            netbox_devices = self.client.get_devices(site=site_slug, tenant=tenant_slug)
            logger.info(
                f"Найдено {len(netbox_devices)} устройств для проверки "
                f"(site={site_slug}, tenant={tenant_slug})"
            )
        except NetBoxConnectionError as e:
            logger.error(f"Ошибка подключения к NetBox: {format_error_for_log(e)}")
            return 0
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox получения устройств: {format_error_for_log(e)}")
            return 0
        except Exception as e:
            logger.error(f"Неизвестная ошибка получения устройств: {e}")
            return 0

        for device in netbox_devices:
            if device.name not in inventory_names:
                device_tenant = device.tenant.slug if device.tenant else None
                if device_tenant != tenant_slug:
                    logger.debug(
                        f"Пропуск {device.name}: tenant={device_tenant} != {tenant_slug}"
                    )
                    continue

                if self.dry_run:
                    logger.info(f"[DRY-RUN] Удаление устройства: {device.name}")
                    deleted += 1
                else:
                    try:
                        device.delete()
                        logger.info(f"Удалено устройство: {device.name}")
                        deleted += 1
                    except NetBoxError as e:
                        logger.error(f"Ошибка NetBox удаления устройства {device.name}: {format_error_for_log(e)}")
                    except Exception as e:
                        logger.error(f"Неизвестная ошибка удаления устройства {device.name}: {e}")

        return deleted
