"""
Нормализация моделей устройств.

Убирает лишние префиксы и лицензионные суффиксы для NetBox.
"""

# =============================================================================
# НОРМАЛИЗАЦИЯ МОДЕЛЕЙ УСТРОЙСТВ
# =============================================================================
# Примеры:
#   WS-C2960C-8TC-L → C2960C-8TC
#   WS-C3850-24P-S → C3850-24P
#   C9300-48P-E → C9300-48P
# =============================================================================

# Лицензионные суффиксы Cisco (убираются)
CISCO_LICENSE_SUFFIXES: tuple = (
    "-L",  # LAN Base
    "-S",  # IP Base / Standard
    "-E",  # IP Services / Enterprise
    "-A",  # Advanced
    "-K9",  # Crypto
)

# Префиксы для удаления
MODEL_PREFIXES_TO_REMOVE: tuple = ("WS-",)  # Cisco legacy


def normalize_device_model(model: str) -> str:
    """
    Нормализует модель устройства для NetBox.

    Убирает:
    - WS- префикс
    - Лицензионные суффиксы (-L, -S, -E, -A, -K9)

    Оставляет:
    - Порты (-8TC, -24P, -48T и т.д.)

    Args:
        model: Сырая модель из show version (например "WS-C2960C-8TC-L")

    Returns:
        str: Нормализованная модель (например "C2960C-8TC")

    Examples:
        >>> normalize_device_model("WS-C2960C-8TC-L")
        'C2960C-8TC'
        >>> normalize_device_model("WS-C3850-24P-S")
        'C3850-24P'
        >>> normalize_device_model("C9300-48P-E")
        'C9300-48P'
        >>> normalize_device_model("N9K-C93180YC-EX")
        'N9K-C93180YC-EX'
    """
    if not model:
        return model

    result = model.strip().upper()

    # Убираем префиксы
    for prefix in MODEL_PREFIXES_TO_REMOVE:
        if result.startswith(prefix):
            result = result[len(prefix) :]
            break

    # Убираем лицензионные суффиксы (только в конце)
    for suffix in CISCO_LICENSE_SUFFIXES:
        if result.endswith(suffix):
            result = result[: -len(suffix)]
            break

    return result
