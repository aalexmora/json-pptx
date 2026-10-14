"""Синонимы (кастомные заголовки) групп AppTitle.

Глобальная map `{original_AppTitle: custom_label}`. Применяется по точному
регистрозависимому совпадению; действует только при включённой `apptitle_grouping`.
"""
from __future__ import annotations

from typing import Dict

_labels: Dict[str, str] = {}


def get_apptitle_label(original: str) -> str:
    """Возвращает кастомное имя, если задано, иначе `original` без изменений."""
    custom_label = _labels.get(original)
    if custom_label is None or str(custom_label).strip() == "":
        return original
    return str(custom_label)


def save_apptitle_label(original: str, custom_label: str) -> None:
    """Задаёт кастомный заголовок; пустое значение сохраняет пустой override."""
    _labels[original] = "" if custom_label is None else str(custom_label)


def export_state() -> dict:
    return dict(_labels)


def import_state(state: dict) -> None:
    _labels.clear()
    _labels.update(state)


def _reset_state() -> None:
    """Сброс in-memory хранилища (для тестов)."""
    _labels.clear()
