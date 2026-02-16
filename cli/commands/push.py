"""
Команды push-descriptions и push-config.

Применение конфигураций на устройства.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from ..utils import prepare_collection, load_devices, get_credentials

logger = logging.getLogger(__name__)


def cmd_push_descriptions(args, ctx=None) -> None:
    """Обработчик команды push-descriptions (применение описаний)."""
    from ...configurator import DescriptionPusher
    import pandas as pd

    dry_run = not args.apply

    # Загружаем результаты сопоставления
    logger.info(f"Загрузка данных из {args.matched_file}...")
    df = pd.read_excel(args.matched_file)

    # Фильтруем только сопоставленные записи
    matched_df = df[df["Matched"] == "Yes"]
    if matched_df.empty:
        logger.warning("Нет сопоставленных записей для применения")
        return

    # Генерируем команды
    commands: dict = {}
    device_names: dict = {}  # IP -> hostname для логирования

    for _, row in matched_df.iterrows():
        hostname = row.get("Device", "")
        device_ip = row.get("IP", "")  # Колонка IP для поиска устройства
        interface = row.get("Interface", "")
        host_name = row.get("Host_Name", "")
        current_desc = row.get("Current_Description", "")

        if not device_ip or not interface or not host_name:
            continue

        # Проверяем условия
        is_empty = pd.isna(current_desc) or str(current_desc).strip() == ""

        if args.only_empty and not is_empty:
            continue
        if not args.overwrite and not is_empty:
            continue

        # Пропускаем если текущее описание совпадает с новым
        if str(current_desc).strip() == str(host_name).strip():
            continue

        # Используем IP как ключ для поиска устройства
        if device_ip not in commands:
            commands[device_ip] = []
            device_names[device_ip] = hostname

        commands[device_ip].append(f"interface {interface}")
        commands[device_ip].append(f"description {host_name}")

    if not commands:
        logger.warning("Нет команд для применения")
        return

    # Показываем что будет сделано
    total_interfaces = sum(len(cmds) // 2 for cmds in commands.values())
    logger.info(f"Будет обновлено {total_interfaces} интерфейсов на {len(commands)} устройствах")

    if dry_run:
        logger.info("=== DRY RUN (команды не будут применены) ===")
        for device_ip, cmds in commands.items():
            display_name = device_names.get(device_ip, device_ip)
            logger.info(f"\n{display_name} ({device_ip}):")
            for cmd in cmds:
                logger.info(f"  {cmd}")
        logger.info("\nДля применения используйте флаг --apply")
        return

    # Получаем учётные данные и устройства
    devices, credentials = prepare_collection(args)

    # Применяем
    pusher = DescriptionPusher(credentials)
    results = pusher.push_descriptions(devices, commands, dry_run=False)

    # Статистика
    success = sum(1 for r in results if r.success)
    failed = len(results) - success

    logger.info("=== РЕЗУЛЬТАТЫ ===")
    logger.info(f"Успешно: {success}")
    logger.info(f"Ошибки: {failed}")

    for r in results:
        if not r.success:
            logger.error(f"  {r.device}: {r.error}")


def _load_commands_yaml(filepath: str) -> Dict[str, Dict[str, List[str]]]:
    """
    Загружает команды из YAML-файла.

    Формат YAML (вложенный):
        _common:
          config:
            - logging buffered 16384
          exec:
            - show running-config | include logging

        cisco_iosxe:
          config:
            - spanning-tree portfast
          exec:
            - show spanning-tree summary

    Args:
        filepath: Путь к YAML-файлу

    Returns:
        Dict[str, Dict[str, List[str]]]: {platform: {"config": [...], "exec": [...]}}

    Raises:
        SystemExit: Если файл не найден или некорректен
    """
    import yaml

    path = Path(filepath)

    # Ищем файл в директории модуля если не найден по указанному пути
    if not path.exists():
        module_dir = Path(__file__).parent.parent.parent
        path = module_dir / filepath

    if not path.exists():
        logger.error(f"Файл команд не найден: {filepath}")
        sys.exit(1)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Ошибка парсинга YAML {filepath}: {e}")
        sys.exit(1)

    if not data or not isinstance(data, dict):
        logger.error(f"Файл {filepath} пуст или имеет неверный формат (ожидается dict)")
        sys.exit(1)

    # Парсинг: {platform: {"config": [...], "exec": [...]}}
    result: Dict[str, Dict[str, List[str]]] = {}

    for key, value in data.items():
        if not isinstance(value, dict):
            logger.error(
                f"Секция '{key}' должна содержать dict с ключами config/exec, "
                f"получен {type(value).__name__}"
            )
            sys.exit(1)

        section: Dict[str, List[str]] = {}
        for sub_key in ("config", "exec"):
            if sub_key in value:
                if not isinstance(value[sub_key], list):
                    logger.error(
                        f"Секция '{key}.{sub_key}' должна быть списком, "
                        f"получен {type(value[sub_key]).__name__}"
                    )
                    sys.exit(1)
                section[sub_key] = [str(cmd) for cmd in value[sub_key]]

        # Проверяем что нет неизвестных ключей
        unknown = set(value.keys()) - {"config", "exec"}
        if unknown:
            logger.error(
                f"Секция '{key}' содержит неизвестные ключи: {unknown}. "
                f"Допустимы: config, exec"
            )
            sys.exit(1)

        if not section:
            logger.error(f"Секция '{key}' должна содержать 'config' и/или 'exec'")
            sys.exit(1)

        result[key] = section

    return result


def _build_device_commands(
    commands_data: Dict[str, Dict[str, List[str]]],
    platform: str,
) -> Tuple[List[str], List[str]]:
    """
    Собирает итоговые списки команд для устройства.

    Config-команды: _common.config + {platform}.config (через send_config_set).
    Exec-команды: _common.exec + {platform}.exec (через send_command).

    Args:
        commands_data: Нормализованные данные {platform: {"config": [...], "exec": [...]}}
        platform: Платформа устройства (cisco_iosxe, arista_eos, etc.)

    Returns:
        Tuple[List[str], List[str]]: (config_commands, exec_commands)
    """
    common = commands_data.get("_common", {})
    platform_data = commands_data.get(platform, {})

    config_cmds = common.get("config", []) + platform_data.get("config", [])
    exec_cmds = common.get("exec", []) + platform_data.get("exec", [])

    return config_cmds, exec_cmds


def cmd_push_config(args, ctx=None) -> None:
    """Обработчик команды push-config (применение конфигурации по платформам)."""
    dry_run = not args.apply
    save_config = not getattr(args, "no_save", False)

    # Загружаем YAML с командами
    commands_data = _load_commands_yaml(args.commands)

    # Доступные платформы (без _common)
    available_platforms = [k for k in commands_data if k != "_common"]

    # Общие команды
    common_data = commands_data.get("_common", {})
    has_common_config = bool(common_data.get("config"))
    has_common_exec = bool(common_data.get("exec"))

    if not available_platforms and not has_common_config and not has_common_exec:
        logger.error("В файле нет команд ни для одной платформы")
        return

    if available_platforms:
        logger.info(f"Загружены команды для платформ: {', '.join(available_platforms)}")
    if has_common_config:
        logger.info(f"Общие config-команды (_common): {len(common_data['config'])} шт.")
    if has_common_exec:
        logger.info(f"Общие exec-команды (_common): {len(common_data['exec'])} шт.")

    # Загружаем устройства
    devices = load_devices(args.devices)

    # Фильтр по платформе (если указан)
    platform_filter = getattr(args, "platform", None)
    if platform_filter:
        devices = [d for d in devices if d.platform == platform_filter]
        if not devices:
            logger.error(f"Нет устройств с платформой '{platform_filter}'")
            return
        logger.info(f"Фильтр по платформе: {platform_filter} ({len(devices)} устройств)")

    # Собираем команды для каждого устройства (список кортежей, т.к. Device unhashable)
    device_commands = []  # [(device, config_cmds, exec_cmds), ...]
    skipped = []

    for device in devices:
        config_cmds, exec_cmds = _build_device_commands(commands_data, device.platform)
        if config_cmds or exec_cmds:
            device_commands.append((device, config_cmds, exec_cmds))
        else:
            skipped.append(device)

    if skipped:
        for d in skipped:
            logger.warning(f"  Пропущен {d.host} — нет команд для платформы '{d.platform}'")

    if not device_commands:
        logger.warning("Нет команд для применения ни на одном устройстве")
        return

    # Показываем превью
    total_devices = len(device_commands)
    total_commands = sum(
        len(cfg) + len(exc) for _, cfg, exc in device_commands
    )
    logger.info(f"Устройств: {total_devices}, команд всего: {total_commands}")

    if dry_run:
        logger.info("=== DRY RUN (команды не будут применены) ===")

    for device, config_cmds, exec_cmds in device_commands:
        logger.info(f"\n  {device.display_name} ({device.host}) [{device.platform}]:")
        if config_cmds:
            logger.info("    [config mode]:")
            for cmd in config_cmds:
                logger.info(f"      {cmd}")
        if exec_cmds:
            logger.info("    [exec mode]:")
            for cmd in exec_cmds:
                logger.info(f"      {cmd}")

    if dry_run:
        logger.info("\nДля применения используйте флаг --apply")
        return

    # Применяем команды
    from ...configurator import ConfigPusher

    credentials = get_credentials()
    pusher = ConfigPusher(credentials, save_config=save_config)

    results = []
    for device, config_cmds, exec_cmds in device_commands:
        result = pusher.push_config(
            device, config_cmds, dry_run=False,
            exec_commands=exec_cmds if exec_cmds else None,
        )
        results.append(result)

    # Статистика
    success = sum(1 for r in results if r.success)
    failed = len(results) - success
    total_sent = sum(r.commands_sent for r in results)

    logger.info("=== РЕЗУЛЬТАТЫ ===")
    logger.info(f"Устройств: {len(results)}")
    logger.info(f"Успешно: {success}")
    logger.info(f"Ошибки: {failed}")
    logger.info(f"Команд отправлено: {total_sent}")

    if save_config:
        logger.info("Конфигурация сохранена на устройствах")
    else:
        logger.info("Конфигурация НЕ сохранена (--no-save)")

    for r in results:
        if not r.success:
            logger.error(f"  {r.device}: {r.error}")
