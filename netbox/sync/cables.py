"""
Синхронизация кабелей с NetBox из LLDP/CDP данных.

Mixin класс для sync_cables_from_lldp и связанных методов.
"""

import logging
from typing import List, Dict, Any, Optional

from .base import (
    SyncBase, SyncStats, LLDPNeighbor, get_cable_endpoints,
    NetBoxError, format_error_for_log, logger,
    normalize_interface_short,
)
from ...core.constants import normalize_hostname

logger = logging.getLogger(__name__)


class CablesSyncMixin:
    """Mixin для синхронизации кабелей."""

    def sync_cables_from_lldp(
        self: SyncBase,
        lldp_data: List[LLDPNeighbor],
        skip_unknown: bool = True,
        cleanup: bool = False,
    ) -> Dict[str, int]:
        """
        Создаёт кабели в NetBox на основе LLDP/CDP данных.

        Args:
            lldp_data: Список LLDP/CDP соседей
            skip_unknown: Пропускать соседей с типом "unknown"
            cleanup: Удалять кабели из NetBox которых нет в LLDP данных

        Returns:
            Dict: Статистика {created, deleted, skipped, failed, already_exists}
        """
        ss = SyncStats("created", "deleted", "skipped", "failed", "already_exists")
        stats, details = ss.stats, ss.details
        # Для дедупликации кабелей в preview (LLDP видит кабель с обеих сторон)
        seen_cables = set()

        neighbors = LLDPNeighbor.ensure_list(lldp_data)

        lldp_devices = set()
        for entry in neighbors:
            if entry.hostname:
                lldp_devices.add(entry.hostname)

        for entry in neighbors:
            local_device = entry.hostname
            local_intf = entry.local_interface
            remote_hostname = entry.remote_hostname
            remote_port = entry.remote_port
            neighbor_type = entry.neighbor_type or "unknown"

            if neighbor_type == "unknown" and skip_unknown:
                logger.debug(f"Пропущен unknown сосед на {local_device}:{local_intf}")
                stats["skipped"] += 1
                continue

            local_device_obj = self._find_device(local_device)
            if not local_device_obj:
                logger.warning(f"Устройство не найдено в NetBox: {local_device}")
                stats["failed"] += 1
                continue

            local_intf_obj = self._find_interface(local_device_obj.id, local_intf)
            if not local_intf_obj:
                logger.warning(f"Интерфейс не найден: {local_device}:{local_intf}")
                stats["failed"] += 1
                continue

            remote_device_obj = self._find_neighbor_device(entry)
            if not remote_device_obj:
                logger.warning(
                    f"Сосед не найден в NetBox: {remote_hostname} "
                    f"(тип: {neighbor_type})"
                )
                stats["skipped"] += 1
                continue

            remote_intf_obj = self._find_interface(remote_device_obj.id, remote_port)
            if not remote_intf_obj:
                logger.warning(
                    f"Интерфейс соседа не найден: "
                    f"{remote_device_obj.name}:{remote_port}"
                    f" (raw LLDP: '{entry.remote_port}')"
                )
                stats["skipped"] += 1
                continue

            local_intf_type = getattr(local_intf_obj.type, 'value', None) if local_intf_obj.type else None
            remote_intf_type = getattr(remote_intf_obj.type, 'value', None) if remote_intf_obj.type else None

            if local_intf_type == "lag":
                logger.debug(
                    f"Пропускаем LAG интерфейс: {local_device}:{local_intf}"
                )
                stats["skipped"] += 1
                continue
            if remote_intf_type == "lag":
                logger.debug(
                    f"Пропускаем LAG интерфейс соседа: {remote_device_obj.name}:{remote_port}"
                )
                stats["skipped"] += 1
                continue

            result = self._create_cable(local_intf_obj, remote_intf_obj)

            if result == "created":
                # Используем имена из NetBox объектов (нормализованные, без пробелов)
                a_name = local_device_obj.name
                b_name = remote_device_obj.name
                a_intf_name = local_intf_obj.name
                b_intf_name = remote_intf_obj.name
                # Дедупликация: сортируем endpoints чтобы A-B и B-A были одинаковы
                cable_key = tuple(sorted([
                    f"{a_name}:{a_intf_name}",
                    f"{b_name}:{b_intf_name}",
                ]))
                if cable_key not in seen_cables:
                    seen_cables.add(cable_key)
                    stats["created"] += 1
                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Создание кабеля: {a_name}:{a_intf_name} ↔ {b_name}:{b_intf_name}")
                    details["create"].append({
                        "name": f"{a_name}:{a_intf_name} ↔ {b_name}:{b_intf_name}",
                        "a_device": a_name,
                        "a_interface": a_intf_name,
                        "b_device": b_name,
                        "b_interface": b_intf_name,
                    })
            elif result == "exists":
                stats["already_exists"] += 1
            else:
                stats["failed"] += 1

        if cleanup and lldp_devices:
            cleanup_result = self._cleanup_cables(neighbors, lldp_devices)
            deleted_details = cleanup_result["deleted"]
            stats["deleted"] = len(deleted_details)
            details["delete"].extend(deleted_details)
            if cleanup_result["failed_devices"] > 0:
                stats["failed"] += cleanup_result["failed_devices"]
                logger.warning(
                    f"Cleanup кабелей: {cleanup_result['failed_devices']} "
                    f"устройств пропущено из-за ошибок"
                )

        logger.info(
            f"Синхронизация кабелей: создано={stats['created']}, "
            f"удалено={stats['deleted']}, существует={stats['already_exists']}, "
            f"пропущено={stats['skipped']}, ошибок={stats['failed']}"
        )
        stats["details"] = details
        return stats

    def _cleanup_cables(
        self: SyncBase,
        lldp_neighbors: List[LLDPNeighbor],
        lldp_devices: set,
    ) -> Dict[str, Any]:
        """Удаляет кабели из NetBox которых нет в LLDP данных.

        Returns:
            Dict: {"deleted": List[Dict], "failed_devices": int}
        """
        deleted_details = []
        failed_devices = 0

        # Строим set валидных endpoints с нормализованными hostname и интерфейсами
        # ВАЖНО: используем normalize_interface_short (не full!) потому что разные
        # вендоры имеют разные полные имена для одного типа:
        # Cisco: HundredGigE, QTech: HundredGigabitEthernet → оба → Hu (short)
        valid_endpoints = set()
        for entry in lldp_neighbors:
            if entry.hostname and entry.local_interface and entry.remote_hostname and entry.remote_port:
                local_intf_norm = normalize_interface_short(entry.local_interface, lowercase=True)
                remote_port_norm = normalize_interface_short(entry.remote_port, lowercase=True)
                endpoints = tuple(sorted([
                    f"{normalize_hostname(entry.hostname)}:{local_intf_norm}",
                    f"{normalize_hostname(entry.remote_hostname)}:{remote_port_norm}",
                ]))
                valid_endpoints.add(endpoints)

        # Нормализуем lldp_devices для проверки
        normalized_lldp_devices = {normalize_hostname(d) for d in lldp_devices}

        for device_name in lldp_devices:
            device = self._find_device(device_name)
            if not device:
                failed_devices += 1
                continue

            try:
                cables = self.client.get_cables(device_id=device.id)
            except Exception as e:
                logger.error(f"Ошибка получения кабелей для {device_name}: {e}")
                failed_devices += 1
                continue

            for cable in cables:
                raw_endpoints = get_cable_endpoints(cable)
                if not raw_endpoints:
                    continue
                # Нормализуем hostname (strip domain) и interface name (short form)
                # Short form нужна потому что NetBox может хранить HundredGigabitEthernet,
                # а LLDP дать HundredGigE — оба → Hu (одинаковая short form)
                cable_endpoints = tuple(sorted(
                    f"{normalize_hostname(ep.split(':')[0])}:{normalize_interface_short(':'.join(ep.split(':')[1:]), lowercase=True)}"
                    for ep in raw_endpoints
                ))
                if cable_endpoints not in valid_endpoints:
                    endpoint_devices = set()
                    for ep in cable_endpoints:
                        dev = ep.split(":")[0]
                        endpoint_devices.add(dev)

                    if endpoint_devices.issubset(normalized_lldp_devices):
                        # Формируем детали до удаления
                        endpoints_list = list(cable_endpoints)
                        cable_detail = {
                            "name": " ↔ ".join(endpoints_list),
                        }
                        if len(endpoints_list) >= 2:
                            a_parts = endpoints_list[0].split(":")
                            b_parts = endpoints_list[1].split(":")
                            cable_detail["a_device"] = a_parts[0] if a_parts else ""
                            cable_detail["a_interface"] = a_parts[1] if len(a_parts) > 1 else ""
                            cable_detail["b_device"] = b_parts[0] if b_parts else ""
                            cable_detail["b_interface"] = b_parts[1] if len(b_parts) > 1 else ""

                        self._delete_cable(cable)
                        deleted_details.append(cable_detail)

        return {"deleted": deleted_details, "failed_devices": failed_devices}

    def _delete_cable(self: SyncBase, cable) -> None:
        """Удаляет кабель из NetBox."""
        if self.dry_run:
            endpoints = get_cable_endpoints(cable)
            endpoints_str = " <-> ".join(endpoints) if endpoints else f"cable#{cable.id}"
            logger.info(f"[DRY-RUN] Удаление кабеля: {endpoints_str}")
            return

        try:
            cable.delete()
            endpoints = get_cable_endpoints(cable)
            endpoints_str = " <-> ".join(endpoints) if endpoints else f"cable#{cable.id}"
            logger.info(f"Удалён кабель: {endpoints_str}")
        except Exception as e:
            logger.error(f"Ошибка удаления кабеля: {e}")

    def _find_neighbor_device(
        self: SyncBase,
        entry: LLDPNeighbor,
    ) -> Optional[Any]:
        """Ищет устройство соседа в NetBox."""
        hostname = entry.remote_hostname or ""
        mac = entry.remote_mac
        ip = entry.remote_ip
        neighbor_type = entry.neighbor_type or "unknown"

        if neighbor_type == "hostname":
            clean_hostname = normalize_hostname(hostname)
            device = self._find_device(clean_hostname)
            if device:
                return device

            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    logger.debug(f"Устройство {hostname} найдено по IP {ip}")
                    return device

            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    logger.debug(f"Устройство {hostname} найдено по MAC {mac}")
                    return device

        elif neighbor_type == "mac":
            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    return device

            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    logger.debug(f"Устройство (MAC {mac}) найдено по IP {ip}")
                    return device

        elif neighbor_type == "ip":
            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    return device

            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    logger.debug(f"Устройство (IP {ip}) найдено по MAC {mac}")
                    return device

        else:
            if ip:
                device = self.client.get_device_by_ip(ip)
                if device:
                    return device
            if mac:
                device = self._find_device_by_mac(mac)
                if device:
                    return device

        return None

    def _create_cable(
        self: SyncBase,
        interface_a,
        interface_b,
    ) -> str:
        """
        Создаёт кабель между интерфейсами.

        Returns:
            str: "created", "exists", "error"
        """
        if interface_a.cable or interface_b.cable:
            return "exists"

        if self.create_only is False and self.update_only:
            return "exists"

        if self.dry_run:
            # Логируем только уникальные кабели (дедупликация в вызывающем коде)
            # Здесь просто возвращаем "created", лог пишется в sync_cables_from_lldp
            return "created"

        try:
            self.client.api.dcim.cables.create(
                {
                    "a_terminations": [
                        {
                            "object_type": "dcim.interface",
                            "object_id": interface_a.id,
                        }
                    ],
                    "b_terminations": [
                        {
                            "object_type": "dcim.interface",
                            "object_id": interface_b.id,
                        }
                    ],
                    "status": "connected",
                }
            )
            logger.info(
                f"Создан кабель: {interface_a.device.name}:{interface_a.name} ↔ "
                f"{interface_b.device.name}:{interface_b.name}"
            )
            return "created"
        except NetBoxError as e:
            logger.error(f"Ошибка NetBox при создании кабеля: {format_error_for_log(e)}")
            return "error"
        except Exception as e:
            logger.error(f"Неизвестная ошибка создания кабеля: {e}")
            return "error"
