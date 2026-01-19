"""
Команда match-mac.

Сопоставление MAC-адресов с хостами из справочника.
"""

import logging

logger = logging.getLogger(__name__)


def cmd_match_mac(args, ctx=None) -> None:
    """Обработчик команды match-mac (сопоставление MAC с хостами)."""
    from ...configurator import DescriptionMatcher
    from ...fields_config import get_reverse_mapping
    import pandas as pd

    # Загружаем MAC-данные
    logger.info(f"Загрузка MAC-данных из {args.mac_file}...")
    mac_df = pd.read_excel(args.mac_file)

    # Получаем обратный маппинг из fields.yaml: display_name → field_name
    # Это позволяет преобразовать колонки Excel обратно в имена полей модели
    reverse_map = get_reverse_mapping("mac")

    # Переименовываем колонки: "MAC Address" → "mac", "Port" → "interface", etc.
    mac_df.columns = [
        reverse_map.get(col.lower(), col.lower())
        for col in mac_df.columns
    ]
    mac_data = mac_df.to_dict("records")
    logger.info(f"Загружено {len(mac_data)} записей MAC")

    # Создаём матчер
    matcher = DescriptionMatcher()

    # Загружаем справочник хостов
    if args.hosts_folder:
        matcher.load_hosts_folder(
            args.hosts_folder,
            mac_column=args.mac_column,
            name_column=args.name_column,
        )
    else:
        matcher.load_hosts_file(
            args.hosts_file,
            mac_column=args.mac_column,
            name_column=args.name_column,
        )

    # Сопоставляем (указываем имена полей из MAC файла)
    # Колонки преобразованы через reverse_map в оригинальные имена полей модели
    matched = matcher.match_mac_data(
        mac_data,
        mac_field="mac",           # Оригинальное имя поля в модели MACEntry
        hostname_field="hostname", # Оригинальное имя поля в модели MACEntry
        interface_field="interface",  # Оригинальное имя поля в модели MACEntry
        vlan_field="vlan",
        description_field="description",
    )

    # Сохраняем результат
    output_file = args.output
    matcher.save_matched(output_file)

    # Статистика
    stats = matcher.get_stats()
    logger.info("=== СТАТИСТИКА ===")
    logger.info(f"Справочник хостов: {stats['reference_hosts']} записей")
    logger.info(f"MAC-адресов: {stats['total_mac_entries']}")
    logger.info(f"Сопоставлено: {stats['matched']} ({stats['match_rate']})")
    logger.info(f"Не сопоставлено: {stats['unmatched']}")
    logger.info(f"Результат сохранён: {output_file}")
