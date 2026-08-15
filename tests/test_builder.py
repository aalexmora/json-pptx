"""Тесты для `roadmap_generator/builder.py` (структурная проверка рендера)."""
from __future__ import annotations

from pptx import Presentation

from roadmap_generator.builder import build_presentation
from roadmap_generator.plugins_engine import RoadmapSlide, build_slide_plan
from roadmap_generator.schema import normalize_roadmap


def _plan(load_fixture, name: str):
    return build_slide_plan(normalize_roadmap(load_fixture(name), language="ru"), {})


def _slide_text(slide) -> str:
    chunks = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def test_pagination_slide_count(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    # product divider + stream divider + 2 roadmap = 4
    assert len(prs.slides) == 4


def test_dividers_render_titles(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    assert "Kaspersky Next" in _slide_text(prs.slides[0])
    assert "Kaspersky Next Optimum" in _slide_text(prs.slides[1])


def test_continuation_eyebrow(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    # slides[2] = первый roadmap (Q1-Q4), slides[3] = continuation (Q1 2026)
    assert "cont." in _slide_text(prs.slides[3])


def test_flat_column_bullets(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    # product divider, stream divider, roadmap = 3 слайда
    roadmap_text = _slide_text(prs.slides[2])
    assert "Q1 2025" in roadmap_text
    assert "Feed X" in roadmap_text
    assert "Sandbox Z" in roadmap_text


def test_group_headers_rendered(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    roadmap_text = _slide_text(prs.slides[2])
    assert "Managed Detection and Response" in roadmap_text


def test_inherits_slide_size(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    template = Presentation(str(synthetic_template_path))
    assert prs.slide_width == template.slide_width
    assert prs.slide_height == template.slide_height


def test_many_bullets_paginate_via_flexible_columns(load_fixture, synthetic_template_path):
    # 200 фич в одном квартале → 20 колонок → 5 roadmap-слайдов (гибкая раскладка)
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 1000 + i, "Kbr": "Yes", "MarketingTitle": f"feature number {i}"}
                for i in range(200)
            ],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    roadmap_slides = [s for s in plan.slides if isinstance(s, RoadmapSlide)]
    assert len(roadmap_slides) == 5  # 200/10 = 20 колонок → 5 слайдов
    prs = build_presentation(plan)
    # product divider + stream divider + 5 roadmap = 7 слайдов
    assert len(prs.slides) == 7
