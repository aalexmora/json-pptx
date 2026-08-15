"""Рендер `SlidePlan` в `.pptx`.

Наследует размер слайда из шаблона (ТЗ v4 §10). До появления финального
размеченного дизайн-шаблона слайды отрисовываются программно из `SlidePlan`
(публичный API python-pptx, без клонирования слайдов/приватных полей). Заполнение
именованных шейпов шаблона подключается при разметке реального шаблона (ТЗ v4 §12).
"""
from __future__ import annotations

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from roadmap_generator.layout import fit_bullets_dynamic
from roadmap_generator.plugins_engine import DividerSlide, RoadmapSlide, SlidePlan
from roadmap_generator.template_registry import select_template

MARGIN = 0.5
GAP = 0.25
BASE_FONT_PT = 14
EYEBROW_FONT_PT = 12
TITLE_FONT_PT = 20
HEADER_FONT_PT = 14


def build_presentation(plan: SlidePlan) -> Presentation:
    """Рендерит план слайдов в объект `Presentation` (ещё не сохранённый)."""
    template = Presentation(select_template("roadmap", 4, False))
    prs = Presentation()
    # размер слайда наследуется из шаблона (ТЗ v4 §10)
    prs.slide_width = template.slide_width
    prs.slide_height = template.slide_height

    blank = prs.slide_layouts[6]
    w = prs.slide_width.inches
    h = prs.slide_height.inches

    for item in plan.slides:
        if isinstance(item, DividerSlide):
            _render_divider(prs, blank, item, w, h)
        elif isinstance(item, RoadmapSlide):
            _render_roadmap(prs, blank, item, w, h)
    return prs


def _render_divider(prs, layout, slide: DividerSlide, w: float, h: float) -> None:
    s = prs.slides.add_slide(layout)
    label = "PRODUCT" if slide.divider_type == "product" else "STREAM"

    title = s.shapes.add_textbox(Inches(MARGIN), Inches(h / 2 - 0.7), Inches(w - 2 * MARGIN), Inches(1.2))
    _set_paragraph(title, slide.title, 40, bold=True, align=PP_ALIGN.CENTER)

    sub = s.shapes.add_textbox(Inches(MARGIN), Inches(h / 2 + 0.6), Inches(w - 2 * MARGIN), Inches(0.4))
    _set_paragraph(sub, label, 14, bold=False, align=PP_ALIGN.CENTER)


def _render_roadmap(prs, layout, slide: RoadmapSlide, w: float, h: float) -> None:
    s = prs.slides.add_slide(layout)

    eyebrow = "Roadmap (cont.)" if slide.continuation else "Roadmap"
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.15), Inches(w - 2 * MARGIN), Inches(0.3)),
        eyebrow, EYEBROW_FONT_PT, bold=False,
    )
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.42), Inches(w - 2 * MARGIN), Inches(0.45)),
        slide.tier, TITLE_FONT_PT, bold=True,
    )

    top = 1.0
    if slide.inheritance_note:
        _set_paragraph(
            s.shapes.add_textbox(Inches(MARGIN), Inches(0.88), Inches(w - 2 * MARGIN), Inches(0.3)),
            slide.inheritance_note, 12, bold=False,
        )
        top = 1.25

    n = len(slide.columns)
    col_w = (w - 2 * MARGIN - (n - 1) * GAP) / n
    body_h = h - top - MARGIN
    x = MARGIN

    overflow: list = []
    for col in slide.columns:
        _set_paragraph(
            s.shapes.add_textbox(Inches(x), Inches(top), Inches(col_w), Inches(0.35)),
            col.quarter, HEADER_FONT_PT, bold=True,
        )
        body_top = top + 0.42
        box = s.shapes.add_textbox(Inches(x), Inches(body_top), Inches(col_w), Inches(body_h - 0.42))
        overflow.extend(_fill_column_body(box, col, body_h - 0.42, col_w))
        x += col_w + GAP

    if slide.footnote:
        _set_paragraph(
            s.shapes.add_textbox(Inches(MARGIN), Inches(h - 0.45), Inches(w - 2 * MARGIN), Inches(0.35)),
            slide.footnote, 10, bold=False,
        )

    if overflow:
        _render_overflow(prs, layout, slide, overflow, w, h)


def _fill_column_body(box, col, body_h_in: float, col_w_in: float) -> list:
    bullets = _column_bullets(col)
    texts = [b.text for b in bullets]
    font_pt, fitting, overflow = fit_bullets_dynamic(texts, body_h_in, col_w_in, BASE_FONT_PT)
    fit_count = len(fitting)

    tf = box.text_frame
    tf.word_wrap = True
    written = 0

    def add(text: str, bold: bool) -> None:
        nonlocal written
        p = tf.paragraphs[0] if written == 0 else tf.add_paragraph()
        _style_paragraph(p, text, font_pt, bold=bold)
        written += 1

    remaining = fit_count
    if col.grouped:
        for group in col.groups:
            if remaining <= 0:
                break
            take = min(len(group.bullets), remaining)
            if take == 0:
                continue
            add(group.app_title, True)
            for bullet in group.bullets[:take]:
                add(_bullet_text(bullet), False)
            remaining -= take
    else:
        for bullet in bullets[:fit_count]:
            add(_bullet_text(bullet), False)

    return overflow


def _bullet_text(bullet) -> str:
    text = f"• {bullet.text}"
    if bullet.is_subject_to_change:
        text += " *"
    return text


def _render_overflow(prs, layout, slide: RoadmapSlide, overflow: list, w: float, h: float) -> None:
    s = prs.slides.add_slide(layout)
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.15), Inches(w - 2 * MARGIN), Inches(0.3)),
        "Roadmap (cont. — overflow)", EYEBROW_FONT_PT, bold=False,
    )
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.42), Inches(w - 2 * MARGIN), Inches(0.45)),
        slide.tier, TITLE_FONT_PT, bold=True,
    )
    box = s.shapes.add_textbox(Inches(MARGIN), Inches(1.0), Inches(w - 2 * MARGIN), Inches(h - 1.5))
    tf = box.text_frame
    tf.word_wrap = True
    for i, text in enumerate(overflow):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        _style_paragraph(p, f"• {text}", BASE_FONT_PT, bold=False)


def _column_bullets(col):
    if col.grouped:
        out = []
        for group in col.groups:
            out.extend(group.bullets)
        return out
    return col.bullets


def _set_paragraph(box, text: str, size: int, bold: bool, align=None) -> None:
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    p = tf.paragraphs[0]
    if align is not None:
        p.alignment = align
    _style_paragraph(p, text, size, bold)


def _style_paragraph(p, text: str, size: int, bold: bool) -> None:
    p.text = text
    for run in p.runs:
        run.font.size = Pt(size)
        run.font.bold = bold
