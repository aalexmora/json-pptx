"""Тесты этапа 6: under_approval_badge и профиль (export/import)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import app
from roadmap_generator import approval
from roadmap_generator.plugins_engine import RoadmapSlide, build_slide_plan
from roadmap_generator.schema import normalize_roadmap


def _two_quarter_model():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [
            {"Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00", "Requirements": [
                {"Id": 11, "Kbr": "Yes", "MarketingTitle": "x", "MarketingTitleEn": "x", "IsSubjectToChange": False},
            ]},
            {"Id": 2, "AppTitle": "A", "TrDate": "15.04.2025 21:00:00", "Requirements": [
                {"Id": 12, "Kbr": "Yes", "MarketingTitle": "y", "MarketingTitleEn": "y", "IsSubjectToChange": False},
            ]},
        ]}]}],
    }]
    return normalize_roadmap(data, language="en")


def test_under_approval_badge_on_marked_quarter():
    approval.set_under_approval_ids([1])  # релиз 1 → Q1 2025
    plan = build_slide_plan(_two_quarter_model(), {})
    slide = next(s for s in plan.slides if isinstance(s, RoadmapSlide))
    by_quarter = {c.quarter: c for c in slide.columns}
    assert by_quarter["Q1 2025"].under_approval_badge == "In the approval process"
    assert by_quarter["Q2 2025"].under_approval_badge == ""


def test_no_under_approval_badge_by_default(load_fixture):
    model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="en")
    plan = build_slide_plan(model, {})
    for s in plan.slides:
        if isinstance(s, RoadmapSlide):
            for c in s.columns:
                assert c.under_approval_badge == ""


def test_profile_roundtrip():
    profile = {
        "ordering": {
            "order": {"": ["B", "A"]},
            "apptitle_priority": ["X"],
            "tier_inheritance_flags": {"a > b > c": True},
        },
        "labels": {"Old": "New"},
        "linter_rules": [{"pattern": "Android", "description": "x"}],
        "under_approval_ids": [5, 6],
    }
    with TestClient(app) as c:
        r = c.post("/api/profile", json=profile)
        assert r.status_code == 200
        got = c.get("/api/profile").json()
        assert got["ordering"]["order"] == {"": ["B", "A"]}
        assert got["ordering"]["apptitle_priority"] == ["X"]
        assert got["labels"] == {"Old": "New"}
        assert got["linter_rules"] == [{"pattern": "Android", "description": "x"}]
        assert got["under_approval_ids"] == [5, 6]
