#!/usr/bin/env python3
"""Exercise the real API inside a disposable container; standard library only."""
import argparse
import io
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile


def request(path, payload=None, status=200):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request("http://127.0.0.1:8000" + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        assert response.status == status, (path, response.status, body[:500])
        return body, response.headers


def api(path, payload=None, status=200):
    return json.loads(request(path, payload, status)[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("fresh", "persist"))
    parser.add_argument("version")
    parser.add_argument("marker")
    args = parser.parse_args()
    fixtures = Path(__file__).resolve().parent
    health = {"status": "ok", "version": args.version}
    assert api("/api/health") == health
    assert json.loads((fixtures / "published-health.json").read_text()) == health
    html, headers = request("/")
    assert "text/html" in headers["Content-Type"]
    assets = re.findall(r'(?:src|href)="(/assets/[^"?]+)"', html.decode())
    assert assets, "Built frontend assets missing"
    for asset in assets:
        content, _ = request(asset)
        assert content, asset

    profile = api("/api/profile")
    marker_path = Path("/app/templates_library/.container-smoke-marker")
    if args.mode == "persist":
        assert profile["deck_meta"]["title"] == args.marker, "Profile did not persist"
        assert marker_path.read_text() == args.marker, "Template volume did not persist"
        print("Persistence after recreation: OK")
        return

    assert not marker_path.exists(), "Expected empty disposable template volume"
    for language, fixture in (("ru", "pagination_5_quarters.json"), ("en", "en_with_content.json")):
        payload = {"json_data": json.loads((fixtures / fixture).read_text()), "language": language}
        plan = api("/api/plan", payload)
        assert not plan["errors"] and plan["plan"]["slides"], (language, plan)
        content, headers = request("/api/pptx", payload)
        assert headers["Content-Type"].startswith("application/vnd.openxmlformats")
        suffix = "RU" if language == "ru" else "ENG"
        assert f'roadmap_{suffix}.pptx' in headers["Content-Disposition"]
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            assert archive.testzip() is None
            ET.fromstring(archive.read("ppt/presentation.xml"))
            slides = [name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
            assert slides, language
            for name in slides:
                ET.fromstring(archive.read(name))
        print(f"{language.upper()} plan and PPTX: OK")

    invalid = api("/api/plan", {"json_data": []})
    assert invalid["errors"] and invalid["plan"] is None
    assert api("/api/pptx", {"json_data": []}, 422)["detail"]["errors"]
    profile["deck_meta"]["title"] = args.marker
    assert api("/api/profile", profile)["status"] == "ok"
    marker_path.write_text(args.marker)
    print("Validation and state writes: OK")


if __name__ == "__main__":
    main()
