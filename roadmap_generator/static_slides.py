"""Статичные слайды пользователя (ТЗ v4 §7.3).

Свободные текстовые слайды с точкой вставки: `end`, `before:<Product>`, `after:<Product>`.
Хранятся в глобальном профиле (project-scope — переедет в проектный файл).
"""
from __future__ import annotations

from typing import Dict, List

_static_slides: List[Dict[str, str]] = []


def get_static_slides() -> List[Dict[str, str]]:
    return [dict(s) for s in _static_slides]


def save_static_slides(slides) -> None:
    _static_slides.clear()
    for s in slides:
        _static_slides.append({
            "title": s.get("title", ""),
            "text": s.get("text", ""),
            "position": s.get("position", "end"),
        })


def export_state() -> List[Dict[str, str]]:
    return [dict(s) for s in _static_slides]


def import_state(state) -> None:
    save_static_slides(state)


def _reset_state() -> None:
    _static_slides.clear()
