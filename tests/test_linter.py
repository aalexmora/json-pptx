"""Тесты для dev-линтера `roadmap_generator/linter.py`."""
from __future__ import annotations

from roadmap_generator.linter import lint_model, save_custom_rules
from roadmap_generator.schema import normalize_roadmap


def _model_with_requirements(requirements, language="en"):
    data = [{
        "Product": "P",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": requirements,
        }]}]}],
    }]
    return normalize_roadmap(data, language=language)


def test_cyrillic_in_en_flagged():
    model = _model_with_requirements([
        {"Id": 10, "Kbr": "Yes", "MarketingTitle": "ok", "MarketingTitleEn": "English feature", "IsSubjectToChange": False},
        {"Id": 11, "Kbr": "Yes", "MarketingTitle": "ok", "MarketingTitleEn": "Русское название", "IsSubjectToChange": False},
    ], language="en")
    issues = lint_model(model)
    assert len(issues) == 1
    assert issues[0]["requirement_id"] == 11
    assert "кириллица" in issues[0]["message"]


def test_cyrillic_not_flagged_in_ru():
    model = _model_with_requirements([
        {"Id": 10, "Kbr": "Yes", "MarketingTitle": "Русский текст", "IsSubjectToChange": False},
    ], language="ru")
    assert lint_model(model) == []


def test_custom_regex_rules(load_fixture):
    save_custom_rules([{"pattern": r"Android", "description": "нежелательное слово Android"}])
    model = normalize_roadmap(load_fixture("en_with_content.json"), language="en")
    issues = lint_model(model)
    assert any("Android" in i["message"] for i in issues)
    # EN-модель en_with_content содержит «Android 16 support» → ровно 1 матч
    assert len(issues) == 1


def test_broken_regex_is_ignored():
    save_custom_rules([{"pattern": r"([", "description": "битая регулярка"}])
    model = _model_with_requirements([
        {"Id": 10, "Kbr": "Yes", "MarketingTitle": "ok", "MarketingTitleEn": "some text", "IsSubjectToChange": False},
    ], language="en")
    assert lint_model(model) == []
