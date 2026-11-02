"""Геометрия и расчёт помещаемости bullet-списка внутри textbox'а.

`fit_bullets_dynamic` — эвристика (ТЗ v4 §4.2 п.8): оценивает число строк
каждого bullet'а по ширине textbox'а и высоте строки (~1.2 × кегль), понижает
кегль до `MIN_FONT_PT`, а при нехватке места переносит излишек на слайд-продолжение
(не обрезает). Точная сверка с рендером PowerPoint — визуальный QA.
"""
from __future__ import annotations

import math
from typing import List, Tuple

MIN_FONT_PT = 8
LINE_HEIGHT_FACTOR = 1.2
CHAR_WIDTH_FACTOR = 0.5  # средняя ширина символа ≈ 0.5 em (латиница)


def estimate_text_lines(text: str, slot_width_in: float, font_pt: int) -> int:
    """Число строк, которое займёт текст при переносе по ширине слота (TOR v2 §3).

    `chars_per_line = floor(slot_width_pt / (CHAR_WIDTH_FACTOR * font_pt))`,
    `line_count = ceil(len(text) / chars_per_line)` — минимум 1 строка.
    """
    width_pt = slot_width_in * 72.0
    chars_per_line = max(1, int(width_pt / (CHAR_WIDTH_FACTOR * font_pt)))
    return max(1, math.ceil(len(text) / chars_per_line))


def estimate_bullet_height_pt(text: str, slot_width_in: float, font_pt: int) -> float:
    """Высота ячейки одной фичи в пунктах: строки × высота строки."""
    return estimate_text_lines(text, slot_width_in, font_pt) * font_pt * LINE_HEIGHT_FACTOR


def estimate_group_height_pt(
    bullet_texts: List[str],
    slot_width_in: float,
    font_pt: int,
    *,
    extra_headers: int = 0,
) -> float:
    """Высота группы AppTitle: строка-заголовок + сумма высот фич."""
    header_pt = font_pt * LINE_HEIGHT_FACTOR
    return (1 + extra_headers) * header_pt + sum(
        estimate_bullet_height_pt(text, slot_width_in, font_pt)
        for text in bullet_texts
    )


def fit_bullets_dynamic(
    bullets: List[str],
    textbox_height_in: float,
    textbox_width_in: float,
    base_font_pt: int,
) -> Tuple[int, List[str], List[str]]:
    """Возвращает (итоговый_кегль, bullets_на_этот_слайд, bullets_на_продолжение)."""
    bullets = list(bullets)
    if not bullets:
        return (base_font_pt, [], [])
    if textbox_height_in <= 0 or textbox_width_in <= 0:
        return (base_font_pt, [], bullets)

    base_font_pt = max(base_font_pt, MIN_FONT_PT)
    height_pt = textbox_height_in * 72.0
    width_pt = textbox_width_in * 72.0

    def lines_for(text: str, font_pt: int) -> int:
        chars_per_line = max(1, int(width_pt / (CHAR_WIDTH_FACTOR * font_pt)))
        return max(1, math.ceil(len(text) / chars_per_line))

    def capacity(font_pt: int) -> int:
        line_height = font_pt * LINE_HEIGHT_FACTOR
        return int(height_pt / line_height)

    # 1) понижаем кегль, пока всё не поместится
    for font_pt in range(base_font_pt, MIN_FONT_PT - 1, -1):
        if sum(lines_for(b, font_pt) for b in bullets) <= capacity(font_pt):
            return (font_pt, bullets, [])

    # 2) на MIN_FONT_PT всё равно не влезает — режем, остаток на продолжение
    cap = capacity(MIN_FONT_PT)
    used = 0
    count = 0
    for b in bullets:
        lines = lines_for(b, MIN_FONT_PT)
        if used + lines > cap:
            break
        used += lines
        count += 1
    return (MIN_FONT_PT, bullets[:count], bullets[count:])
