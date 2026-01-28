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


def get_netbox_token(config_token: Optional[str] = None) -> Optional[str]:
    """
    Получает NetBox API токен из безопасного хранилища.

    Приоритет источников:
    1. Переменная окружения NETBOX_TOKEN
    2. Системное хранилище (Windows Credential Manager / Linux Secret Service)
    3. Параметр config_token (из config.yaml)

    Args:
        config_token: Токен из config.yaml (fallback)

    Returns:
        str: API токен или None

    Example:
        # Из переменной окружения
        export NETBOX_TOKEN="your-token"

        # Или сохранить в Credential Manager
        python -m network_collector config set-token

        # Использование
        token = get_netbox_token(config.netbox.token)
    """
    # 1. Переменная окружения (высший приоритет)
    env_token = os.getenv("NETBOX_TOKEN")
    if env_token:
        logger.debug("NetBox токен получен из переменной окружения NETBOX_TOKEN")
        return env_token.strip()

    # 2. Системное хранилище (keyring)
    try:
        import keyring

        stored_token = keyring.get_password("network_collector", "netbox_token")
        if stored_token:
            logger.debug("NetBox токен получен из системного хранилища (Credential Manager)")
            return stored_token.strip()
    except ImportError:
        logger.debug("Библиотека keyring не установлена, пропускаем системное хранилище")
    except Exception as e:
        logger.warning(f"Ошибка при чтении токена из системного хранилища: {e}")

    # 3. Fallback на config.yaml
    if config_token:
        logger.debug("NetBox токен получен из config.yaml")
        return config_token.strip()

    logger.warning("NetBox токен не найден ни в одном источнике")
    return None


def set_netbox_token(token: str) -> bool:
    """
    Сохраняет NetBox API токен в системное хранилище.

    На Windows использует Credential Manager.
    На Linux использует Secret Service (Gnome Keyring).
    На macOS использует Keychain.

    Args:
        token: API токен для сохранения

    Returns:
        bool: True если успешно сохранено

    Raises:
        ImportError: Если keyring не установлен
        Exception: Если не удалось сохранить токен

    Example:
        set_netbox_token("4dd51a78084a1c18c7dc95f56a5355c692811c02")
    """
    try:
        import keyring

        keyring.set_password("network_collector", "netbox_token", token.strip())
        logger.info("NetBox токен успешно сохранён в системное хранилище")
        return True
    except ImportError:
        raise ImportError(
            "Библиотека keyring не установлена. "
            "Установите: pip install keyring"
        )
    except Exception as e:
        logger.error(f"Ошибка при сохранении токена: {e}")
        raise

