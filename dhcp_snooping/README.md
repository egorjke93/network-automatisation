# Cisco DHCP Snooping Automation

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Netmiko](https://img.shields.io/badge/netmiko-4.5-green)

Скрипт для автоматической настройки DHCP Snooping на устройствах Cisco.

## 📖 Описание
- Автоматическое определение trunk/access портов
- Конфигурация DHCP Snooping trust на trunk-портах
- Установка лимита DHCP-запросов на access-портах
- Глобальная настройка DHCP Snooping
- Логирование всех изменений

## ⚙️ Требования
- Python 3.8+
- Поддерживаемые устройства: Cisco IOS/IOS-XE
- Доступ по SSH с правами enable

## 🚀 Установка
1. Клонировать репозиторий:
```bash
git clone https://github.com/egorjke93/cisco-dhcp-snooping.git
cd cisco-dhcp-snoopings