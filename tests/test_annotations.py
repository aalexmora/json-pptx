"""Тесты для текстовых аннотаций (Этап 6): Subject to Change и наследование тиров."""
from __future__ import annotations

from roadmap_generator import ordering, static_slides, strings
from roadmap_generator.plugins_engine import (
    DividerSlide,
    RoadmapSlide,
    StaticSlide,
    ThankYouSlide,
    build_slide_plan,
)
from roadmap_generator.schema import normalize_roadmap


def _roadmap_slides(plan):
    return [s for s in plan.slides if isinstance(s, RoadmapSlide)]


# ---------------------------------------------------------------------------
# Subject to Change (текст: сортировка + `*` + сноска, без шейпа шаблона)
# ---------------------------------------------------------------------------

def test_subject_to_change_sorts_false_first():
    data = [{
        "Product": "Kaspersky Threat Intelligence",  # не-Next → группировка выключена (плоский список)
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "Tentative", "IsSubjectToChange": True},
                {"Id": 11, "Kbr": "Yes", "MarketingTitle": "Confirmed", "IsSubjectToChange": False},
            ],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    slide = _roadmap_slides(plan)[0]
    assert [b.text for b in slide.columns[0].bullets] == ["Confirmed", "Tentative"]


def test_subject_to_change_footnote_added(load_fixture):
    model = normalize_roadmap(load_fixture("subject_to_change_mixed.json"), language="ru")
    plan = build_slide_plan(model, {})
    slide = _roadmap_slides(plan)[0]
    assert slide.has_subject_to_change is True
    assert slide.footnote


def test_no_footnote_without_subject_to_change(load_fixture):
    model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="ru")
    plan = build_slide_plan(model, {})
    for slide in _roadmap_slides(plan):
        assert slide.has_subject_to_change is False
        assert slide.footnote == ""


# ---------------------------------------------------------------------------
# Наследование тиров
# ---------------------------------------------------------------------------

def test_tier_inheritance_note_on_subsequent_tier(load_fixture):
    model = normalize_roadmap(load_fixture("tier_hierarchy_next.json"), language="en")
    ordering.save_tier_inheritance_flag(
        "Kaspersky Next > Kaspersky Next Optimum > Kaspersky Next EDR Optimum", True,
    )
    plan = build_slide_plan(model, {})
    slides = _roadmap_slides(plan)

    opt = next(s for s in slides if s.tier == "Kaspersky Next EDR Optimum")
    assert "inc. all features of previous tier(s):" in opt.inheritance_note
    assert "Kaspersky Next EDR Foundations" in opt.inheritance_note

    foundations = next(s for s in slides if s.tier == "Kaspersky Next EDR Foundations")
    assert foundations.inheritance_note == ""


def test_tier_inheritance_note_disabled_by_default(load_fixture):
    model = normalize_roadmap(load_fixture("tier_hierarchy_next.json"), language="en")
    plan = build_slide_plan(model, {})
    assert all(s.inheritance_note == "" for s in _roadmap_slides(plan))


def test_tier_inheritance_note_lists_all_previous_tiers(load_fixture):
    model = normalize_roadmap(load_fixture("tier_hierarchy_next.json"), language="en")
    ordering.save_tier_inheritance_flag(
        "Kaspersky Next > Kaspersky Next Optimum > Kaspersky Next XDR Optimum", True,
    )
    plan = build_slide_plan(model, {})
    slides = _roadmap_slides(plan)
    xdr = next(s for s in slides if s.tier == "Kaspersky Next XDR Optimum")
    assert "Kaspersky Next EDR Foundations" in xdr.inheritance_note
    assert "Kaspersky Next EDR Optimum" in xdr.inheritance_note


def test_service_strings_override(load_fixture):
    strings.save_service_strings({"thank_you": {"ru": "Пока!", "en": "Bye!"}})
    model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="ru")
    plan = build_slide_plan(model, {})
    thank = next(s for s in plan.slides if isinstance(s, ThankYouSlide))
    assert thank.text == "Пока!"


def test_service_strings_default_when_no_override(load_fixture):
    model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="en")
    plan = build_slide_plan(model, {})
    thank = next(s for s in plan.slides if isinstance(s, ThankYouSlide))
    assert thank.text == "Thank you!"


def test_static_slides_insertion(load_fixture):
    static_slides.save_static_slides([
        {"name": "Intro", "position": "end"},
        {"name": "Pre", "position": "before:Kaspersky Next"},
    ])
    model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="ru")
    plan = build_slide_plan(model, {})
    static_names = [s.name for s in plan.slides if isinstance(s, StaticSlide)]
    assert static_names == ["Pre", "Intro"]
    idx_pre = next(i for i, s in enumerate(plan.slides) if isinstance(s, StaticSlide) and s.name == "Pre")
    idx_prod = next(i for i, s in enumerate(plan.slides) if isinstance(s, DividerSlide) and s.divider_type == "product")
    assert idx_pre < idx_prod
