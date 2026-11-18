"""Версия образа для Linux-сервера совпадает с версией приложения."""
from __future__ import annotations

import re
from pathlib import Path

from roadmap_generator.version import APP_VERSION

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/aalexmora/json-pptx"


def test_ghcr_compose_pins_current_version():
    compose = (ROOT / "docker-compose.ghcr.yml").read_text(encoding="utf-8")

    assert re.findall(rf"{re.escape(IMAGE)}:([\w.-]+)", compose) == [APP_VERSION]


def test_readme_names_current_version_and_image():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert f"> **Версия:** {APP_VERSION}" in readme
    assert set(re.findall(rf"{re.escape(IMAGE)}:(\d+\.\d+\.\d+)", readme)) == {APP_VERSION}
