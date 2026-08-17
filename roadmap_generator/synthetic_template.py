"""Генерация синтетического шаблона разработки (ТЗ v4 §12).

Создаёт `.pptx` «мастер-шаблон»: один слайд с 4 колонками и именованными шейпами
по конвенции (`col_{n}_header`, `col_{n}_bullets`, `col_{n}_group_{m}_header`).
Builder клонирует этот слайд и заполняет шейпы под конкретный roadmap-слайд
(заполненные колонки — данными, неиспользованные — очищаются).
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from roadmap_generator.template_registry import load_contracts

SYNTHETIC_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "synthetic_template.pptx"
)


def make_synthetic_template(path) -> None:
    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    margin = 0.5
    col_w = 2.9  # ширина одной колонки-прототипа (builder клонирует её под кварталы)

    eyebrow = slide.shapes.add_textbox(Inches(margin), Inches(0.15), Inches(12.333), Inches(0.3))
    eyebrow.name = "eyebrow"
    eyebrow.text_frame.text = "Roadmap"

    title = slide.shapes.add_textbox(Inches(margin), Inches(0.45), Inches(12.333), Inches(0.5))
    title.name = "slide_title"
    title.text_frame.text = "Tier name"

    header = slide.shapes.add_textbox(Inches(margin), Inches(1.1), Inches(col_w), Inches(0.4))
    header.name = "col_header"
    header.text_frame.text = "Q1 2025"

    bullets = slide.shapes.add_textbox(Inches(margin), Inches(1.6), Inches(col_w), Inches(5.2))
    bullets.name = "col_bullets"
    bullets.text_frame.text = "• feature"
    bullets.text_frame.word_wrap = True

    prs.save(str(path))


def ensure_synthetic_template(path=None) -> Path:
    """Генерирует синтетический шаблон, если его ещё нет. Возвращает путь."""
    path = Path(path) if path else SYNTHETIC_TEMPLATE_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        make_synthetic_template(path)
    return path
