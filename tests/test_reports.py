from __future__ import annotations

import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app import app
from roadmap_generator.reports import analyze_public_features_xlsx, build_json_report


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


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


def test_analyze_public_features_xlsx_maps_public_features_by_req_id():
    data = _xlsx_bytes([
        ["Application", "Requirement", "ReqId", "IsPublished"],
        ["Product A", "Mapped", 10, True],
        ["Product A", "Not mapped", 30, "true"],
        ["Product B", "Not public", 40, False],
        ["Product B", "Same missing feature", 30, 1],
    ])

    report = analyze_public_features_xlsx(data, _roadmap(), "features.xlsx")

    assert report["filename"] == "features.xlsx"
    assert report["public_features"] == 2
    assert report["mapped_public_features"] == 1
    assert report["unmapped_public_features"] == 1
    assert report["mapped_percent"] == 50.0
    assert [product["product"] for product in report["products"]] == ["Product A", "Product B"]
    assert report["products"][0]["requirements"] == [{"req_id": "30", "title": "Not mapped"}]


def test_analyze_public_features_xlsx_requires_columns():
    data = _xlsx_bytes([
        ["Application", "Requirement", "ReqId"],
        ["Product A", "Feature", 10],
    ])

    with pytest.raises(ValueError, match="ReqId и IsPublished"):
        analyze_public_features_xlsx(data, _roadmap())


def test_public_features_report_endpoint():
    data = _xlsx_bytes([
        ["Application", "Requirement", "ReqId", "IsPublished"],
        ["Product A", "Mapped", 10, True],
        ["Product A", "Not mapped", 30, True],
    ])

    with TestClient(app) as client:
        response = client.post(
            "/api/reports/public-features",
            data={"json_data": json.dumps(_roadmap())},
            files={
                "file": (
                    "features.xlsx",
                    data,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
            },
        )

    assert response.status_code == 200
    assert response.json()["unmapped_public_features"] == 1


def test_public_features_report_endpoint_rejects_non_xlsx():
    with TestClient(app) as client:
        response = client.post(
            "/api/reports/public-features",
            data={"json_data": json.dumps(_roadmap())},
            files={"file": ("features.csv", b"ReqId,IsPublished\n10,true", "text/csv")},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Отчёт должен быть в формате XLSX"
