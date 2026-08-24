"""Тесты для текстовых аннотаций (Этап 6): Subject to Change и наследование тиров."""
from __future__ import annotations

from roadmap_generator import ordering, static_slides, strings
from roadmap_generator.plugins_engine import (
    DividerSlide,
    RoadmapSlide,
    StaticSlide,
    ThankYouSlide,
    build_slide_plan,
    build_tree,
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
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "Tentative"},
                {"Id": 11, "Kbr": "No", "MarketingTitle": "Confirmed"},
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
    ordering.save_product_inheritance_flag("Kaspersky Next", True)
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
    ordering.save_product_inheritance_flag("Kaspersky Next", True)
    plan = build_slide_plan(model, {})
    slides = _roadmap_slides(plan)
    xdr = next(s for s in slides if s.tier == "Kaspersky Next XDR Optimum")
    assert "Kaspersky Next EDR Foundations" in xdr.inheritance_note
    assert "Kaspersky Next EDR Optimum" in xdr.inheritance_note


# ---------------------------------------------------------------------------
# Наследование: дедупликация фич
# ---------------------------------------------------------------------------

def _all_bullet_texts(slide):
    """Тексты всех фич слайда (учитывает grouped/groups)."""
    out = []
    for col in slide.columns:
        if col.grouped:
            out.extend(b.text for g in col.groups for b in g.bullets)
        else:
            out.extend(b.text for b in col.bullets)
    return out


def _two_tier_data():
    return [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [
            {"Tier": "Junior", "Releases": [
                {"Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
                 "Requirements": [{"Id": 1001, "Kbr": "Yes", "MarketingTitle": "Junior feature"}]}
            ]},
            {"Tier": "Senior", "Releases": [
                {"Id": 2, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
                 "Requirements": [
                     {"Id": 1001, "Kbr": "Yes", "MarketingTitle": "Junior feature"},  # дубль из младшего
                     {"Id": 1002, "Kbr": "Yes", "MarketingTitle": "Senior feature"},  # уникальная
                 ]}
            ]},
        ]}],
    }]


def test_tier_inheritance_dedup_removes_junior_features():
    """При включённом наследовании старший тир не дублирует фичи младшего."""
    ordering.save_product_inheritance_flag("Kaspersky Next", True)
    plan = build_slide_plan(normalize_roadmap(_two_tier_data(), language="ru"), {})
    slides = _roadmap_slides(plan)

    junior = next(s for s in slides if s.tier == "Junior")
    senior = next(s for s in slides if s.tier == "Senior")

    assert "Junior feature" in _all_bullet_texts(junior)
    assert "Junior feature" not in _all_bullet_texts(senior)
    assert "Senior feature" in _all_bullet_texts(senior)


def test_tier_inheritance_disabled_keeps_duplicates():
    """Без галки наследования старший тир показывает все свои фичи (включая дубли)."""
    plan = build_slide_plan(normalize_roadmap(_two_tier_data(), language="ru"), {})
    slides = _roadmap_slides(plan)

    senior = next(s for s in slides if s.tier == "Senior")
    texts = _all_bullet_texts(senior)
    assert "Junior feature" in texts
    assert "Senior feature" in texts


def test_tier_inheritance_skips_tier_empty_after_dedup():
    """Tier без уникальных фич после дедупликации не создаёт roadmap-слайд."""
    data = _two_tier_data()
    senior_requirements = data[0]["Streams"][0]["Tiers"][1]["Releases"][0]["Requirements"]
    senior_requirements[:] = senior_requirements[:1]
    ordering.save_product_inheritance_flag("Kaspersky Next", True)

    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    tier_names = [slide.tier for slide in _roadmap_slides(plan)]

    assert tier_names == ["Junior"]


def test_tier_inheritance_dedup_uses_effective_tree_order():
    """Предыдущий Tier определяется сохранённым порядком дерева, а не сырого JSON."""
    ordering.save_order("Kaspersky Next > S", ["Senior", "Junior"])
    ordering.save_product_inheritance_flag("Kaspersky Next", True)

    plan = build_slide_plan(normalize_roadmap(_two_tier_data(), language="ru"), {})
    slides = _roadmap_slides(plan)

    assert [slide.tier for slide in slides] == ["Senior"]
    assert "Senior feature" in _all_bullet_texts(slides[0])


def test_product_inheritance_deduplicates_across_all_product_streams():
    """Product-флаг использует единую историю Id для всех Stream продукта."""
    def make_stream(stream_name, base_text, unique_id):
        return {
            "Stream": stream_name,
            "Tiers": [
                {"Tier": "Base", "Releases": [{
                    "Id": unique_id * 10,
                    "AppTitle": "A",
                    "TrDate": "15.01.2025 21:00:00",
                    "Requirements": [{"Id": 1001, "Kbr": "Yes", "MarketingTitle": base_text}],
                }]},
                {"Tier": "Senior", "Releases": [{
                    "Id": unique_id * 10 + 1,
                    "AppTitle": "A",
                    "TrDate": "15.01.2025 21:00:00",
                    "Requirements": [
                        {"Id": 1001, "Kbr": "Yes", "MarketingTitle": base_text},
                        {"Id": unique_id, "Kbr": "Yes", "MarketingTitle": f"Unique {stream_name}"},
                    ],
                }]},
            ],
        }

    data = [{
        "Product": "Kaspersky Next",
        "Streams": [make_stream("S1", "Base S1", 2001), make_stream("S2", "Base S2", 2002)],
    }]
    ordering.save_product_inheritance_flag("Kaspersky Next", True)

    slides = _roadmap_slides(build_slide_plan(normalize_roadmap(data, language="ru"), {}))
    base_slides = [slide for slide in slides if slide.tier == "Base"]
    senior_by_stream = {slide.stream: slide for slide in slides if slide.tier == "Senior"}

    assert len(base_slides) == 1
    assert set(senior_by_stream) == {"S1", "S2"}
    assert "Base S1" in _all_bullet_texts(base_slides[0])
    assert _all_bullet_texts(senior_by_stream["S1"]) == ["Unique S1"]
    assert _all_bullet_texts(senior_by_stream["S2"]) == ["Unique S2"]
    assert "S1 / Base" in senior_by_stream["S1"].inheritance_note
    assert "S1 / Senior" in senior_by_stream["S2"].inheritance_note
    assert "S2 / Base" in senior_by_stream["S2"].inheritance_note


def test_product_inheritance_flag_is_exposed_on_product_tree_node(load_fixture):
    ordering.save_product_inheritance_flag("Kaspersky Next", True)
    model = normalize_roadmap(load_fixture("tier_hierarchy_next.json"), language="en")

    tree = build_tree(model)
    product = next(item for item in tree["products"] if item["name"] == "Kaspersky Next")

    assert product["inheritance_flag"] is True
    assert all("inheritance_flag" not in tier for stream in product["streams"] for tier in stream["tiers"])


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
