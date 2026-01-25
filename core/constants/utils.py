"""
Утилиты: slug, транслитерация, маски подсетей, дефолты.
"""

from typing import Dict, List

# =============================================================================
# ДЕФОЛТНЫЕ ЗНАЧЕНИЯ
# =============================================================================

# Дефолтная папка для отчётов
DEFAULT_OUTPUT_FOLDER: str = "reports"

# Дефолтная папка для бэкапов
DEFAULT_BACKUP_FOLDER: str = "backups"

# Дефолтная длина маски подсети (если не указана)
DEFAULT_PREFIX_LENGTH: int = 24

# Максимальная ширина колонки в Excel
MAX_EXCEL_COLUMN_WIDTH: int = 50


# =============================================================================
# СТАТУСЫ
# =============================================================================

# Статусы портов, означающие "online"
ONLINE_PORT_STATUSES: List[str] = ["connected", "connect", "up"]

# Статусы портов, означающие "offline"
OFFLINE_PORT_STATUSES: List[str] = ["notconnect", "notconnected", "down", "disabled"]


# =============================================================================
# SLUG GENERATION
# =============================================================================


def slugify(name: str) -> str:
    """
    Генерирует slug для NetBox из имени.

    Преобразует:
    - Пробелы в дефисы
    - Подчёркивания в дефисы
    - Слэши в дефисы
    - Всё в нижний регистр

    Args:
        name: Исходное имя

    Returns:
        str: Slug для NetBox

    Examples:
        >>> slugify("Main Office")
        'main-office'
        >>> slugify("C9200L-24P/4X")
        'c9200l-24p-4x'
    """
    if not name:
        return ""
    return name.lower().replace(" ", "-").replace("_", "-").replace("/", "-")


# Таблица транслитерации кириллицы в латиницу
_TRANSLIT_TABLE: Dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def transliterate_to_slug(name: str) -> str:
    """
    Транслитерирует кириллицу в латиницу и создаёт валидный slug.

    Args:
        name: Имя (может содержать кириллицу)

    Returns:
        str: Валидный slug (только латиница, цифры, дефисы, подчёркивания)

    Examples:
        >>> transliterate_to_slug("Москва")
        'moskva'
        >>> transliterate_to_slug("Офис №1")
        'ofis-1'
    """
    result = []
    for char in name.lower():
        if char in _TRANSLIT_TABLE:
            result.append(_TRANSLIT_TABLE[char])
        elif char.isalnum() or char in "-_":
            result.append(char)
        elif char == " ":
            result.append("-")
        # Другие символы пропускаем
    return "".join(result)


# =============================================================================
# NETWORK UTILITIES
# =============================================================================


def mask_to_prefix(mask: str) -> int:
    """
    Конвертирует маску сети в длину префикса.

    Args:
        mask: Маска в формате 255.255.255.0 или уже числовой префикс

    Returns:
        int: Длина префикса (например, 24)

    Examples:
        >>> mask_to_prefix("255.255.255.0")
        24
        >>> mask_to_prefix("255.255.0.0")
        16
        >>> mask_to_prefix("24")
        24
    """
    if not mask:
        return 24
    # Если уже число (строка или int)
    if str(mask).isdigit():
        return int(mask)
    try:
        octets = [int(x) for x in mask.split(".")]
        binary = "".join(format(x, "08b") for x in octets)
        return binary.count("1")
    except Exception:
        return 24
