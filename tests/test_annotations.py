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
                {"Id": 10, "Kbr": "Subject to Change", "MarketingTitle": "Tentative"},
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
    assert xdr.inheritance_note.splitlines() == [
        "inc. all features of previous tier(s):",
        "• Kaspersky Next Optimum / Kaspersky Next EDR Foundations",
        "• Kaspersky Next Optimum / Kaspersky Next EDR Optimum",
    ]


# ---------------------------------------------------------------------------
# Наследование: заметка без фильтрации фич
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


def test_tier_inheritance_keeps_requirements_and_adds_note():
    """Галка добавляет заметку, но не скрывает Requirements текущего Tier."""
    ordering.save_product_inheritance_flag("Kaspersky Next", True)
    plan = build_slide_plan(normalize_roadmap(_two_tier_data(), language="ru"), {})
    slides = _roadmap_slides(plan)

    junior = next(s for s in slides if s.tier == "Junior")
    senior = next(s for s in slides if s.tier == "Senior")

    assert "Junior feature" in _all_bullet_texts(junior)
    assert "Junior feature" in _all_bullet_texts(senior)
    assert "Senior feature" in _all_bullet_texts(senior)
    assert "S / Junior" in senior.inheritance_note


def test_tier_inheritance_disabled_keeps_duplicates():
    """Без галки наследования старший тир показывает все свои фичи (включая дубли)."""
    plan = build_slide_plan(normalize_roadmap(_two_tier_data(), language="ru"), {})
    slides = _roadmap_slides(plan)

    senior = next(s for s in slides if s.tier == "Senior")
    texts = _all_bullet_texts(senior)
    assert "Junior feature" in texts
    assert "Senior feature" in texts


def test_tier_inheritance_keeps_tier_with_only_reused_feature():
    """Tier с повторным Requirement остаётся в плане при включённой галке."""
    data = _two_tier_data()
    senior_requirements = data[0]["Streams"][0]["Tiers"][1]["Releases"][0]["Requirements"]
    senior_requirements[:] = senior_requirements[:1]
    ordering.save_product_inheritance_flag("Kaspersky Next", True)

    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    tier_names = [slide.tier for slide in _roadmap_slides(plan)]

    assert tier_names == ["Junior", "Senior"]
    senior = next(slide for slide in _roadmap_slides(plan) if slide.tier == "Senior")
    assert _all_bullet_texts(senior) == ["Junior feature"]


def test_tier_inheritance_note_uses_effective_tree_order_without_filtering():
    """Порядок влияет на заметку, но не на состав Requirements."""
    ordering.save_order("Kaspersky Next > S", ["Senior", "Junior"])
    ordering.save_product_inheritance_flag("Kaspersky Next", True)

    plan = build_slide_plan(normalize_roadmap(_two_tier_data(), language="ru"), {})
    slides = _roadmap_slides(plan)

    assert [slide.tier for slide in slides] == ["Senior", "Junior"]
    assert _all_bullet_texts(slides[0]) == ["Junior feature", "Senior feature"]
    assert _all_bullet_texts(slides[1]) == ["Junior feature"]
    assert "S / Senior" in slides[1].inheritance_note


def test_product_inheritance_keeps_requirements_across_all_product_streams():
    """Product-флаг добавляет заметки, не фильтруя одинаковые Id между Stream."""
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

    assert len(base_slides) == 2
    assert set(senior_by_stream) == {"S1", "S2"}
    assert [_all_bullet_texts(slide) for slide in base_slides] == [["Base S1"], ["Base S2"]]
    assert _all_bullet_texts(senior_by_stream["S1"]) == ["Base S1", "Unique S1"]
    assert _all_bullet_texts(senior_by_stream["S2"]) == ["Base S2", "Unique S2"]
    assert "S1 / Base" in senior_by_stream["S1"].inheritance_note
    assert "S1 / Senior" in senior_by_stream["S2"].inheritance_note
    assert "S2 / Base" in senior_by_stream["S2"].inheritance_note


def test_product_inheritance_never_deduplicates_next_product():
    """История Requirement.Id и список предыдущих тиров сбрасываются на границе Product."""
    def make_product(product_name, requirement_text):
        return {
            "Product": product_name,
            "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
                "Id": 1,
                "AppTitle": "A",
                "TrDate": "15.01.2025 21:00:00",
                "Requirements": [{
                    "Id": 1001,
                    "Kbr": "Yes",
                    "MarketingTitle": requirement_text,
                }],
            }]}]}],
        }

    data = [
        make_product("Kaspersky Next", "Next feature"),
        make_product("Another Product", "Another product feature"),
    ]
    ordering.save_product_inheritance_flag("Kaspersky Next", True)

    slides = _roadmap_slides(build_slide_plan(normalize_roadmap(data, language="ru"), {}))
    another = next(slide for slide in slides if slide.product == "Another Product")

    assert _all_bullet_texts(another) == ["Another product feature"]
    assert another.inheritance_note == ""


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
        {"name": "Intro", "position": "end", "prompt": "Summarize the roadmap"},
        {"name": "Pre", "position": "before:Kaspersky Next"},
        {"name": "English end", "position": "end", "language": "en"},
    ])
    model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="ru")
    plan = build_slide_plan(model, {})
    static_names = [s.name for s in plan.slides if isinstance(s, StaticSlide)]
    assert static_names == ["Pre", "Intro"]
    intro = next(s for s in plan.slides if isinstance(s, StaticSlide) and s.name == "Intro")
    assert intro.prompt == "Summarize the roadmap"
    assert static_slides.export_state()[1]["prompt"] == ""
    assert intro.language == "ru"
    en_model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="en")
    en_plan = build_slide_plan(en_model, {})
    assert [s.name for s in en_plan.slides if isinstance(s, StaticSlide)] == ["English end"]
    idx_pre = next(i for i, s in enumerate(plan.slides) if isinstance(s, StaticSlide) and s.name == "Pre")
    idx_prod = next(i for i, s in enumerate(plan.slides) if isinstance(s, DividerSlide) and s.divider_type == "product")
    assert idx_pre < idx_prod


def test_first_static_slide_and_optional_generated_ends(load_fixture):
    from roadmap_generator import deck_meta
    from roadmap_generator.plugins_engine import TitleSlide

    static_slides.save_static_slides([
        {"name": "Own cover", "position": "first", "language": "ru"},
    ])
    deck_meta.import_state({
        "include_title_slide": False,
        "include_thank_you_slide": False,
    })
    plan = build_slide_plan(
        normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="ru"),
        {},
    )

    assert isinstance(plan.slides[0], StaticSlide)
    assert plan.slides[0].position == "first"
    assert not any(isinstance(slide, TitleSlide) for slide in plan.slides)
    assert not any(isinstance(slide, ThankYouSlide) for slide in plan.slides)
