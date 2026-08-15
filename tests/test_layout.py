"""Тесты для `roadmap_generator/layout.py` (эвристика помещаемости bullet'ов)."""
from __future__ import annotations

from roadmap_generator.layout import fit_bullets_dynamic


def test_empty_bullets():
    assert fit_bullets_dynamic([], 5.0, 4.0, 14) == (14, [], [])


def test_all_fit_at_base():
    font, on, overflow = fit_bullets_dynamic(["a", "b", "c"], 5.0, 4.0, 14)
    assert font == 14
    assert on == ["a", "b", "c"]
    assert overflow == []


def test_shrinks_font_to_fit_all():
    # много коротких bullet'ов в невысоком box'е — кегль снижается, всё помещается
    bullets = ["x"] * 30
    font, on, overflow = fit_bullets_dynamic(bullets, 5.0, 3.0, 14)
    assert font < 14
    assert on == bullets
    assert overflow == []


def test_overflow_splits_preserving_order():
    bullets = [f"feature number {i} with a fairly long description" for i in range(30)]
    font, on, overflow = fit_bullets_dynamic(bullets, 3.0, 2.0, 14)
    assert font >= 8
    assert overflow
    assert on + overflow == bullets


def test_font_floor_is_min():
    bullets = ["very long feature description " * 5 for _ in range(20)]
    font, on, overflow = fit_bullets_dynamic(bullets, 1.0, 1.0, 14)
    assert font >= 8


def test_zero_dimensions_pushes_all_to_overflow():
    bullets = ["a", "b"]
    font, on, overflow = fit_bullets_dynamic(bullets, 0.0, 4.0, 14)
    assert on == []
    assert overflow == bullets
