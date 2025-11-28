#!/usr/bin/env python3
"""
Точка входа для сбора MAC-адресов с сетевых устройств.

Использование:
    python -m mac_collector.main
"""

import logging
import os
import re
from datetime import datetime
from getpass import getpass

# Импорт списка устройств из внешнего файла devices_ips.py
# Файл должен содержать список devices_list с устройствами
from devices_ips import devices_list

from .config import SAVE_PER_DEVICE, OUTPUT_FOLDER
from .collector import collect_from_device
from .excel_writer import save_to_excel


# Настройка логирования
logging.basicConfig(
    filename="mac_collector.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Основная функция сбора MAC-адресов."""
    print("=" * 60)
    print("Сбор MAC-адресов с сетевых устройств")
    print("=" * 60)

    # Запрашиваем учётные данные
    username = input("Введите имя пользователя: ")
    password = getpass("Введите пароль: ")
    enable_password = getpass("Введите enable пароль (если требуется, иначе Enter): ")

    if not devices_list:
        print("⚠️  Список устройств пуст!")
        print("   Отредактируйте файл: devices_ips.py")
        return

    # Создаём папку для отчётов
    if OUTPUT_FOLDER:
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)
            print(f"📁 Создана папка: {OUTPUT_FOLDER}")
        else:
            print(f"📁 Папка для отчётов: {OUTPUT_FOLDER}")
    print("-" * 60)

    all_data = []
    saved_files = []
    failed_devices = []
    current_date = datetime.now().strftime("%Y-%m-%d")

    for device in devices_list:
        host = device.get("host", "unknown")

        # Добавляем учётные данные к устройству
        device_params = device.copy()
        device_params["username"] = username
        device_params["password"] = password
        if enable_password:
            device_params["secret"] = enable_password

        try:
            print(f"\nПодключение к {host}...")
            data, hostname = collect_from_device(device_params)

            print(f"  Устройство: {hostname}")
            print(f"  Найдено MAC: {len(data)}")

            if SAVE_PER_DEVICE and data:
                # Очищаем hostname от недопустимых символов
                safe_hostname = (
                    re.sub(r'[<>:"/\\|?*]', "_", hostname) if hostname else host
                )
                filename = f"{safe_hostname}_{current_date}.xlsx"
                filepath = save_to_excel(data, filename)
                if filepath:
                    saved_files.append(filepath)
            else:
                all_data.extend(data)

            print("-" * 40)

        except Exception as e:
            logger.error(f"Ошибка при работе с {host}: {e}")
            print(f"❌ Ошибка на {host}: {e}")
            failed_devices.append(host)
            print("-" * 40)

    # Сохраняем общий файл
    if not SAVE_PER_DEVICE and all_data:
        filename = f"mac_tables_{current_date}.xlsx"
        filepath = save_to_excel(all_data, filename)
        if filepath:
            saved_files.append(filepath)

    # Итоги
    print("\n" + "=" * 60)
    print("Сбор MAC-таблиц завершён.")
    print("=" * 60)

    if saved_files:
        print(f"\n✅ Успешно сохранено файлов: {len(saved_files)}")
        for f in saved_files:
            print(f"   📄 {f}")

    if failed_devices:
        print(f"\n❌ Ошибки на устройствах: {len(failed_devices)}")
        for d in failed_devices:
            print(f"   ⚠️  {d}")

    print("=" * 60)


if __name__ == "__main__":
    main()
