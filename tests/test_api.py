"""Тесты FastAPI-слоя (этап 5): /api/plan, /api/pptx, /api/health."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import app


def _plan(client, data, language="ru", plugin_settings=None):
    return client.post(
        "/api/plan",
        json={"json_data": data, "language": language, "plugin_settings": plugin_settings or {}},
    )


def test_health():
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_plan_endpoint(load_fixture):
    data = load_fixture("pagination_5_quarters.json")
    with TestClient(app) as c:
        r = _plan(c, data)
        assert r.status_code == 200
        body = r.json()
        assert body["errors"] == []
        slides = body["plan"]["slides"]
        assert slides
        # первый слайд — титульный (TitleSlide с полем year/version)
        assert "year" in slides[0] and "version" in slides[0]
        # product-divider присутствует
        products = [s for s in slides if s.get("divider_type") == "product"]
        assert products and products[0]["title"] == "Kaspersky Next"


def test_plan_endpoint_invalid_json():
    with TestClient(app) as c:
        r = _plan(c, [])
        assert r.status_code == 200
        body = r.json()
        assert body["errors"]  # пустой список → ошибка валидации
        assert body["plan"] is None


def test_plan_reflects_plugin_settings(load_fixture):
    data = load_fixture("missing_optional_fields.json")
    with TestClient(app) as c:
        # по умолчанию kbr_filter включён → 2 фичи
        on = _plan(c, data).json()
        n_on = sum(len(col["bullets"]) for s in on["plan"]["slides"] for col in s.get("columns", []))
        # выключаем kbr_filter → 4 фичи
        off = _plan(c, data, plugin_settings={"global": {"kbr_filter": {"enabled": False}}}).json()
        n_off = sum(len(col["bullets"]) for s in off["plan"]["slides"] for col in s.get("columns", []))
        assert n_on == 2
        assert n_off == 4


def test_pptx_endpoint(load_fixture):
    data = load_fixture("pagination_5_quarters.json")
    with TestClient(app) as c:
        r = c.post("/api/pptx", json={"json_data": data, "language": "ru", "plugin_settings": {}})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert r.content[:2] == b"PK"  # zip-magic .pptx


def test_lint_issues_in_plan_response():
    data = [{
        "Product": "P",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "ok", "MarketingTitleEn": "Русский", "IsSubjectToChange": False},
            ],
        }]}]}],
    }]
    with TestClient(app) as c:
        r = _plan(c, data, language="en")
        body = r.json()
        assert len(body["lint_issues"]) == 1
        assert body["lint_issues"][0]["message"]


def test_diff_endpoint():
    old = [{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 10, "Kbr": "Yes", "MarketingTitle": "old", "IsSubjectToChange": False}],
        }]}]}],
    }]
    new = [{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 10, "Kbr": "Yes", "MarketingTitle": "new", "IsSubjectToChange": False}],
        }]}]}],
    }]
    with TestClient(app) as c:
        r = c.post("/api/diff", json={"old_json": old, "new_json": new, "language": "ru"})
        assert r.status_code == 200
        body = r.json()
        assert body["diff"]["changed_requirement_ids"] == [10]
