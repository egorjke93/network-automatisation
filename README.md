# Network Collector

Утилита для сбора данных с сетевых устройств и синхронизации с NetBox.

## Возможности

- Сбор MAC-адресов, LLDP/CDP соседей, интерфейсов, inventory
- Экспорт в Excel, CSV, JSON
- Синхронизация с NetBox (устройства, интерфейсы, IP, кабели, VLAN)
- Поддержка Cisco IOS/IOS-XE/NX-OS, Arista EOS, Juniper JunOS, QTech

## Быстрый старт

```bash
# Установка
cd /home/sa/project
source network_collector/myenv/bin/activate
pip install -r network_collector/requirements.txt

# Настройка учётных данных
export NET_USERNAME="admin"
export NET_PASSWORD="password"

# Сбор данных
python -m network_collector devices --format excel
python -m network_collector mac --format excel
python -m network_collector lldp --protocol both --format csv

# Синхронизация с NetBox
export NETBOX_URL="https://netbox.example.com"
export NETBOX_TOKEN="your-token"
python -m network_collector sync-netbox --sync-all --site "Office" --role "switch" --dry-run
```

## Документация

- **[Полное руководство](docs/MANUAL.md)** — все команды, опции, конфигурация
- **[Архитектура](docs/ARCHITECTURE.md)** — техническое устройство
- **[Разработка](docs/DEVELOPMENT.md)** — тестирование, добавление платформ

## Основные команды

| Команда | Описание |
|---------|----------|
| `devices` | Инвентаризация устройств |
| `mac` | Сбор MAC-адресов |
| `lldp` | Сбор LLDP/CDP соседей |
| `interfaces` | Сбор интерфейсов |
| `backup` | Резервное копирование конфигураций |
| `sync-netbox` | Синхронизация с NetBox |
| `match-mac` | Сопоставление MAC с хостами |
| `push-descriptions` | Применение описаний портов |

## Лицензия

MIT
