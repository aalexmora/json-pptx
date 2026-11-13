"""Генерация синтетического шаблона разработки (ТЗ v4 §12).

Создаёт `.pptx`-шаблон с колонкой-прототипом, аннотациями и именованными
разделителями. Builder клонирует колонку под данные и переставляет разделители
для адаптивной сетки 1/2/3/4 колонки.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.util import Inches, Pt

from roadmap_generator.template_registry import get_layout_shape_names

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
    bullets.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
    bullets.text_frame.margin_left = bullets.text_frame.margin_right = 0
    bullets.text_frame.margin_top = bullets.text_frame.margin_bottom = 0

    inheritance = slide.shapes.add_textbox(Inches(margin), Inches(5.4), Inches(12.333), Inches(1.3))
    inheritance.name = "tier_inheritance_note"
    inheritance.text_frame.text = "inc. all features of previous tier(s):\n• Stream / Tier"
    inheritance.text_frame.paragraphs[0].runs[0].font.size = Pt(10)
    inheritance.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor(0x1D, 0x4E, 0xD8)

    footnote = slide.shapes.add_textbox(Inches(margin), Inches(7.0), Inches(8.5), Inches(0.25))
    footnote.name = "subject_to_change_footnote"
    footnote.text_frame.text = "* Subject to Change"
    footnote.text_frame.paragraphs[0].runs[0].font.size = Pt(10)

    number = slide.shapes.add_textbox(Inches(12.1), Inches(7.0), Inches(0.7), Inches(0.25))
    number.name = "slide_number"
    number.text_frame.text = "1"
    number.text_frame.paragraphs[0].runs[0].font.size = Pt(10)

    for index, name in enumerate(get_layout_shape_names("separators"), start=1):
        x = margin + index * ((13.333 - 2 * margin) / 4)
        separator = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(x),
            Inches(1.1),
            Inches(x),
            Inches(6.8),
        )
        separator.name = name

    prs.save(str(path))


def ensure_synthetic_template(path=None) -> Path:
    """Генерирует синтетический шаблон, если его ещё нет. Возвращает путь."""
    path = Path(path) if path else SYNTHETIC_TEMPLATE_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        make_synthetic_template(path)
    return path
