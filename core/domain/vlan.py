"""
Domain logic для VLAN.

Парсинг диапазонов, сравнение, валидация.
Не зависит от NetBox или других внешних систем.
"""

import logging
from typing import List, Set, Optional

logger = logging.getLogger(__name__)


# Полные диапазоны VLAN (все VLAN)
FULL_VLAN_RANGES = frozenset({"all", "1-4094", "1-4093", "1-4095", "none", ""})


def parse_vlan_range(vlan_str: str) -> List[int]:
    """
    Парсит строку с диапазонами VLAN в список VID.

    Args:
        vlan_str: Строка типа "10,20,30-50,100" или "1-4094"

    Returns:
        List[int]: Список VID, например [10, 20, 30, 31, ..., 50, 100]
                   Пустой список если строка пустая или "all"

    Examples:
        >>> parse_vlan_range("10,20,30")
        [10, 20, 30]
        >>> parse_vlan_range("10-15")
        [10, 11, 12, 13, 14, 15]
        >>> parse_vlan_range("all")
        []
    """
    if not vlan_str:
        return []

    vlan_str = vlan_str.strip().lower()

    # Пропускаем "all" и полные диапазоны (tagged-all)
    if vlan_str in FULL_VLAN_RANGES:
        return []

    result = []
    try:
        # Разбиваем по запятым: "10,20,30-50" → ["10", "20", "30-50"]
        for part in vlan_str.split(","):
            part = part.strip()
            if not part:
                continue

            if "-" in part:
                # Диапазон: "30-50" → [30, 31, ..., 50]
                start_end = part.split("-", 1)
                if len(start_end) == 2:
                    start = int(start_end[0].strip())
                    end = int(start_end[1].strip())
                    result.extend(range(start, end + 1))
            else:
                # Одиночный VLAN: "10" → [10]
                result.append(int(part))
    except ValueError as e:
        logger.debug(f"Ошибка парсинга VLAN: {vlan_str} - {e}")
        return []

    # Убираем дубликаты и сортируем
    return sorted(set(result))


def is_full_vlan_range(vlan_str: str) -> bool:
    """
    Проверяет является ли строка полным диапазоном VLAN (все VLAN).

    Args:
        vlan_str: Строка VLAN

    Returns:
        bool: True если это "all", "1-4094" и т.д.

    Examples:
        >>> is_full_vlan_range("all")
        True
        >>> is_full_vlan_range("1-4094")
        True
        >>> is_full_vlan_range("10,20,30")
        False
    """
    if not vlan_str:
        return True
    return vlan_str.strip().lower() in FULL_VLAN_RANGES


class VlanSet:
    """
    Множество VLAN для сравнения и операций.

    Инкапсулирует логику работы с набором VLAN:
    - Парсинг из строки
    - Сравнение с другим набором
    - Вычисление разницы

    Examples:
        >>> local = VlanSet.from_string("10,20,30")
        >>> remote = VlanSet.from_ids([10, 20])
        >>> local == remote
        False
        >>> local.added(remote)
        {30}
    """

    def __init__(self, vids: Set[int]):
        """
        Args:
            vids: Множество VID
        """
        self._vids = frozenset(vids)

    @classmethod
    def from_string(cls, vlan_str: str) -> "VlanSet":
        """Создаёт из строки типа '10,20,30-50'."""
        return cls(set(parse_vlan_range(vlan_str)))

    @classmethod
    def from_ids(cls, ids: List[int]) -> "VlanSet":
        """Создаёт из списка ID."""
        return cls(set(ids))

    @classmethod
    def from_vlan_objects(cls, vlans) -> "VlanSet":
        """Создаёт из списка VLAN объектов NetBox (имеющих .vid)."""
        if not vlans:
            return cls(set())
        return cls({v.vid for v in vlans})

    @property
    def vids(self) -> Set[int]:
        """Возвращает множество VID."""
        return set(self._vids)

    @property
    def sorted_list(self) -> List[int]:
        """Возвращает отсортированный список VID."""
        return sorted(self._vids)

    def __eq__(self, other) -> bool:
        if isinstance(other, VlanSet):
            return self._vids == other._vids
        return False

    def __len__(self) -> int:
        return len(self._vids)

    def __bool__(self) -> bool:
        return len(self._vids) > 0

    def __repr__(self) -> str:
        return f"VlanSet({self.sorted_list})"

    def added(self, other: "VlanSet") -> Set[int]:
        """VLAN которые есть в self, но нет в other (добавленные)."""
        return self._vids - other._vids

    def removed(self, other: "VlanSet") -> Set[int]:
        """VLAN которые есть в other, но нет в self (удалённые)."""
        return other._vids - self._vids

    def intersection(self, other: "VlanSet") -> Set[int]:
        """Общие VLAN."""
        return self._vids & other._vids
