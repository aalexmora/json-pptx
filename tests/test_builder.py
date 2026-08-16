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


def _all_texts(prs) -> list:
    return [_slide_text(s) for s in prs.slides]


def test_pagination_slide_count(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    # титульный + product + stream + 2 roadmap + спасибо = 6
    assert len(prs.slides) == 6


def test_dividers_render_titles(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    texts = _all_texts(prs)
    assert any("PRODUCT" in t and "Kaspersky Next" in t for t in texts)
    assert any("STREAM" in t and "Kaspersky Next Optimum" in t for t in texts)


def test_continuation_eyebrow(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    # RU-заголовок продолжения — «Роадмап (продолжение)»
    assert any("продолжение" in t for t in _all_texts(prs))


def test_flat_column_bullets(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    joined = "\n".join(_all_texts(prs))
    assert "Q1 2025" in joined
    assert "Feed X" in joined
    assert "Sandbox Z" in joined


def test_group_headers_rendered(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    assert any("Managed Detection and Response" in t for t in _all_texts(prs))


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
    # титульный + product + stream + 5 roadmap + спасибо = 9 слайдов
    assert len(prs.slides) == 9


def test_title_and_thank_you_slides(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    texts = _all_texts(prs)
    # первый слайд — титульный (дефолтный заголовок «Roadmap»), последний — «Спасибо!»
    assert "Roadmap" in texts[0]
    assert "Спасибо!" in texts[-1]
