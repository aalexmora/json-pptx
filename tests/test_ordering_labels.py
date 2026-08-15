"""Тесты для `roadmap_generator/ordering.py` и `labels.py` (Этап 2)."""
from __future__ import annotations

from roadmap_generator import labels, ordering
from roadmap_generator.plugins_engine import RoadmapSlide, build_slide_plan
from roadmap_generator.schema import normalize_roadmap


# ---------------------------------------------------------------------------
# ordering.get_effective_order
# ---------------------------------------------------------------------------

def test_get_effective_order_default_preserves_input():
    assert ordering.get_effective_order("", ["A", "B", "C"]) == ["A", "B", "C"]


def test_get_effective_order_saved_order_new_at_end():
    ordering.save_order("root", ["B", "A"])
    # «C» не встречался — в конец, в порядке появления
    assert ordering.get_effective_order("root", ["A", "B", "C"]) == ["B", "A", "C"]


def test_get_effective_order_drops_gone_nodes():
    ordering.save_order("root", ["B", "A", "Z"])
    # «Z» больше нет во входном списке — отбрасывается
    assert ordering.get_effective_order("root", ["A", "B"]) == ["B", "A"]


# ---------------------------------------------------------------------------
# ordering.resolve_apptitle_order
# ---------------------------------------------------------------------------

def test_resolve_apptitle_order_priority_first_then_count():
    ordering.save_apptitle_priority(["VIP"])
    items = [("Sandbox", 1), ("VIP", 2), ("Feeds", 3)]
    assert ordering.resolve_apptitle_order(items) == ["VIP", "Feeds", "Sandbox"]


def test_resolve_apptitle_order_no_priority_count_desc():
    items = [("A", 1), ("B", 3), ("C", 2)]
    assert ordering.resolve_apptitle_order(items) == ["B", "C", "A"]


# ---------------------------------------------------------------------------
# labels
# ---------------------------------------------------------------------------

def test_get_apptitle_label_default():
    assert labels.get_apptitle_label("Original") == "Original"


def test_save_and_get_apptitle_label():
    labels.save_apptitle_label("Original", "Custom")
    assert labels.get_apptitle_label("Original") == "Custom"
    assert labels.get_apptitle_label("Other") == "Other"


def test_save_apptitle_label_blank_removes():
    labels.save_apptitle_label("Original", "Custom")
    labels.save_apptitle_label("Original", "")
    assert labels.get_apptitle_label("Original") == "Original"


def test_label_applied_in_slide_plan(load_fixture):
    labels.save_apptitle_label("Threat Data Feeds", "Фид угроз")
    model = normalize_roadmap(load_fixture("non_next_product_flat.json"), language="ru")
    settings = {"products": {"Kaspersky Threat Intelligence": {"apptitle_grouping": {"enabled": True}}}}
    plan = build_slide_plan(model, settings)
    slide = next(s for s in plan.slides if isinstance(s, RoadmapSlide))
    group_titles = [g.app_title for g in slide.columns[0].groups]
    assert group_titles == ["Фид угроз", "Sandbox"]
