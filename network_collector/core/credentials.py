"""
Модуль управления учётными данными.

Предоставляет безопасные способы получения логина и пароля:
- Интерактивный ввод (getpass)
- Переменные окружения
- Файл с credentials (опционально)

Пример использования:
    creds = CredentialsManager()
    username, password, secret = creds.get_credentials()
"""

import os
import logging
from getpass import getpass
from dataclasses import dataclass
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Credentials:
    """
    Контейнер для учётных данных.
    
    Attributes:
        username: Имя пользователя
        password: Пароль
        secret: Enable пароль (опционально)
    """
    username: str
    password: str
    secret: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Преобразует в словарь для Netmiko."""
        result = {
            "username": self.username,
            "password": self.password,
        }
        if self.secret:
            result["secret"] = self.secret
        return result


class CredentialsManager:
    """
    Менеджер учётных данных.
    
    Поддерживает несколько источников credentials:
    1. Переменные окружения (NET_USERNAME, NET_PASSWORD, NET_SECRET)
    2. Интерактивный ввод через терминал
    3. Явная передача при создании
    
    Attributes:
        _credentials: Закэшированные учётные данные
        
    Example:
        # Автоматический выбор источника
        manager = CredentialsManager()
        creds = manager.get_credentials()
        
        # Явная передача
        manager = CredentialsManager(
            username="admin",
            password="secret123"
        )
    """
    
    # Имена переменных окружения
    ENV_USERNAME = "NET_USERNAME"
    ENV_PASSWORD = "NET_PASSWORD"
    ENV_SECRET = "NET_SECRET"
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        secret: Optional[str] = None,
    ):
        """
        Инициализация менеджера.
        
        Args:
            username: Имя пользователя (опционально)
            password: Пароль (опционально)
            secret: Enable пароль (опционально)
        """
        self._credentials: Optional[Credentials] = None
        
        # Если переданы явно — используем их
        if username and password:
            self._credentials = Credentials(
                username=username,
                password=password,
                secret=secret,
            )
    
    def get_credentials(self, interactive: bool = True) -> Credentials:
        """
        Получает учётные данные.
        
        Порядок проверки:
        1. Уже закэшированные
        2. Переменные окружения
        3. Интерактивный ввод (если interactive=True)
        
        Args:
            interactive: Разрешить интерактивный ввод
            
        Returns:
            Credentials: Объект с учётными данными
            
        Raises:
            ValueError: Если не удалось получить credentials
        """
        # Возвращаем закэшированные
        if self._credentials:
            return self._credentials
        
        # Пробуем переменные окружения
        env_username = os.getenv(self.ENV_USERNAME)
        env_password = os.getenv(self.ENV_PASSWORD)
        env_secret = os.getenv(self.ENV_SECRET)
        
        if env_username and env_password:
            logger.info("Используем учётные данные из переменных окружения")
            self._credentials = Credentials(
                username=env_username,
                password=env_password,
                secret=env_secret,
            )
            return self._credentials
        
        # Интерактивный ввод
        if interactive:
            logger.info("Запрос учётных данных интерактивно")
            self._credentials = self._prompt_credentials()
            return self._credentials
        
        raise ValueError(
            "Не удалось получить учётные данные. "
            f"Установите {self.ENV_USERNAME} и {self.ENV_PASSWORD} "
            "или включите интерактивный режим."
        )
    
    def _prompt_credentials(self) -> Credentials:
        """Запрашивает учётные данные интерактивно."""
        print("\n" + "=" * 50)
        print("Введите учётные данные для подключения")
        print("=" * 50)
        
        username = input("Имя пользователя: ").strip()
        password = getpass("Пароль: ")
        secret = getpass("Enable пароль (Enter если не требуется): ")
        
        return Credentials(
            username=username,
            password=password,
            secret=secret if secret else None,
        )

