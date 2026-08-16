"""Тесты для `roadmap_generator/diffing.py` (этап 7)."""
from __future__ import annotations

from roadmap_generator.diffing import compute_diff, match_previous_project
from roadmap_generator.schema import normalize_roadmap


def _model(data, language="ru"):
    return normalize_roadmap(data, language=language)


def test_compute_diff_new_changed_removed():
    old = _model([{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [
            {"Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00", "Requirements": [
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "old text", "IsSubjectToChange": False},
            ]},
            {"Id": 2, "AppTitle": "B", "TrDate": "15.04.2025 21:00:00", "Requirements": [
                {"Id": 20, "Kbr": "Yes", "MarketingTitle": "remove me", "IsSubjectToChange": False},
            ]},
        ]}]}],
    }])
    new = _model([{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [
            {"Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00", "Requirements": [
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "changed text", "IsSubjectToChange": False},
            ]},
            {"Id": 3, "AppTitle": "C", "TrDate": "15.07.2025 21:00:00", "Requirements": [
                {"Id": 30, "Kbr": "Yes", "MarketingTitle": "new req", "IsSubjectToChange": False},
            ]},
        ]}]}],
    }])

    diff = compute_diff(old, new)
    assert diff.new_release_ids == [3]
    assert diff.removed_release_ids == [2]
    assert diff.changed_release_ids == []
    assert diff.new_requirement_ids == [30]
    assert diff.removed_requirement_ids == [20]
    assert diff.changed_requirement_ids == [10]


def test_compute_diff_release_changed_when_quarter_moves():
    old = _model([{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [
            {"Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00", "Requirements": [
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "x", "IsSubjectToChange": False},
            ]},
        ]}]}],
    }])
    new = _model([{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [
            {"Id": 1, "AppTitle": "A", "TrDate": "15.04.2025 21:00:00", "Requirements": [
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "x", "IsSubjectToChange": False},
            ]},
        ]}]}],
    }])

    diff = compute_diff(old, new)
    assert diff.changed_release_ids == [1]  # квартал сменился Q1 -> Q2
    assert diff.changed_requirement_ids == []


def test_match_previous_project_new_tier():
    old = _model([{"Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": []}]}]}])
    new_raw = [{
        "Product": "P",
        "Streams": [{"Stream": "S", "Tiers": [
            {"Tier": "T", "Releases": []},
            {"Tier": "T2", "Releases": []},
        ]}],
    }]
    match = match_previous_project(old, new_raw)
    assert match.new_tier_paths == ["P > S > T2"]
    assert "P > S > T" in match.matched_tier_paths
