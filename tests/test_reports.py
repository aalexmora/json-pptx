from __future__ import annotations

import csv
import json
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from app import app
from roadmap_generator.reports import analyze_public_features_csv, build_json_report


def _csv_bytes(
    rows: list[list[object]],
    *,
    delimiter: str = "\t",
    encoding: str = "utf-8-sig",
) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter)
    for row in rows:
        writer.writerow(row)
    return output.getvalue().encode(encoding)


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


def test_analyze_public_features_csv_maps_public_features_by_req_id():
    data = _csv_bytes([
        ["Application", "Requirement", "ReqId", "IsPublished", "ApplicableForProducts"],
        ["Продукт А", "Есть в JSON", 10, True, "Product A"],
        ["Продукт А", "Не замаплено", 30, "true", "Product A"],
        ["Продукт Б", "Не публично", 40, False, "Product B"],
        ["Продукт Б", "Та же отсутствующая фича", 30, 1, "Product B"],
    ])

    report = analyze_public_features_csv(data, _roadmap(), "features.csv")

    assert report["filename"] == "features.csv"
    assert report["public_features"] == 2
    assert report["mapped_public_features"] == 1
    assert report["unmapped_public_features"] == 1
    assert report["mapped_percent"] == 50.0
    assert [product["product"] for product in report["products"]] == ["Продукт А", "Продукт Б"]
    assert report["products"][0]["requirements"] == [{"req_id": "30", "title": "Не замаплено"}]
    assert report["complete_products_by_year"] == {"2026": [], "2027": []}


def test_analyze_public_features_csv_supports_semicolon_and_prefers_application():
    data = _csv_bytes([
        ["Product", "Application", "Requirement", "ReqId", "IsPublished", "ApplicableForProducts"],
        ["Линейка", "Приложение", "Фича", 30, True, "Product A"],
    ], delimiter=";", encoding="cp1251")

    report = analyze_public_features_csv(data, _roadmap(), "features.csv")

    assert report["products"][0]["product"] == "Приложение"


def test_analyze_public_features_csv_requires_columns():
    data = _csv_bytes([
        ["Application", "Requirement", "ReqId"],
        ["Product A", "Feature", 10],
    ])

    with pytest.raises(ValueError, match="ApplicableForProducts"):
        analyze_public_features_csv(data, _roadmap())


def test_complete_products_are_calculated_per_trdate_year():
    data = _csv_bytes([
        ["ReqId", "IsPublished", "ApplicableForProducts"],
        [10, True, "Product A"],
        [20, True, "Product A"],
    ])

    report = analyze_public_features_csv(data, _roadmap(), "features.csv")

    assert report["complete_products_by_year"] == {
        "2026": [],
        "2027": ["Product A"],
    }


def test_public_features_report_endpoint():
    data = _csv_bytes([
        ["Application", "Requirement", "ReqId", "IsPublished", "ApplicableForProducts"],
        ["Product A", "Mapped", 10, True, "Product A"],
        ["Product A", "Not mapped", 30, True, "Product A"],
    ])

    with TestClient(app) as client:
        response = client.post(
            "/api/reports/public-features",
            files={
                "json_file": (
                    "roadmap.json",
                    json.dumps(_roadmap()).encode("utf-8"),
                    "application/json",
                ),
                "file": (
                    "features.csv",
                    data,
                    "text/tab-separated-values",
                ),
            },
        )

    assert response.status_code == 200
    assert response.json()["unmapped_public_features"] == 1


def test_public_features_report_endpoint_accepts_json_larger_than_one_mb():
    roadmap = _roadmap()
    roadmap[0]["unused_large_field"] = "я" * 600_000
    data = _csv_bytes([
        ["Application", "Requirement", "ReqId", "IsPublished", "ApplicableForProducts"],
        ["Product A", "Mapped", 10, True, "Product A"],
    ])

    with TestClient(app) as client:
        response = client.post(
            "/api/reports/public-features",
            files={
                "json_file": (
                    "roadmap.json",
                    json.dumps(roadmap).encode("utf-8"),
                    "application/json",
                ),
                "file": ("features.csv", data, "text/tab-separated-values"),
            },
        )

    assert response.status_code == 200
    assert response.json()["mapped_public_features"] == 1


def test_public_features_report_endpoint_rejects_non_csv():
    with TestClient(app) as client:
        response = client.post(
            "/api/reports/public-features",
            files={
                "json_file": (
                    "roadmap.json",
                    json.dumps(_roadmap()).encode("utf-8"),
                    "application/json",
                ),
                "file": ("features.xlsx", b"not xlsx", "application/octet-stream"),
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Отчёт должен быть в формате CSV"
