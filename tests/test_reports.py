from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import app
from roadmap_generator.reports import build_json_report


def _roadmap() -> list[dict]:
    return [{
        "Product": "Product A",
        "Streams": [{
            "Stream": "Stream A",
            "Tiers": [{
                "Tier": "Tier A",
                "Releases": [
                    {
                        "Id": 1,
                        "Title": "Release one",
                        "TfsUrl": "https://tfs.example/releases/1",
                        "AppTitle": "App A",
                        "TrDate": "15.01.2026 21:00:00",
                        "CrDate": None,
                        "Requirements": [
                            {"Id": 10, "MarketingTitle": "Feature 10"},
                            {"Id": 20, "MarketingTitle": "Feature 20"},
                        ],
                    },
                    {
                        "Id": 2,
                        "Title": "Release two",
                        "AppTitle": "",
                        "TrDate": "not-a-date",
                        "CrDate": "16.04.2026 21:00:00",
                        "Requirements": [{"Id": 10, "MarketingTitle": "Feature 10"}],
                    },
                    {
                        "Id": 3,
                        "Title": "Release three",
                        "AppTitle": "App A",
                        "TrDate": "15.07.2026 21:00:00",
                        "CrDate": "",
                        "Requirements": [],
                    },
                    {
                        "Id": 4,
                        "Title": "Release four",
                        "AppTitle": "App A",
                        "TrDate": "15.01.2027 21:00:00",
                        "CrDate": "16.01.2027 21:00:00",
                        "Requirements": [{"Id": 20, "MarketingTitle": "Feature 20"}],
                    },
                ],
            }],
        }],
    }]


def test_build_json_report_counts_requirements_and_release_problems():
    report = build_json_report(_roadmap())
    report_2026 = report["years"]["2026"]
    report_2027 = report["years"]["2027"]

    assert report_2026["requirements"] == {
        "unique": 2,
        "occurrences": 2,
        "reused": 0,
        "duplicate_occurrences": 0,
    }
    assert report_2026["releases"] == {
        "total": 2,
        "with_problems": 2,
        "missing_crdate": 2,
        "invalid_crdate": 0,
        "invalid_trdate": 0,
        "missing_app_title": 0,
        "empty_requirements": 1,
    }
    assert report_2026["release_problems"][0]["codes"] == ["missing_crdate"]
    assert report_2026["release_problems"][0]["tfs_url"] == "https://tfs.example/releases/1"
    assert report_2026["release_problems"][1]["codes"] == ["missing_crdate", "empty_requirements"]
    assert report_2027["releases"]["total"] == 1
    assert report_2027["requirements"]["unique"] == 1
    assert report_2027["release_problems"] == []
    assert report["english_name_issues"] == []


def test_build_json_report_finds_english_name_terms_as_whole_words_everywhere():
    roadmap = _roadmap()
    requirements = roadmap[0]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"]
    requirements[0].update({
        "MarketingTitle": "Яндекс ФСБ",
        "MarketingTitleEn": "фстек ФСТЭК FSTEC fsb ФСБ СБЕР sber YANDEX Яндекс ASTRA Астра",
    })
    requirements[1]["MarketingTitleEn"] = "myYandexCloud Astraware"
    # Same ReqId in a separate release occurrence remains a separate report row,
    # even if its release date is outside the annual report tabs.
    roadmap[0]["Streams"][0]["Tiers"][0]["Releases"].append({
        "Id": 99,
        "Title": "Unscheduled release",
        "TrDate": "not-a-date",
        "Requirements": [{"Id": 10, "MarketingTitleEn": "A Yandex.Cloud integration"}],
    })

    issues = build_json_report(roadmap)["english_name_issues"]

    assert len(issues) == 2
    assert issues[0]["requirement_id"] == "10"
    assert issues[0]["matched_terms"] == [
        "фстек", "ФСТЭК", "FSTEC", "fsb", "ФСБ", "СБЕР", "sber",
        "YANDEX", "Яндекс", "ASTRA", "Астра",
    ]
    assert issues[0]["product"] == "Product A"
    assert issues[0]["release_title"] == "Release one"
    assert issues[1]["requirement_id"] == "10"
    assert issues[1]["release_id"] == 99
    assert issues[1]["matched_terms"] == ["Yandex"]


def test_build_json_report_ignores_non_string_english_titles():
    roadmap = _roadmap()
    requirements = roadmap[0]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"]
    requirements[0]["MarketingTitleEn"] = None
    requirements[1]["MarketingTitleEn"] = 123

    assert build_json_report(roadmap)["english_name_issues"] == []


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
    assert report["years"]["2026"]["releases"]["total"] == 1
    assert report["years"]["2026"]["requirements"]["unique"] == 3
    assert report["years"]["2027"]["releases"]["total"] == 0
    assert report["english_name_issues"][0]["matched_terms"] == ["Yandex"]
