"""
Синхронизация VLAN с NetBox.

Mixin класс для sync_vlans_from_interfaces.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from .base import (
    SyncBase, SyncStats, Interface,
    NetBoxError, NetBoxValidationError, format_error_for_log, logger,
)

logger = logging.getLogger(__name__)


class VLANsSyncMixin:
    """Mixin для синхронизации VLAN."""

    def sync_vlans_from_interfaces(
        self: SyncBase,
        device_name: str,
        interfaces: List[Interface],
        site: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Синхронизирует VLAN в NetBox на основе SVI интерфейсов.

        Args:
            device_name: Имя устройства в NetBox
            interfaces: Список интерфейсов (Interface модели)
            site: Сайт для создания VLAN

        Returns:
            Dict: Статистика {created, skipped, failed}
        """
        ss = SyncStats("created", "skipped", "failed")
        stats, details = ss.stats, ss.details

        vlan_pattern = re.compile(r"^[Vv]lan(\d+)$")
        interface_models = Interface.ensure_list(interfaces)

        vlans_to_create = {}

        for intf in interface_models:
            match = vlan_pattern.match(intf.name)
            if match:
                vid = int(match.group(1))
                description = intf.description.strip() if intf.description else ""
                vlan_name = description if description else f"VLAN {vid}"
                vlans_to_create[vid] = vlan_name

        if not vlans_to_create:
            logger.info(f"VLAN SVI интерфейсы не найдены на {device_name}")
            return stats

        logger.info(f"Найдено {len(vlans_to_create)} VLAN SVI на {device_name}")

        for vid, name in vlans_to_create.items():
            existing = self.client.get_vlan_by_vid(vid, site=site)
            if existing:
                logger.debug(f"VLAN {vid} уже существует")
                stats["skipped"] += 1
                continue

            if self.dry_run:
                logger.info(f"[DRY-RUN] Создание VLAN: {vid} ({name})")
                stats["created"] += 1
                continue

            try:
                self.client.create_vlan(
                    vid=vid,
                    name=name,
                    site=site,
                    status="active",
                )
                stats["created"] += 1
            except NetBoxValidationError as e:
                logger.error(f"Ошибка валидации VLAN {vid}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except NetBoxError as e:
                logger.error(f"Ошибка NetBox создания VLAN {vid}: {format_error_for_log(e)}")
                stats["failed"] += 1
            except Exception as e:
                logger.error(f"Неизвестная ошибка создания VLAN {vid}: {e}")
                stats["failed"] += 1

        logger.info(
            f"Синхронизация VLAN {device_name}: "
            f"создано={stats['created']}, пропущено={stats['skipped']}, "
            f"ошибок={stats['failed']}"
        )
        return stats
