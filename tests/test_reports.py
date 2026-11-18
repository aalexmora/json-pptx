from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from roadmap_generator import report_terms
from roadmap_generator.reports import NO_APP_TITLE_GROUP, NO_PRODUCT_GROUP, build_json_report
from roadmap_generator.schema import SERVICE_PRODUCT_NAME


def _release(release_id, trdate, crdate, app_title, requirements, **extra) -> dict:
    return {
        "Id": release_id,
        "Title": f"Release {release_id} title",
        "AppTitle": app_title,
        "TrDate": trdate,
        "CrDate": crdate,
        "TfsUrl": f"https://tfs.example/releases/{release_id}",
        "Requirements": requirements,
        **extra,
    }


def _requirement(requirement_id, **fields) -> dict:
    return {
        "Id": requirement_id,
        "Title": f"Feature {requirement_id}",
        "MarketingTitle": f"Маркетинг {requirement_id}",
        "TfsUrl": f"https://tfs.example/requirements/{requirement_id}",
        **fields,
    }


def _product(name, tiers) -> dict:
    return {
        "Product": name,
        "Streams": [{
            "Stream": "Stream",
            "Tiers": [{"Tier": tier, "Releases": releases} for tier, releases in tiers],
        }],
    }


def _roadmap() -> list[dict]:
    req_10 = _requirement(
        10, ApplicableForProduct="Product A; Product B",
        Visibility="RU and ENG", MarketingTitle="Интеграция с ФСТЭК",
    )
    req_20 = _requirement(20, Visibility="Only ENG", MarketingTitle="Яндекс")
    req_30 = _requirement(
        30, ApplicableForProduct="   ", Visibility="  only   RU ",
        MarketingTitle="Поддержка Astra Linux",
    )
    release_1 = _release(1, "1/15/2026 12:00:00 AM", None, "App A", [req_10, req_20])
    return [
        _product("Product A", [
            ("Tier 1", [release_1]),
            # Тот же релиз под другим Tier — одно и то же по Id.
            ("Tier 2", [json.loads(json.dumps(release_1))]),
        ]),
        _product("Product B", [("Tier 1", [
            _release(2, "16.04.2026 21:00:00", "", "App B", [req_10, req_30]),
            _release(3, "15.01.2027 21:00:00", "16.01.2027 21:00:00", "App B", [req_20]),
            _release(4, "not-a-date", None, "App B", [_requirement(50, ApplicableForProduct=None)]),
        ])]),
        {
            "Product": SERVICE_PRODUCT_NAME,
            "Streams": [{"Stream": "-", "Tiers": [{"Tier": "-", "Releases": [
                _release(5, "2/26/2026 12:00:00 AM", None, "App A", [
                    _requirement(40, ApplicableForProduct=None, Visibility="RU and ENG", MarketingTitle="СБЕР Бизнес"),
                ]),
                _release(6, "3/1/2026 12:00:00 AM", None, "", [
                    _requirement(
                        41, Title=None, MarketingTitle="MT 41", ApplicableForProduct=None,
                        Visibility="RU and ENG", TfsUrl="javascript:alert(1)",
                    ),
                ]),
            ]}]}],
        },
    ]


def _groups(section: dict) -> list[tuple[str, int, list[str]]]:
    return [
        (group["name"], group["count"], [item["id"] for item in group["items"]])
        for group in section["groups"]
    ]


def test_year_totals_count_unique_requirements_and_releases():
    years = build_json_report(_roadmap())["years"]

    assert years["2026"]["totals"] == {"requirements": 5, "releases": 4}
    assert years["2027"]["totals"] == {"requirements": 1, "releases": 1}


def test_missing_applicable_report_groups_by_app_title():
    report = build_json_report(_roadmap())["years"]["2026"]["missing_applicable"]

    assert report["count"] == 3
    assert _groups(report) == [
        ("App B", 1, ["30"]),
        ("App A", 1, ["40"]),
        (NO_APP_TITLE_GROUP, 1, ["41"]),
    ]
    # Требование без поля ApplicableForProduct не считается незаполненным.
    assert "20" not in json.dumps(report)
    no_app_title = report["groups"][-1]["items"][0]
    assert no_app_title == {"id": "41", "title": "MT 41", "tfs_url": None}
    assert report["groups"][0]["items"][0]["tfs_url"] == "https://tfs.example/requirements/30"


def test_missing_crdate_report_groups_releases_by_product_with_service_node_last():
    report = build_json_report(_roadmap())["years"]["2026"]["missing_crdate"]

    assert report["count"] == 4
    assert _groups(report) == [
        ("Product A", 1, ["1"]),
        ("Product B", 1, ["2"]),
        (NO_PRODUCT_GROUP, 2, ["5", "6"]),
    ]
    assert report["groups"][0]["items"][0] == {
        "id": "1",
        "title": "Release 1 title",
        "tfs_url": "https://tfs.example/releases/1",
        "trdate": "15.01.2026",
    }
    assert report["groups"][1]["items"][0]["trdate"] == "16.04.2026"


def test_only_ru_report_uses_dictionary_and_ru_visibility():
    report = build_json_report(_roadmap())["years"]["2026"]["only_ru"]

    assert report["count"] == 3
    assert _groups(report) == [
        ("Product A", 1, ["10"]),
        ("Product B", 2, ["10", "30"]),
        (NO_PRODUCT_GROUP, 1, ["40"]),
    ]
    product_b = report["groups"][1]["items"]
    assert product_b[1]["marketing_title"] == "Поддержка Astra Linux"
    assert product_b[1]["matched_terms"] == ["Astra"]
    # Only ENG не попадает в отчёт, даже если MarketingTitle содержит термин.
    assert all(item["id"] != "20" for group in report["groups"] for item in group["items"])


def test_reports_switch_with_year():
    year_2027 = build_json_report(_roadmap())["years"]["2027"]

    assert year_2027["missing_applicable"] == {"count": 0, "groups": []}
    assert year_2027["missing_crdate"] == {"count": 0, "groups": []}
    assert year_2027["only_ru"] == {"count": 0, "groups": []}


def test_custom_dictionary_is_cleaned_and_prefers_longer_terms():
    report = build_json_report(_roadmap(), ["Astra", "Astra Linux", "astra linux", " ", "сбер"])

    assert report["terms"] == ["Astra", "Astra Linux", "сбер"]
    only_ru = report["years"]["2026"]["only_ru"]
    assert _groups(only_ru) == [("Product B", 1, ["30"]), (NO_PRODUCT_GROUP, 1, ["40"])]
    assert only_ru["groups"][0]["items"][0]["matched_terms"] == ["Astra Linux"]
    assert only_ru["groups"][1]["items"][0]["matched_terms"] == ["СБЕР"]


def test_empty_dictionary_finds_nothing():
    roadmap = _roadmap()
    roadmap[0]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"][0]["MarketingTitleEn"] = "Yandex"

    report = build_json_report(roadmap, [])

    assert report["terms"] == []
    assert report["english_name_issues"] == []
    assert report["years"]["2026"]["only_ru"] == {"count": 0, "groups": []}


def test_english_name_terms_match_whole_words_and_skip_service_node():
    roadmap = _roadmap()
    requirements = roadmap[0]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"]
    requirements[0]["MarketingTitleEn"] = "фстек ФСТЭК FSTEC fsb ФСБ СБЕР sber YANDEX Яндекс ASTRA Астра"
    requirements[1]["MarketingTitleEn"] = "myYandexCloud Astraware"
    roadmap[1]["Streams"][0]["Tiers"][0]["Releases"][2]["Requirements"][0]["MarketingTitleEn"] = (
        "A Yandex.Cloud integration"
    )
    roadmap[2]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"][0]["MarketingTitleEn"] = "Yandex"

    issues = build_json_report(roadmap)["english_name_issues"]

    # Требование 10 есть в релизах 1 и 2 — каждое вхождение отдельной строкой.
    assert [(issue["product"], issue["release_id"], issue["requirement_id"]) for issue in issues] == [
        ("Product A", 1, "10"), ("Product B", 2, "10"), ("Product B", 4, "50"),
    ]
    assert issues[0]["matched_terms"] == [
        "фстек", "ФСТЭК", "FSTEC", "fsb", "ФСБ", "СБЕР", "sber",
        "YANDEX", "Яндекс", "ASTRA", "Астра",
    ]
    assert issues[0]["product"] == "Product A"
    assert issues[0]["release_title"] == "Release 1 title"
    assert issues[2]["matched_terms"] == ["Yandex"]


def test_report_ignores_malformed_values():
    roadmap = _roadmap()
    requirements = roadmap[0]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"]
    requirements[0]["MarketingTitleEn"] = None
    requirements[1]["MarketingTitleEn"] = 123
    requirements.append("not a requirement")
    roadmap.append("not a product")

    report = build_json_report(roadmap)

    assert report["english_name_issues"] == []
    assert report["years"]["2026"]["totals"] == {"requirements": 5, "releases": 4}
    assert build_json_report({"not": "a list"})["years"]["2026"]["totals"] == {"requirements": 0, "releases": 0}


def test_profile_keeps_report_terms(tmp_path):
    with TestClient(app) as client:
        profile = client.get("/api/profile").json()
        assert profile["report_terms"] == list(report_terms.DEFAULT_TERMS)

        profile["report_terms"] = ["  Astra ", "astra", "", "Росатом", 7]
        assert client.post("/api/profile", json=profile).status_code == 200
        assert client.get("/api/profile").json()["report_terms"] == ["Astra", "Росатом"]

        # Старый клиент или проект без ключа не сбрасывает словарь.
        legacy = {key: value for key, value in profile.items() if key != "report_terms"}
        assert client.post("/api/profile", json=legacy).status_code == 200
        assert client.get("/api/profile").json()["report_terms"] == ["Astra", "Росатом"]

        profile["report_terms"] = []
        assert client.post("/api/profile", json=profile).status_code == 200
        assert client.get("/api/profile").json()["report_terms"] == []

    saved = json.loads((tmp_path / "profile.json").read_text(encoding="utf-8"))
    assert saved["report_terms"] == []


def test_profile_without_report_terms_loads_default_dictionary(tmp_path):
    (tmp_path / "profile.json").write_text(json.dumps({"tier_names": {}}), encoding="utf-8")
    report_terms.import_state(["Только это"])

    app_module._load_profile()

    assert report_terms.get_terms() == list(report_terms.DEFAULT_TERMS)


def test_plan_report_uses_saved_dictionary():
    with TestClient(app) as client:
        profile = client.get("/api/profile").json()
        profile["report_terms"] = ["Astra Linux"]
        client.post("/api/profile", json=profile)
        roadmap = _roadmap()
        product_b_releases = roadmap[1]["Streams"][0]["Tiers"][0]["Releases"]
        product_b_releases[0]["CrDate"] = None  # экспортёр отдаёт null, а не пустую строку
        del product_b_releases[2]  # релиз с некорректной TrDate не проходит проверку
        payload = client.post("/api/plan", json={"json_data": roadmap, "language": "ru"}).json()

    assert payload["errors"] == []
    assert payload["report"]["terms"] == ["Astra Linux"]
    assert _groups(payload["report"]["years"]["2026"]["only_ru"]) == [("Product B", 1, ["30"])]


def test_csv_upload_api_is_removed():
    with TestClient(app) as client:
        response = client.post(
            "/api/reports/public-features",
            files={
                "json_file": ("roadmap.json", json.dumps(_roadmap()).encode(), "application/json"),
                "file": (
                    "features.csv",
                    b"ReqId\tIsPublished\tApplicableForProducts\n10\ttrue\tProduct A\n",
                    "text/tab-separated-values",
                ),
            },
        )
        assert response.status_code in {404, 405}
        assert "/api/reports/public-features" not in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("language", ["ru", "en"])
def test_annual_json_reports_work_without_csv(language, load_fixture):
    roadmap = load_fixture("en_with_content.json")
    release = roadmap[0]["Streams"][0]["Tiers"][0]["Releases"][0]
    release["TrDate"] = "15.01.2026 21:00:00"
    release["CrDate"] = "16.01.2026 21:00:00"
    release["Requirements"][0]["MarketingTitleEn"] = "Yandex integration"

    with TestClient(app) as client:
        response = client.post("/api/plan", json={"json_data": roadmap, "language": language})

    assert response.status_code == 200
    payload = response.json()
    assert payload["errors"] == []
    assert payload["plan"] is not None
    report = payload["report"]
    assert report["years"]["2026"]["totals"] == {"requirements": 3, "releases": 1}
    assert report["years"]["2027"]["totals"] == {"requirements": 0, "releases": 0}
    assert report["english_name_issues"][0]["matched_terms"] == ["Yandex"]
