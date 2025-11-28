"""
Основная логика сбора MAC-адресов с устройств.
"""

import logging
from typing import List, Tuple, Dict, Any, Optional
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException

from .config import (
    EXCLUDE_TRUNK_PORTS,
    COLLECT_STICKY_MAC,
    COLLECT_DYNAMIC_MAC,
    SHOW_DEVICE_STATUS,
)
from .utils import (
    normalize_mac,
    format_mac,
    normalize_interface_name,
    get_interface_description,
    should_exclude_interface,
)
from .parsers import get_parser


# Настройка логирования
logger = logging.getLogger(__name__)


def collect_from_device(device_params: Dict[str, Any]) -> Tuple[List, str]:
    """
    Собирает MAC-адреса с одного устройства.

    Args:
        device_params: параметры подключения для Netmiko
            {
                "device_type": "cisco_ios",
                "host": "192.168.1.1",
                "username": "admin",
                "password": "password",
                "secret": "enable_password",  # опционально
            }

    Returns:
        Tuple[List, str]: (список записей MAC, hostname устройства)
        Каждая запись: [hostname, interface, description, mac, type, vlan, status?]

    Raises:
        NetmikoTimeoutException: таймаут подключения
        NetmikoAuthenticationException: ошибка аутентификации
        ValueError: неподдерживаемый тип устройства
    """
    device_type = device_params.get("device_type", "cisco_ios")
    host = device_params.get("host", "unknown")

    # Получаем парсер для данного типа устройства
    parser = get_parser(device_type)
    commands = parser.get_commands()

    logger.info(f"Подключение к {host} ({parser.vendor_name})")

    with ConnectHandler(**device_params) as connection:
        # Переходим в enable режим если нужно
        if device_params.get("secret"):
            connection.enable()

        # Получаем hostname из prompt (надёжнее чем парсить команду)
        # Пример: "SW-CORE-01#" -> "SW-CORE-01"
        prompt = connection.find_prompt()
        hostname = prompt.strip("#>$ ").strip()
        if not hostname:
            hostname = "Unknown"
        logger.info(f"Hostname: {hostname}")

        # Получаем описания интерфейсов
        interfaces_output = connection.send_command(commands["interfaces"])
        interfaces = parser.parse_interfaces_description(interfaces_output)
        logger.debug(f"Найдено интерфейсов: {len(interfaces)}")

        # Получаем trunk интерфейсы (если включена фильтрация)
        trunk_interfaces = set()
        if EXCLUDE_TRUNK_PORTS:
            trunk_output = connection.send_command(commands["trunk"])
            trunk_interfaces = parser.parse_trunk_interfaces(trunk_output)
            logger.debug(f"Найдено trunk портов: {len(trunk_interfaces)}")

        # Получаем MAC-таблицу
        mac_entries = []
        if COLLECT_DYNAMIC_MAC:
            mac_output = connection.send_command(commands["mac_table"])
            mac_entries = parser.parse_mac_address_table(mac_output)
            logger.debug(f"Найдено MAC в таблице: {len(mac_entries)}")

        # Получаем sticky MAC
        sticky_entries = []
        if COLLECT_STICKY_MAC:
            config_output = connection.send_command(commands["running_config"])
            sticky_entries = parser.parse_sticky_mac(config_output)
            logger.debug(f"Найдено sticky MAC: {len(sticky_entries)}")

    # Объединяем данные
    result = merge_mac_data(
        mac_entries, sticky_entries, interfaces, hostname, trunk_interfaces
    )

    logger.info(f"Собрано уникальных MAC: {len(result)}")

    return result, hostname


def merge_mac_data(
    mac_table_entries: List[Tuple[str, str, str, str]],
    sticky_entries: List[Tuple[str, str, str]],
    interfaces: Dict[str, str],
    hostname: str,
    trunk_interfaces: set = None,
) -> List[List]:
    """
    Объединяет MAC-адреса из таблицы и sticky port-security.

    Args:
        mac_table_entries: список (interface, mac, type, vlan) из MAC-таблицы
        sticky_entries: список (interface, mac, vlan) из sticky
        interfaces: словарь {interface: description}
        hostname: имя устройства
        trunk_interfaces: множество trunk интерфейсов

    Returns:
        Список записей [hostname, interface, description, mac, type, vlan, status?]
    """
    if trunk_interfaces is None:
        trunk_interfaces = set()

    mac_dict = {}
    macs_in_table = set()  # Для определения online/offline

    # Добавляем MAC из таблицы
    if COLLECT_DYNAMIC_MAC:
        for iface, mac, mac_type, vlan in mac_table_entries:
            short_iface = normalize_interface_name(iface)

            if should_exclude_interface(short_iface):
                continue
            if EXCLUDE_TRUNK_PORTS and (
                iface in trunk_interfaces or short_iface in trunk_interfaces
            ):
                continue

            norm_mac = normalize_mac(mac)
            macs_in_table.add(norm_mac)

            entry_type = mac_type.lower() if mac_type else "dynamic"

            mac_dict[norm_mac] = {
                "hostname": hostname,
                "interface": short_iface,
                "description": get_interface_description(interfaces, iface),
                "mac": mac,
                "type": entry_type,
                "vlan": vlan,
            }

    # Добавляем sticky MAC (имеют приоритет)
    if COLLECT_STICKY_MAC:
        for iface, mac, vlan in sticky_entries:
            short_iface = normalize_interface_name(iface)

            if should_exclude_interface(short_iface):
                continue
            if EXCLUDE_TRUNK_PORTS and (
                iface in trunk_interfaces or short_iface in trunk_interfaces
            ):
                continue

            norm_mac = normalize_mac(mac)

            mac_dict[norm_mac] = {
                "hostname": hostname,
                "interface": short_iface,
                "description": get_interface_description(interfaces, iface),
                "mac": mac,
                "type": "sticky",
                "vlan": vlan,
            }

    # Формируем результат
    result = []
    for norm_mac, data in mac_dict.items():
        status = "online" if norm_mac in macs_in_table else "offline"

        row = [
            data["hostname"],
            data["interface"],
            data["description"],
            format_mac(data["mac"]),
            data["type"],
            data["vlan"],
        ]

        if SHOW_DEVICE_STATUS:
            row.append(status)

        result.append(row)

    return result
