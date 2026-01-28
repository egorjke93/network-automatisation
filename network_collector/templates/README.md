# Кастомные TextFSM шаблоны

Папка для шаблонов нестандартных платформ (QTech, Eltex и др.),
вывод которых отличается от Cisco.

## Как добавить новый шаблон

### 1. Добавь маппинг в `core/constants.py`:

```python
CUSTOM_TEXTFSM_TEMPLATES = {
    ("qtech", "show mac address-table"): "qtech_show_mac.textfsm",
}
```

### 2. Создай шаблон в этой папке:

```bash
# templates/qtech_show_mac.textfsm
```

### 3. Готово!

Парсер автоматически найдёт и использует кастомный шаблон.

---

## Формат TextFSM шаблона

```
Value VLAN (\d+)
Value MAC ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})
Value TYPE (\w+)
Value INTERFACE (\S+)

Start
  ^${VLAN}\s+${MAC}\s+${TYPE}\s+${INTERFACE} -> Record
```

### Объяснение:
- `Value` — определение переменной с regex паттерном
- `Start` — начальное состояние
- `^...` — паттерн для строки
- `-> Record` — сохранить запись и продолжить

---

## Примеры шаблонов

### show mac address-table (QTech)

Если вывод QTech выглядит так:
```
Vlan    Mac Address       Type        Ports
----    -----------       ----        -----
1       0011.2233.4455    dynamic     Gi0/1
1       aabb.ccdd.eeff    static      Gi0/2
```

Шаблон:
```
Value VLAN (\d+)
Value MAC ([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})
Value TYPE (\w+)
Value INTERFACE (\S+)

Start
  ^${VLAN}\s+${MAC}\s+${TYPE}\s+${INTERFACE}\s*$$ -> Record
```

### show version (QTech)

Если вывод отличается от Cisco:
```
Value HOSTNAME (\S+)
Value VERSION (\S+)
Value SERIAL (\S+)
Value HARDWARE (\S+)

Start
  ^Hostname:\s+${HOSTNAME}
  ^Software Version:\s+${VERSION}
  ^Serial Number:\s+${SERIAL}
  ^Hardware Model:\s+${HARDWARE}
```

---

## Тестирование шаблона

```python
import textfsm

# Сырой вывод устройства
output = """
Vlan    Mac Address       Type        Ports
1       0011.2233.4455    dynamic     Gi0/1
"""

# Тестируем шаблон
with open("templates/qtech_show_mac.textfsm") as f:
    fsm = textfsm.TextFSM(f)
    result = fsm.ParseText(output)

    # Выводим результат
    print(fsm.header)  # ['VLAN', 'MAC', 'TYPE', 'INTERFACE']
    print(result)      # [['1', '0011.2233.4455', 'dynamic', 'Gi0/1']]
```

---

## Ресурсы

- [TextFSM Wiki](https://github.com/google/textfsm/wiki)
- [NTC Templates](https://github.com/networktocode/ntc-templates)
- [TextFSM Tutorial](https://pyneng.readthedocs.io/en/latest/book/21_textfsm/)
