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
_product_inheritance_flags: Dict[str, bool] = {}
_product_slide_hidden_flags: Dict[str, bool] = {}


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


def get_product_inheritance_flag(product_name: str) -> bool:
    """Флаг наследования для всех Stream и Tier выбранного Product."""
    return _product_inheritance_flags.get(product_name, False)


def save_product_inheritance_flag(product_name: str, flag: bool) -> None:
    _product_inheritance_flags[product_name] = bool(flag)


def get_product_slide_hidden_flag(product_name: str) -> bool:
    """Нужно ли пропустить автоматический Product-разделитель."""
    return _product_slide_hidden_flags.get(product_name, False)


def save_product_slide_hidden_flag(product_name: str, flag: bool) -> None:
    """Сохраняет флаг скрытия Product-разделителя."""
    _product_slide_hidden_flags[product_name] = bool(flag)


def export_state() -> dict:
    return {
        "order": dict(_order_store),
        "apptitle_priority": list(_apptitle_priority),
        "product_inheritance_flags": dict(_product_inheritance_flags),
        "product_slide_hidden_flags": dict(_product_slide_hidden_flags),
    }


def import_state(state: dict) -> None:
    _order_store.clear()
    _order_store.update(state.get("order", {}))
    _apptitle_priority[:] = list(state.get("apptitle_priority", []))
    _product_inheritance_flags.clear()
    _product_slide_hidden_flags.clear()
    _product_slide_hidden_flags.update(state.get("product_slide_hidden_flags", {}))
    product_flags = state.get("product_inheritance_flags")
    if product_flags is not None:
        _product_inheritance_flags.update(product_flags)
        return

    # Совместимость с профилями до v1.3.0: если наследование было включено хотя
    # бы у одного Tier, включаем новое правило на уровне всего Product.
    for tier_path, enabled in state.get("tier_inheritance_flags", {}).items():
        if enabled:
            product_name = tier_path.split(SEPARATOR, 1)[0]
            _product_inheritance_flags[product_name] = True


def _reset_state() -> None:
    """Сброс in-memory хранилища (для тестов)."""
    _order_store.clear()
    _apptitle_priority.clear()
    _product_inheritance_flags.clear()
    _product_slide_hidden_flags.clear()
