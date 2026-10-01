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
                ],
            }],
        }],
    }]


def test_build_json_report_counts_requirements_and_release_problems():
    report = build_json_report(_roadmap())

    assert report["requirements"] == {
        "unique": 2,
        "occurrences": 3,
        "reused": 1,
        "duplicate_occurrences": 1,
    }
    assert report["releases"] == {
        "total": 3,
        "with_problems": 3,
        "missing_crdate": 2,
        "invalid_crdate": 0,
        "invalid_trdate": 1,
        "missing_app_title": 1,
        "empty_requirements": 1,
    }
    assert report["release_problems"][0]["codes"] == ["missing_crdate"]
    assert report["release_problems"][2]["codes"] == ["missing_crdate", "empty_requirements"]


def test_analyze_public_features_csv_maps_public_features_by_req_id():
    data = _csv_bytes([
        ["Application", "Requirement", "ReqId", "IsPublished"],
        ["Продукт А", "Есть в JSON", 10, True],
        ["Продукт А", "Не замаплено", 30, "true"],
        ["Продукт Б", "Не публично", 40, False],
        ["Продукт Б", "Та же отсутствующая фича", 30, 1],
    ])

    report = analyze_public_features_csv(data, _roadmap(), "features.csv")

    assert report["filename"] == "features.csv"
    assert report["public_features"] == 2
    assert report["mapped_public_features"] == 1
    assert report["unmapped_public_features"] == 1
    assert report["mapped_percent"] == 50.0
    assert [product["product"] for product in report["products"]] == ["Продукт А", "Продукт Б"]
    assert report["products"][0]["requirements"] == [{"req_id": "30", "title": "Не замаплено"}]


def test_analyze_public_features_csv_supports_semicolon_and_prefers_application():
    data = _csv_bytes([
        ["Product", "Application", "Requirement", "ReqId", "IsPublished"],
        ["Линейка", "Приложение", "Фича", 30, True],
    ], delimiter=";", encoding="cp1251")

    report = analyze_public_features_csv(data, _roadmap(), "features.csv")

    assert report["products"][0]["product"] == "Приложение"


def test_analyze_public_features_csv_requires_columns():
    data = _csv_bytes([
        ["Application", "Requirement", "ReqId"],
        ["Product A", "Feature", 10],
    ])

    with pytest.raises(ValueError, match="ReqId и IsPublished"):
        analyze_public_features_csv(data, _roadmap())


def test_public_features_report_endpoint():
    data = _csv_bytes([
        ["Application", "Requirement", "ReqId", "IsPublished"],
        ["Product A", "Mapped", 10, True],
        ["Product A", "Not mapped", 30, True],
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
        ["Application", "Requirement", "ReqId", "IsPublished"],
        ["Product A", "Mapped", 10, True],
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
