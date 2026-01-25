"""
Базовый класс NetBox клиента.

Инициализация подключения к NetBox API.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Пробуем импортировать pynetbox
try:
    import pynetbox

    PYNETBOX_AVAILABLE = True
except ImportError:
    PYNETBOX_AVAILABLE = False
    logger.warning("pynetbox не установлен. pip install pynetbox")


class NetBoxClientBase:
    """
    Базовый класс для NetBox клиента.

    Отвечает за инициализацию подключения к NetBox API.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        ssl_verify: bool = True,
    ):
        """
        Инициализация клиента NetBox.

        Токен ищется в следующем порядке:
        1. Параметр token
        2. get_netbox_token() - проверяет env NETBOX_TOKEN, Credential Manager, config.yaml

        Args:
            url: URL NetBox сервера (или env NETBOX_URL)
            token: API токен (опционально)
            ssl_verify: Проверять SSL сертификат

        Raises:
            ImportError: pynetbox не установлен
            ValueError: URL или токен не указаны
        """
        if not PYNETBOX_AVAILABLE:
            raise ImportError(
                "pynetbox не установлен. Установите: pip install pynetbox"
            )

        from ...core.credentials import get_netbox_token

        # Получаем URL из параметров или переменных окружения
        self.url = url or os.environ.get("NETBOX_URL")

        # Получаем токен через безопасное хранилище
        self._token = get_netbox_token(config_token=token)

        if not self.url:
            raise ValueError(
                "NetBox URL не указан. Укажите url или установите NETBOX_URL"
            )
        if not self._token:
            raise ValueError(
                "NetBox токен не указан. Добавьте токен в Windows Credential Manager "
                "или установите NETBOX_TOKEN. См. документацию SECURITY.md"
            )

        # Инициализируем pynetbox API
        self.api = pynetbox.api(self.url, token=self._token)

        # Настройка SSL
        if not ssl_verify:
            import requests

            session = requests.Session()
            session.verify = False
            self.api.http_session = session

        logger.info(f"NetBox клиент инициализирован: {self.url}")

    def _resolve_site_slug(self, site_name_or_slug: str) -> Optional[str]:
        """Находит slug сайта по имени или slug."""
        # Сначала пробуем как slug
        site_obj = self.api.dcim.sites.get(slug=site_name_or_slug.lower())
        if site_obj:
            return site_obj.slug

        # Пробуем как имя
        site_obj = self.api.dcim.sites.get(name=site_name_or_slug)
        if site_obj:
            return site_obj.slug

        # Ищем частичное совпадение
        sites = list(self.api.dcim.sites.filter(name__ic=site_name_or_slug))
        if len(sites) == 1:
            return sites[0].slug

        return None

    def _resolve_role_slug(self, role_name_or_slug: str) -> Optional[str]:
        """Находит slug роли по имени или slug."""
        # Сначала пробуем как slug
        role_obj = self.api.dcim.device_roles.get(slug=role_name_or_slug.lower())
        if role_obj:
            return role_obj.slug

        # Пробуем как имя
        role_obj = self.api.dcim.device_roles.get(name=role_name_or_slug)
        if role_obj:
            return role_obj.slug

        # Ищем частичное совпадение
        roles = list(self.api.dcim.device_roles.filter(name__ic=role_name_or_slug))
        if len(roles) == 1:
            return roles[0].slug

        return None
