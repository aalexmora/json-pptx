"""Missing marketing labels use the technical Title and remain visible errors."""
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from pptx import Presentation
import pytest

from app import app
from roadmap_generator.schema import normalize_roadmap, validate_roadmap

SOFFICE = os.environ.get("SOFFICE_PATH") or shutil.which("soffice")
PDFTOTEXT = os.environ.get("PDFTOTEXT_PATH") or shutil.which("pdftotext")


MISSING = object()


def roadmap(requirement):
    return [{"Product": "P", "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
        "Id": 100, "Title": "Release R", "AppTitle": "App A",
        "TrDate": "15.04.2026 21:00:00", "CrDate": "15.04.2026 21:00:00",
        "Requirements": [requirement],
    }]}]}]}]


def requirement(**changes):
    return {"Id": 10, "Title": "[BRQ] Technical requirement", "Kbr": "Yes",
            "MarketingTitle": "Public RU", "MarketingTitleEn": "Public EN", **changes}


@pytest.mark.parametrize("language,field,attribute", [
    ("ru", "MarketingTitle", "marketing_title"),
    ("en", "MarketingTitleEn", "marketing_title_en"),
])
@pytest.mark.parametrize("value", [pytest.param(MISSING, id="absent"), None, "", " \t\n", 17])
def test_missing_marketing_title_uses_title_with_nonblocking_error(language, field, attribute, value):
    raw = requirement()
    if value is MISSING:
        raw.pop(field)
    else:
        raw[field] = value
    data = roadmap(raw)

    assert validate_roadmap(data) == []
    model = normalize_roadmap(data, language)
    normalized = model.products[0].streams[0].tiers[0].releases[0].requirements
    assert len(normalized) == 1
    assert getattr(normalized[0], attribute) == "[BRQ] Technical requirement"
    assert len(model.quality_issues) == 1
    issue = model.quality_issues[0]
    assert issue["code"] == "missing_marketing_title"
    assert issue["severity"] == "error"
    assert issue["requirement_id"] == 10
    assert issue["requirement_title"] == "[BRQ] Technical requirement"
    assert issue["release_id"] == 100
    assert issue["language"] == language
    assert issue["field"] == field
    assert field in issue["message"] and "Title" in issue["message"]


@pytest.mark.parametrize("language,attribute,expected", [
    ("ru", "marketing_title", "Public RU"), ("en", "marketing_title_en", "Public EN"),
])
def test_present_marketing_title_is_preserved(language, attribute, expected):
    model = normalize_roadmap(roadmap(requirement()), language)
    normalized = model.products[0].streams[0].tiers[0].releases[0].requirements[0]
    assert getattr(normalized, attribute) == expected
    assert model.quality_issues == []


def test_fallback_does_not_admit_requirement_hidden_for_selected_language():
    model = normalize_roadmap(roadmap(requirement(Visibility="Only RU", MarketingTitleEn=None)), "en")
    assert model.products[0].streams[0].tiers[0].releases[0].requirements == []
    assert model.quality_issues == []


def test_missing_en_title_and_missing_fallback_are_reported_without_blank_bullet():
    model = normalize_roadmap(roadmap(requirement(Title=None, MarketingTitleEn=None)), "en")
    assert model.products[0].streams[0].tiers[0].releases[0].requirements == []
    issue = model.quality_issues[0]
    assert issue["code"] == "missing_marketing_title" and issue["severity"] == "error"
    assert issue["requirement_id"] == 10
    assert "Title" in issue["message"]


@pytest.mark.parametrize("language", ["ru", "en"])
def test_plan_and_pptx_include_title_when_both_marketing_fields_are_null(language):
    data = roadmap(requirement(MarketingTitle=None, MarketingTitleEn=None))
    with TestClient(app) as client:
        plan = client.post("/api/plan", json={"json_data": data, "language": language}).json()
        assert plan["errors"] == []
        assert plan["plan"] is not None
        assert any(issue["requirement_id"] == 10 and issue["language"] == language
                   for issue in plan["quality_issues"] if issue["code"] == "missing_marketing_title")
        response = client.post("/api/pptx", json={"json_data": data, "language": language})
    assert response.status_code == 200
    presentation = Presentation(BytesIO(response.content))
    text = "\n".join(shape.text for slide in presentation.slides for shape in slide.shapes if shape.has_text_frame)
    assert "[BRQ] Technical requirement" in text


@pytest.mark.skipif(not (SOFFICE and PDFTOTEXT), reason="LibreOffice and Poppler are needed for rendered slide QA")
@pytest.mark.parametrize("language", ["ru", "en"])
def test_synthetic_template_keeps_fallback_and_following_features_above_footer(tmp_path, monkeypatch, language):
    import roadmap_generator.builder as builder
    from roadmap_generator.plugins_engine import build_slide_plan
    from roadmap_generator.synthetic_template import make_synthetic_template

    template = tmp_path / "template.pptx"
    make_synthetic_template(template)
    monkeypatch.setattr(builder, "select_template", lambda *args, **kwargs: str(template))
    titles = [
        "Support automatic processing of alerts and incidents through external scripts",
        "Improve loading and transitions in the application user interface",
        "Provide an updated package of threat detection content",
        "Coordinate endpoint agents and the response server for shared installations",
        "Configure which notifications are displayed for individual users",
        "Playbooks that combine multiple response actions in the same workflow",
        "Allow formatted comments and extended descriptions for events and related incidents",
        "Manage certificates used by agents when connecting securely to application servers",
    ]
    requirements = []
    for index, title in enumerate(titles):
        text = title + f" EndMarker{index}"
        requirements.append(requirement(Id=index + 1, Title=text, MarketingTitle=text, MarketingTitleEn=text))
    requirements[3]["MarketingTitle"] = requirements[3]["MarketingTitleEn"] = None
    data = roadmap(requirements[0])
    data[0]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"] = requirements
    presentation = builder.build_presentation(build_slide_plan(normalize_roadmap(data, language), {}))
    pptx = tmp_path / "fallback.pptx"
    presentation.save(pptx)
    env = dict(os.environ, XDG_CACHE_HOME=str(tmp_path / "cache"))
    env.pop("DYLD_FALLBACK_LIBRARY_PATH", None)
    conversion = subprocess.run([SOFFICE, "-env:UserInstallation=" + (tmp_path / "lo-profile").as_uri(),
        "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(pptx)],
        env=env, text=True, capture_output=True, check=True, timeout=60)
    pdf = tmp_path / "fallback.pdf"
    assert pdf.is_file(), conversion.stdout + conversion.stderr
    bbox = tmp_path / "words.html"
    subprocess.run([PDFTOTEXT, "-bbox", str(pdf), str(bbox)], env=env, check=True, timeout=30)
    markers = {word.text: float(word.attrib["yMax"]) for word in ET.parse(bbox).iter()
               if word.tag.endswith("}word") and (word.text or "").startswith("EndMarker")}
    assert set(markers) == {f"EndMarker{i}" for i in range(8)}, markers
    assert all(bottom < 504 for bottom in markers.values()), markers  # Footnotes start at 7 inches.
