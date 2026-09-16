"""Тесты FastAPI-слоя (этап 5): /api/plan, /api/pptx, /api/health."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import app
from roadmap_generator import product_logos, tier_names


def _plan(client, data, language="ru", plugin_settings=None):
    return client.post(
        "/api/plan",
        json={"json_data": data, "language": language, "plugin_settings": plugin_settings or {}},
    )


def test_health():
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert isinstance(body["version"], str) and body["version"]


def test_profile_persists_language_specific_tier_names():
    original = "Kaspersky Next EDR Foundations"
    with TestClient(app) as c:
        profile = c.get("/api/profile").json()
        profile["tier_names"] = {original: {"ru": "Kaspersky Symphony EDR Foundations", "en": "English Tier"}}
        assert c.post("/api/profile", json=profile).status_code == 200
        saved = c.get("/api/profile").json()["tier_names"]

    assert saved[original] == {"ru": "Kaspersky Symphony EDR Foundations", "en": "English Tier"}
    assert tier_names.get_tier_name(original, "ru") == "Kaspersky Symphony EDR Foundations"


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
    data = load_fixture("non_next_product_flat.json")
    with TestClient(app) as c:
        # по умолчанию (auto) не-Next → группировка выключена
        auto = _plan(c, data).json()
        auto_cols = [col for s in auto["plan"]["slides"] for col in s.get("columns", [])]
        assert auto_cols and all(col["grouped"] is False for col in auto_cols)
        # включаем группировку → grouped
        on = _plan(c, data, plugin_settings={"global": {"apptitle_grouping": {"enabled": True}}}).json()
        on_cols = [col for s in on["plan"]["slides"] for col in s.get("columns", [])]
        assert on_cols and all(col["grouped"] is True for col in on_cols)


def test_pptx_endpoint(load_fixture):
    data = load_fixture("pagination_5_quarters.json")
    with TestClient(app) as c:
        r = c.post("/api/pptx", json={"json_data": data, "language": "ru", "plugin_settings": {}})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert r.headers["content-disposition"] == 'attachment; filename="roadmap_RU.pptx"'
        assert r.content[:2] == b"PK"  # zip-magic .pptx


def test_pptx_endpoint_english_filename(load_fixture):
    data = load_fixture("en_with_content.json")
    with TestClient(app) as c:
        r = c.post("/api/pptx", json={"json_data": data, "language": "en", "plugin_settings": {}})
        assert r.status_code == 200
        assert r.headers["content-disposition"] == 'attachment; filename="roadmap_ENG.pptx"'


def test_lint_issues_in_plan_response():
    data = [{
        "Product": "P",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 10, "Kbr": "Yes", "MarketingTitle": "ok", "MarketingTitleEn": "Русский"},
            ],
        }]}]}],
    }]
    with TestClient(app) as c:
        r = _plan(c, data, language="en")
        body = r.json()
        assert len(body["lint_issues"]) == 1
        assert body["lint_issues"][0]["message"]


def test_plan_returns_structured_quality_issue_for_missing_crdate():
    data = [{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "Title": "RPP title", "AppTitle": "A",
            "TrDate": "15.04.2025 21:00:00", "CrDate": None,
            "Requirements": [{"Id": 10, "MarketingTitle": "ok"}],
        }]}]}],
    }]
    with TestClient(app) as c:
        body = _plan(c, data).json()

    assert body["errors"] == []
    assert body["quality_issues"][0] == {
        "code": "missing_crdate",
        "severity": "warning",
        "message": "CrDate не заполнена — квартал рассчитан по TrDate",
        "release_id": 1,
        "rpp_title": "RPP title",
        "trdate": "15.04.2025 21:00:00",
        "quarter": "Q2 2025",
        "product": "P",
        "stream": "S",
        "tier": "T",
    }


def test_diff_endpoint():
    old = [{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 10, "Kbr": "Yes", "MarketingTitle": "old"}],
        }]}]}],
    }]
    new = [{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 10, "Kbr": "Yes", "MarketingTitle": "new"}],
        }]}]}],
    }]
    with TestClient(app) as c:
        r = c.post("/api/diff", json={"old_json": old, "new_json": new, "language": "ru"})
        assert r.status_code == 200
        body = r.json()
        assert body["diff"]["changed_requirement_ids"] == [10]


def test_svg_product_logo_upload_is_converted_to_png(tmp_path, monkeypatch):
    monkeypatch.setattr(product_logos, "LOGO_DIR", tmp_path / "product-logos")
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40">
      <rect width="80" height="40" fill="#006dff"/>
    </svg>'''

    with TestClient(app) as c:
        response = c.post(
            "/api/product-logos/upload",
            data={"product_name": "Kaspersky Next"},
            files={"file": ("next.svg", svg, "image/svg+xml")},
        )

    assert response.status_code == 200
    assert response.json()["filename"] == "kaspersky-next.png"
    saved = tmp_path / "product-logos" / "kaspersky-next.png"
    assert saved.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_logo_upload_rejects_unsupported_format(tmp_path, monkeypatch):
    monkeypatch.setattr(product_logos, "LOGO_DIR", tmp_path / "product-logos")

    with TestClient(app) as c:
        response = c.post(
            "/api/product-logos/upload",
            data={"product_name": "Kaspersky Next"},
            files={"file": ("next.gif", b"GIF89a", "image/gif")},
        )

    assert response.status_code == 422
    assert "Неподдерживаемый формат" in response.json()["detail"]
