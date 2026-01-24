"""
Команда push-descriptions.

Применение описаний интерфейсов на устройства.
"""

import logging

from ..utils import prepare_collection

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
