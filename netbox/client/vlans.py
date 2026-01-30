"""
Mixin для работы с VLAN в NetBox.
"""

import logging
from typing import List, Any, Optional

logger = logging.getLogger(__name__)


class VLANsMixin:
    """Методы для работы с VLAN."""

    def get_vlans(
        self,
        site: Optional[str] = None,
        **filters,
    ) -> List[Any]:
        """
        Получает список VLAN.

        Args:
            site: Фильтр по сайту (name или slug)
            **filters: Дополнительные фильтры

        Returns:
            List: Список VLAN
        """
        params = {}
        if site:
            # NetBox API требует slug сайта, конвертируем
            site_slug = site.lower().replace(" ", "-")
            params["site"] = site_slug
        params.update(filters)

        vlans = list(self.api.ipam.vlans.filter(**params))
        logger.debug(f"Получено VLAN: {len(vlans)}")
        return vlans

    def get_vlan_by_vid(self, vid: int, site: Optional[str] = None) -> Optional[Any]:
        """
        Находит VLAN по номеру.

        Args:
            vid: Номер VLAN
            site: Сайт (name или slug, опционально)

        Returns:
            VLAN или None (первый найденный если несколько)
        """
        params = {"vid": vid}
        if site:
            site_slug = site.lower().replace(" ", "-")
            params["site"] = site_slug
        vlans = list(self.api.ipam.vlans.filter(**params))
        return vlans[0] if vlans else None

    def create_vlan(
        self,
        vid: int,
        name: str,
        site: Optional[str] = None,
        status: str = "active",
        description: str = "",
        **kwargs,
    ) -> Any:
        """
        Создаёт VLAN в NetBox.

        Args:
            vid: Номер VLAN (1-4094)
            name: Название VLAN
            site: Сайт (slug или id)
            status: Статус (active, reserved, deprecated)
            description: Описание
            **kwargs: Дополнительные параметры

        Returns:
            Созданный VLAN
        """
        data = {
            "vid": vid,
            "name": name,
            "status": status,
            **kwargs,
        }

        if description:
            data["description"] = description

        if site:
            site_obj = self.api.dcim.sites.get(slug=site)
            if not site_obj:
                site_obj = self.api.dcim.sites.get(name=site)
            if site_obj:
                data["site"] = site_obj.id

        vlan = self.api.ipam.vlans.create(data)
        logger.info(f"Создан VLAN: {vid} ({name})")
        return vlan

    def update_interface_vlan(
        self,
        interface_id: int,
        mode: str = "access",
        untagged_vlan: Optional[int] = None,
        tagged_vlans: Optional[List[int]] = None,
    ) -> Any:
        """
        Обновляет VLAN привязку интерфейса.

        Args:
            interface_id: ID интерфейса
            mode: Режим порта (access, tagged, tagged-all)
            untagged_vlan: ID VLAN для untagged трафика
            tagged_vlans: Список ID VLAN для tagged трафика

        Returns:
            Обновлённый интерфейс
        """
        interface = self.api.dcim.interfaces.get(interface_id)
        if not interface:
            logger.warning(f"Интерфейс {interface_id} не найден")
            return None

        updates = {"mode": mode}

        if untagged_vlan:
            updates["untagged_vlan"] = untagged_vlan

        if tagged_vlans:
            updates["tagged_vlans"] = tagged_vlans

        interface.update(updates)
        logger.debug(f"Обновлён интерфейс {interface.name}: mode={mode}")
        return interface
