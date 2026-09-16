"""Статичные слайды пользователя (ТЗ v4 §7.3).

Слайд = загруженная `.pptx`-заготовка (копируется 1:1) с названием для карточек,
точкой вставки `end` / `before:<Product>` / `after:<Product>` и необязательным
prompt для будущей AI-генерации/актуализации. Хранятся в профиле.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pptx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_SLIDES_DIR = PROJECT_ROOT / "templates_library" / "static_slides"

_static_slides: List[Dict[str, str]] = []


def get_static_slides(language: str | None = None) -> List[Dict[str, str]]:
    slides = [dict(s) for s in _static_slides]
    if language is None:
        return slides
    return [slide for slide in slides if slide["language"] == language]


def save_static_slides(slides) -> None:
    _static_slides.clear()
    for s in slides:
        _static_slides.append({
            "name": s.get("name", "") or s.get("title", ""),
            "position": s.get("position", "end"),
            "pptx": s.get("pptx", ""),
            "prompt": s.get("prompt", ""),
            # Legacy-профили создавались до языкового разделения и фактически
            # использовались прежде всего для RU-колоды.
            "language": s.get("language") if s.get("language") in {"ru", "en"} else "ru",
        })


def save_static_slide_pptx(filename: str, data: bytes) -> str:
    """Сохраняет загруженную `.pptx`-заготовку. Возвращает имя файла."""
    STATIC_SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    path = STATIC_SLIDES_DIR / filename
    path.write_bytes(data)
    return filename


def static_slide_pptx_path(filename: str) -> Path:
    return STATIC_SLIDES_DIR / filename


def extract_slide_title(filename: str) -> str:
    """Возвращает первый непустой текст первого слайда (для автоназвания)."""
    path = static_slide_pptx_path(filename)
    if not path.exists():
        return ""
    try:
        prs = pptx.Presentation(str(path))
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame and shape.text_frame.text.strip():
                    return shape.text_frame.text.strip().split("\n")[0][:80]
            break
    except Exception:
        return ""
    return ""


def export_state() -> List[Dict[str, str]]:
    return [dict(s) for s in _static_slides]


def import_state(state) -> None:
    save_static_slides(state)


def _reset_state() -> None:
    _static_slides.clear()
