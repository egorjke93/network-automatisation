"""
Общие утилиты для API сервисов.

Содержит функции, переиспользуемые несколькими сервисами.
"""

from typing import List, Optional, Dict, Any

from network_collector.core.device import Device
from network_collector.core.logging import get_logger

logger = get_logger(__name__)


def get_devices_for_operation(
    device_list: Optional[List[str]] = None,
    *,
    default_platform: str = "cisco_ios",
) -> List[Device]:
    """
    Получает список устройств для операций (сбор, синхронизация, push).

    Порядок приоритета:
    1. Если device_list указан - использует его, обогащая данными из device_service
    2. Если device_list пуст - получает enabled устройства из device_service
    3. Fallback на devices_ips.py

    Args:
        device_list: Список IP адресов (опционально).
                    None или [] = использовать все устройства из device management.
        default_platform: Платформа по умолчанию для устройств без данных.

    Returns:
        List[Device]: Список устройств для операций.

    Examples:
        >>> devices = get_devices_for_operation()  # все enabled устройства
        >>> devices = get_devices_for_operation(["10.0.0.1", "10.0.0.2"])  # конкретные
    """
    from .device_service import get_device_service

    device_service = get_device_service()

    # Создаём маппинг host -> device_data для обогащения
    all_device_data = device_service.get_all_devices()
    host_to_data: Dict[str, Dict[str, Any]] = {
        d["host"]: d for d in all_device_data if "host" in d
    }

    # Случай 1: Явно указан список IP
    if device_list:
        devices = []
        for ip in device_list:
            device_data = host_to_data.get(ip)
            if device_data:
                devices.append(Device(
                    host=device_data.get("host", ip),
                    platform=device_data.get("device_type", default_platform),
                ))
            else:
                # Устройство не найдено в базе - используем default
                logger.debug(f"Устройство {ip} не найдено в device management, используем platform={default_platform}")
                devices.append(Device(host=ip, platform=default_platform))
        return devices

    # Случай 2: Получаем enabled устройства из device_service
    hosts = device_service.get_device_hosts()
    if hosts:
        return [
            Device(
                host=ip,
                platform=host_to_data.get(ip, {}).get("device_type", default_platform),
            )
            for ip in hosts
        ]

    # Случай 3: Fallback на devices_ips.py
    try:
        from network_collector.devices_ips import devices_list

        logger.info("Используем устройства из devices_ips.py")
        return [
            Device(
                host=d.get("host", d) if isinstance(d, dict) else d,
                platform=d.get("device_type", default_platform) if isinstance(d, dict) else default_platform,
            )
            for d in devices_list
        ]
    except ImportError:
        logger.warning("devices_ips.py не найден, возвращаем пустой список")
        return []
    except Exception as e:
        logger.error(f"Ошибка загрузки devices_ips.py: {e}")
        return []


def get_device_platform_map() -> Dict[str, str]:
    """
    Возвращает маппинг host -> platform для всех устройств.

    Полезно когда нужно быстро узнать платформу по IP.

    Returns:
        Dict[str, str]: {ip: platform}
    """
    from .device_service import get_device_service

    device_service = get_device_service()
    all_devices = device_service.get_all_devices()

    return {
        d["host"]: d.get("device_type", "cisco_ios")
        for d in all_devices
        if "host" in d
    }
