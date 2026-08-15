"""Синонимы (кастомные заголовки) групп AppTitle.

Глобальная map `{original_AppTitle: custom_label}`. Применяется по точному
регистрозависимому совпадению; действует только при включённой `apptitle_grouping`.
"""
from __future__ import annotations

from typing import Dict

_labels: Dict[str, str] = {}


def get_apptitle_label(original: str) -> str:
    """Возвращает кастомное имя, если задано, иначе `original` без изменений."""
    return _labels.get(original, original)


def save_apptitle_label(original: str, custom_label: str) -> None:
    """Задаёт кастомный заголовок; пустое значение — удаляет синоним."""
    if custom_label is None or str(custom_label).strip() == "":
        _labels.pop(original, None)
    else:
        _labels[original] = str(custom_label)


def _reset_state() -> None:
    """Сброс in-memory хранилища (для тестов)."""
    _labels.clear()
