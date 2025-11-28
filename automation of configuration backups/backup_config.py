from netmiko import ConnectHandler
import datetime
from getpass import getpass
from devices_ips import *
import logging
import os  # Импортируем модуль OS
import re  # Импортируем модуль регулярных выражений

# включение логирования
logging.basicConfig(filename="netmiko_global.log", level=logging.INFO)
logger = logging.getLogger("netmiko")

username = input("Введите имя пользователя: ")
password = getpass("Введите пароль: ")
enable_password = getpass("Введите enable пароль (если требуется, иначе Enter): ")
# определение устройств

current_date = datetime.datetime.now().strftime("%Y-%m-%d")
# текущая дата для имени файла

# Название папки для бэкапов
BACKUP_DIR = "config_backups"


# Функция для определения команды на бэкап в зависимости от ОС
def get_backup_command(device_type):
    if "juniper" in device_type:
        return "show configuration | display set"
    elif "cisco_ios" in device_type or "arista" in device_type:
        return "show running-config"
    else:
        return "show running-config"


def backup_config(device_info):

    # Добавляем глобально введенные учетные данные в словарь устройства
    device_info["username"] = username
    device_info["password"] = password

    # Добавляем enable пароль, если он был введен
    if enable_password:
        device_info["secret"] = enable_password

    # Также добавим общие настройки, например, задержку
    if not device_info.get("global_delay_factor"):
        device_info["global_delay_factor"] = 2

    # Убеждаемся, что conn_timeout установлен для ConnectHandler
    device_info.setdefault("conn_timeout", 60)

    try:
        print(f"Подключение к устройству {device_info['host']}...")

        net_connect = ConnectHandler(**device_info)

        # Переход в enable mode, если поддерживается и указан secret
        if device_info.get("secret"):
            net_connect.enable()

        # Получаем имя хоста и обрезаем символы приглашения (например, # или >)
        hostname = net_connect.find_prompt().strip("#").strip(">").strip()

        print(f"Подключено к хосту: {hostname}")

        command = get_backup_command(device_info["device_type"])

        # *** КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ДЛЯ ELTEX ***
        # Явно указываем ожидаемую строку (регулярное выражение) для send_command
        # Используем таймаут чтения (read_timeout) внутри send_command, где он поддерживается
        prompt_pattern = rf"{hostname}[#>]\s*$"

        config_output = net_connect.send_command(
            command,
            expect_string=re.compile(prompt_pattern),
            read_timeout=120,  # Таймаут на чтение вывода команды (поддерживается здесь)
        )

        # сохранение конфигурации в файл
        filename = f"{hostname}_backup_{current_date}.txt"
        filepath = os.path.join(BACKUP_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as file:
            file.write(config_output)

        print(f"Конфигурация успешно сохранена в файл: {filepath}")

        net_connect.disconnect()

    except Exception as e:
        print(
            f"Ошибка подключения или получения конфигурации с устройства {device_info['host']}: {e}"
        )


# --- Основной блок выполнения ---
if __name__ == "__main__":
    # Проверяем и создаем папку для бэкапов, если она не существует
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"Создана папка: {BACKUP_DIR}")

    # Запуск процесса для всех устройств в списке, импортированном из devices_ips
    for device in devices_list:
        backup_config(device)

print("Процесс снятия конфигураций завершен.")
