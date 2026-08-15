"""Порядок узлов дерева слайдов и глобальный приоритет AppTitle.

Хранилище — глобальный профиль (in-memory; на этапах 5/8 переносится в SQLite).
Ключ `parent_path` — путь родителя через `SEPARATOR`, например
`"Kaspersky Next > Kaspersky Next Optimum"`. Корень (список продуктов) — `""`.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

SEPARATOR = " > "

_order_store: Dict[str, List[str]] = {}
_apptitle_priority: List[str] = []


def get_effective_order(parent_path: str, item_names: List[str]) -> List[str]:
    """Возвращает `item_names` в эффективном порядке.

    Сохранённый порядок сохраняет позиции известных узлов; новые (не
    встречавшиеся) имена — в конец, в порядке их появления в `item_names`.
    """
    saved = _order_store.get(parent_path)
    result: List[str] = []
    if saved:
        present = set(item_names)
        for name in saved:
            if name in present and name not in result:
                result.append(name)
    for name in item_names:
        if name not in result:
            result.append(name)
    return result


def save_order(parent_path: str, ordered_names: List[str]) -> None:
    """Сохраняет порядок детей для `parent_path` (после drag & drop в UI)."""
    _order_store[parent_path] = list(ordered_names)


def get_apptitle_priority() -> List[str]:
    """Глобальный приоритетный список AppTitle (единый для всей презентации)."""
    return list(_apptitle_priority)


def save_apptitle_priority(ordered_names: List[str]) -> None:
    _apptitle_priority[:] = list(ordered_names)


def resolve_apptitle_order(app_titles_with_counts: List[Tuple[str, int]]) -> List[str]:
    """Приоритетные AppTitle — первыми (в заданном порядке), остальные — по убыванию count."""
    priority = get_apptitle_priority()
    counts = dict(app_titles_with_counts)
    result = [a for a in priority if a in counts]
    rest = [a for a, _ in sorted(app_titles_with_counts, key=lambda x: -x[1]) if a not in priority]
    return result + rest


def _reset_state() -> None:
    """Сброс in-memory хранилища (для тестов)."""
    _order_store.clear()
    _apptitle_priority.clear()
