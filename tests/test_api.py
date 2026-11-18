"""Тесты FastAPI-слоя (этап 5): /api/plan, /api/pptx, /api/health."""
from __future__ import annotations

from fastapi.testclient import TestClient

from io import BytesIO

from pptx import Presentation

from app import PlanRequest, _build, app
from roadmap_generator import product_logos, static_slides, tier_names
from roadmap_generator.schema import SERVICE_PRODUCT_NAME


def _service_product_node() -> dict:
    return {
        "Product": SERVICE_PRODUCT_NAME,
        "Streams": [{"Stream": "-", "Tiers": [{"Tier": "-", "Releases": [{
            "Id": 900, "Title": "Release without product", "AppId": 9, "AppTitle": "App X",
            "TrDate": "2/26/2026 12:00:00 AM", "CrDate": None,
            "Requirements": [{"Id": 9001, "Title": "Orphan", "ApplicableForProduct": None}],
        }]}]}],
    }


def _slide_texts(content: bytes) -> list[list[str]]:
    deck = Presentation(BytesIO(content))
    return [
        [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
        for slide in deck.slides
    ]


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


def test_release_log_matches_health_version():
    with TestClient(app) as c:
        health = c.get("/api/health").json()
        response = c.get("/api/release-log")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == health["version"]
    assert body["implemented"]
    assert body["remaining"]


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
        assert set(body["report"]["years"]) == {"2026", "2027"}
        slides = body["plan"]["slides"]
        assert slides
        # первый слайд — титульный (TitleSlide с полем year/version)
        assert "year" in slides[0] and "version" in slides[0]
        # product-divider присутствует
        products = [s for s in slides if s.get("divider_type") == "product"]
        assert products and products[0]["title"] == "Kaspersky Next"


def test_plan_request_filters_releases_to_requested_display_year(load_fixture):
    data = load_fixture("pagination_5_quarters.json")
    for year in (2025, 2026):
        plan, errors, *_ = _build(PlanRequest(
            json_data=data,
            language="ru",
            plugin_settings={},
            roadmap_year=year,
        ))

        assert errors == []
        quarters = {
            column.quarter
            for slide in plan.slides
            if hasattr(slide, "columns")
            for column in slide.columns
        }
        assert quarters
        assert {quarter.rsplit(" ", 1)[-1] for quarter in quarters} == {str(year)}


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


def test_static_slide_can_be_downloaded_after_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(static_slides, "STATIC_SLIDES_DIR", tmp_path / "static-slides")
    content = b"PK\x03\x04static-pptx"

    with TestClient(app) as c:
        uploaded = c.post(
            "/api/static-slides/pptx",
            files={"file": ("example.pptx", content, "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
        )
        downloaded = c.get("/api/static-slides/pptx/example.pptx")

    assert uploaded.status_code == 200
    assert downloaded.status_code == 200
    assert downloaded.content == content
    assert downloaded.headers["content-disposition"] == 'attachment; filename="example.pptx"'


def test_static_slide_download_returns_404_for_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(static_slides, "STATIC_SLIDES_DIR", tmp_path / "static-slides")
    with TestClient(app) as c:
        response = c.get("/api/static-slides/pptx/missing.pptx")
    assert response.status_code == 404


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


def test_service_product_node_does_not_change_plan_tree_or_quality(load_fixture):
    data = load_fixture("pagination_5_quarters.json")
    with TestClient(app) as c:
        for language in ("ru", "en"):
            plain = _plan(c, data, language=language).json()
            with_node = _plan(c, data + [_service_product_node()], language=language).json()

            assert with_node["errors"] == []
            for key in ("plan", "tree", "releases", "warnings", "lint_issues", "quality_issues"):
                assert with_node[key] == plain[key], key
            assert SERVICE_PRODUCT_NAME not in str(with_node["tree"])


def test_service_product_node_does_not_change_pptx(load_fixture):
    data = load_fixture("pagination_5_quarters.json")
    with TestClient(app) as c:
        for language in ("ru", "en"):
            payload = {"language": language, "plugin_settings": {}}
            plain = c.post("/api/pptx", json={**payload, "json_data": data})
            with_node = c.post("/api/pptx", json={**payload, "json_data": data + [_service_product_node()]})

            assert plain.status_code == with_node.status_code == 200
            assert _slide_texts(with_node.content) == _slide_texts(plain.content)


def test_only_service_product_node_is_reported_as_error():
    with TestClient(app) as c:
        body = _plan(c, [_service_product_node()]).json()
        pptx = c.post("/api/pptx", json={"json_data": [_service_product_node()], "language": "ru"})

    assert body["plan"] is None
    assert body["errors"] and SERVICE_PRODUCT_NAME in body["errors"][0]
    assert pptx.status_code == 422


def test_diff_ignores_service_product_node():
    old = [{
        "Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 10, "Kbr": "Yes", "MarketingTitle": "old"}],
        }]}]}],
    }]
    with TestClient(app) as c:
        body = c.post(
            "/api/diff",
            json={"old_json": old, "new_json": old + [_service_product_node()], "language": "ru"},
        ).json()

    assert all(not ids for ids in body["diff"].values())
    assert body["new_tier_paths"] == []
    assert body["removed_tier_paths"] == []


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


def test_product_slide_image_upload_status_and_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(product_logos, "PRODUCT_SLIDE_DIR", tmp_path / "product-slide-images")
    png = b"\x89PNG\r\n\x1a\nplaceholder"

    with TestClient(app) as c:
        uploaded = c.post(
            "/api/product-slide-images/upload",
            data={"product_name": "Product A"},
            files={"file": ("cover.png", png, "image/png")},
        )
        status = c.post(
            "/api/product-slide-images/status",
            json={"products": ["Product A", "Product B"]},
        ).json()["logos"]
        deleted = c.delete("/api/product-slide-images", params={"product_name": "Product A"})

    assert uploaded.status_code == 200
    assert status["Product A"]["has_logo"] is True
    assert status["Product B"]["has_logo"] is False
    assert deleted.status_code == 200


def test_product_slide_image_rejects_non_png(tmp_path, monkeypatch):
    monkeypatch.setattr(product_logos, "PRODUCT_SLIDE_DIR", tmp_path / "product-slide-images")

    with TestClient(app) as c:
        response = c.post(
            "/api/product-slide-images/upload",
            data={"product_name": "Product A"},
            files={"file": ("cover.jpg", b"not-a-png", "image/jpeg")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Фон продуктового слайда должен быть в формате PNG"

    with TestClient(app) as c:
        invalid_png = c.post(
            "/api/product-slide-images/upload",
            data={"product_name": "Product A"},
            files={"file": ("cover.png", b"not-a-png", "image/png")},
        )

    assert invalid_png.status_code == 422
    assert invalid_png.json()["detail"] == "Не удалось прочитать PNG-файл"


def test_tier_logo_key_uses_product_except_for_next_and_symphony():
    assert product_logos.tier_logo_key("Kaspersky Endpoint Security", "Tier A") == "Kaspersky Endpoint Security"
    assert product_logos.tier_logo_key("Kaspersky Next", "Tier A") == "Tier A"
    assert product_logos.tier_logo_key("Kaspersky Symphony XDR", "Tier B") == "Tier B"
    assert product_logos.tier_logo_key("Kaspersky Next Generation Firewall", "Tier C") == "Kaspersky Next Generation Firewall"


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
