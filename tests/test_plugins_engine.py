"""Тесты для `roadmap_generator/plugins_engine.py` (Этап 2).

Покрывают загрузку/конфликты плагинов, дефолты (Next vs не-Next), kbr-фильтр,
группировку по AppTitle, пагинацию по кварталам и формирование deck-порядка.
"""
from __future__ import annotations

from roadmap_generator.plugins_engine import (
    DividerSlide,
    RoadmapSlide,
    build_slide_plan,
    load_plugins,
    resolve_conflicts,
)
from roadmap_generator.schema import normalize_roadmap


def _model(load_fixture, name: str, language: str = "ru"):
    return normalize_roadmap(load_fixture(name), language=language)


def _roadmap_slides(plan):
    return [s for s in plan.slides if isinstance(s, RoadmapSlide)]


# ---------------------------------------------------------------------------
# Загрузка и конфликты
# ---------------------------------------------------------------------------

def test_load_plugins_finds_expected_ids():
    ids = {p.id for p in load_plugins()}
    assert {"kbr_filter", "apptitle_grouping"} <= ids


def test_resolve_conflicts_no_conflict():
    applicable, conflicts = resolve_conflicts(load_plugins())
    assert conflicts == []
    assert {p.id for p in applicable} == {"kbr_filter", "apptitle_grouping"}


class _FakeGroupingA:
    id = "fake_grouping_a"
    label = "Fake A"
    kind = "grouping"
    scope = "tier"

    def default_settings(self):
        return {}

    def apply(self, context, settings):
        return context


class _FakeGroupingB:
    id = "fake_grouping_b"
    label = "Fake B"
    kind = "grouping"
    scope = "tier"

    def default_settings(self):
        return {}

    def apply(self, context, settings):
        return context


def test_resolve_conflicts_detects_same_kind():
    applicable, conflicts = resolve_conflicts([_FakeGroupingA(), _FakeGroupingB()])
    assert applicable == []
    assert len(conflicts) == 1
    assert "grouping" in conflicts[0]


# ---------------------------------------------------------------------------
# kbr_filter
# ---------------------------------------------------------------------------

def test_kbr_filter_keeps_only_yes(load_fixture):
    model = _model(load_fixture, "missing_optional_fields.json")
    plan = build_slide_plan(model, {})
    slide = _roadmap_slides(plan)[0]
    texts = {b.text for b in slide.columns[0].bullets}
    # 4 требования: 2 с Kbr=Yes, 2 без Kbr (не проходят фильтр)
    assert texts == {"Complete", "No StC"}


def test_kbr_filter_excludes_no():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 11, "Kbr": "Yes", "MarketingTitle": "keep"},
                {"Id": 12, "Kbr": "No", "MarketingTitle": "drop"},
            ],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    slide = _roadmap_slides(plan)[0]
    assert {b.text for b in slide.columns[0].bullets} == {"keep"}


def test_kbr_filter_disabled_keeps_all(load_fixture):
    model = _model(load_fixture, "missing_optional_fields.json")
    plan = build_slide_plan(model, {"global": {"kbr_filter": {"enabled": False}}})
    slide = _roadmap_slides(plan)[0]
    assert len(slide.columns[0].bullets) == 4


# ---------------------------------------------------------------------------
# apptitle_grouping: дефолты и override
# ---------------------------------------------------------------------------

def test_grouping_default_on_for_next(load_fixture):
    model = _model(load_fixture, "pagination_5_quarters.json")
    plan = build_slide_plan(model, {})
    slide = _roadmap_slides(plan)[0]
    assert slide.columns[0].grouped is True


def test_grouping_default_off_for_non_next(load_fixture):
    model = _model(load_fixture, "non_next_product_flat.json")
    plan = build_slide_plan(model, {})
    slide = _roadmap_slides(plan)[0]
    assert slide.columns[0].grouped is False
    assert slide.columns[0].groups == []


def test_grouping_override_enable_and_order_by_count(load_fixture):
    model = _model(load_fixture, "non_next_product_flat.json")
    settings = {"products": {"Kaspersky Threat Intelligence": {"apptitle_grouping": {"enabled": True}}}}
    plan = build_slide_plan(model, settings)
    slide = _roadmap_slides(plan)[0]
    col = slide.columns[0]
    assert col.grouped is True
    # 2 группы: Threat Data Feeds (2 фичи) и Sandbox (1) — по убыванию количества
    assert [g.app_title for g in col.groups] == ["Threat Data Feeds", "Sandbox"]


# ---------------------------------------------------------------------------
# Пагинация и deck-порядок
# ---------------------------------------------------------------------------

def test_pagination_5_quarters(load_fixture):
    model = _model(load_fixture, "pagination_5_quarters.json")
    plan = build_slide_plan(model, {})
    slides = _roadmap_slides(plan)
    assert len(slides) == 2
    assert slides[0].continuation is False
    assert slides[1].continuation is True
    assert [c.quarter for c in slides[0].columns] == ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025"]
    assert [c.quarter for c in slides[1].columns] == ["Q1 2026"]


def test_single_slide_for_four_or_fewer_quarters(load_fixture):
    model = _model(load_fixture, "non_next_product_flat.json")
    plan = build_slide_plan(model, {})
    slides = _roadmap_slides(plan)
    assert len(slides) == 1
    assert slides[0].continuation is False


def test_flexible_columns_split_heavy_quarter():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 1000 + i, "Kbr": "Yes", "MarketingTitle": f"f{i}"}
                for i in range(25)
            ],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    slides = _roadmap_slides(plan)
    # 25 фич в одном квартале → 3 колонки (10+10+5) → 1 слайд (≤4)
    assert len(slides) == 1
    assert len(slides[0].columns) == 3
    assert [len(c.bullets) for c in slides[0].columns] == [10, 10, 5]


def test_flexible_columns_heavy_quarter_spans_columns_in_order():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [
            {"Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00", "Requirements": [
                {"Id": 1000 + i, "Kbr": "Yes", "MarketingTitle": f"q1-{i}"} for i in range(25)
            ]},
            {"Id": 2, "AppTitle": "A", "TrDate": "15.04.2025 21:00:00", "Requirements": [
                {"Id": 2000 + i, "Kbr": "Yes", "MarketingTitle": f"q2-{i}"} for i in range(5)
            ]},
        ]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    slides = _roadmap_slides(plan)
    assert len(slides) == 1
    assert len(slides[0].columns) == 4
    assert [c.quarter for c in slides[0].columns] == ["Q1 2025", "Q1 2025", "Q1 2025", "Q2 2025"]


def test_flexible_columns_paginate_when_over_four():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 1000 + i, "Kbr": "Yes", "MarketingTitle": f"f{i}"}
                for i in range(45)
            ],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    slides = _roadmap_slides(plan)
    # 45 фич → 5 колонок (10×4 + 5) → 2 слайда (4 + 1)
    assert len(slides) == 2
    assert slides[0].continuation is False
    assert slides[1].continuation is True
    assert len(slides[0].columns) == 4
    assert len(slides[1].columns) == 1


def test_product_divider_precedes_slides(load_fixture):
    model = _model(load_fixture, "pagination_5_quarters.json")
    plan = build_slide_plan(model, {})
    assert isinstance(plan.slides[0], DividerSlide)
    assert plan.slides[0].divider_type == "product"
    assert plan.slides[0].title == "Kaspersky Next"


def test_stream_dash_has_no_stream_divider():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "-", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 11, "Kbr": "Yes", "MarketingTitle": "x"}],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    dividers = [s for s in plan.slides if isinstance(s, DividerSlide)]
    assert len(dividers) == 1
    assert dividers[0].divider_type == "product"
    assert len(_roadmap_slides(plan)) == 1


def test_empty_tier_after_filter_skipped():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 11, "Kbr": "No", "MarketingTitle": "drop"}],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    assert plan.slides == []


def test_empty_product_skipped(real_data):
    model = normalize_roadmap(real_data, language="ru")
    plan = build_slide_plan(model, {})
    # только Kaspersky Next даёт контент; остальные продукты пропущены целиком
    products = {s.title for s in plan.slides if isinstance(s, DividerSlide) and s.divider_type == "product"}
    assert products == {"Kaspersky Next"}
