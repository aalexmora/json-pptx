"""Общие фикстуры и хелперы для тестов.

Пути резолвятся относительно расположения этого файла, поэтому тесты работают
независимо от текущей рабочей директории.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import pytest

from roadmap_generator import approval, deck_meta, labels, linter, ordering, product_languages, product_logos, static_slides, strings, template_registry
from roadmap_generator.synthetic_template import make_synthetic_template

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REAL_DATA_PATH = PROJECT_ROOT / "Requirements" / "product-tiers-data.json"


@pytest.fixture(autouse=True)
def _isolate_profile(tmp_path):
    """Персистентность профиля в тестах идёт во временный файл, не в data/profile.json."""
    os.environ["ROADMAP_PROFILE_PATH"] = str(tmp_path / "profile.json")


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    """Сбрасывает состояние тестов, не затрагивая пользовательские логотипы."""
    monkeypatch.setattr(product_logos, "LOGO_DIR", tmp_path / "product-logos")
    monkeypatch.setattr(product_logos, "TIER_LOGO_DIR", tmp_path / "tier-logos")
    ordering._reset_state()
    labels._reset_state()
    linter._reset_state()
    approval._reset_state()
    deck_meta._reset_state()
    strings._reset_state()
    static_slides._reset_state()
    product_languages._reset_state()
    template_registry._reset_template_state()
    product_logos.reset_logo_state()
    yield
    ordering._reset_state()
    labels._reset_state()
    linter._reset_state()
    approval._reset_state()
    deck_meta._reset_state()
    strings._reset_state()
    static_slides._reset_state()
    product_languages._reset_state()
    template_registry._reset_template_state()
    product_logos.reset_logo_state()


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def real_data():
    """Реальный `product-tiers-data.json` — интеграционный smoke-источник."""
    return load_json(REAL_DATA_PATH)


@pytest.fixture(scope="session")
def load_fixture() -> Callable[[str], list]:
    """Загрузчик синтетических фикстур из `tests/fixtures/` по имени файла."""
    def _load(name: str) -> list:
        return load_json(FIXTURES_DIR / name)

    return _load


@pytest.fixture(scope="session")
def synthetic_template_path() -> Path:
    """Путь к синтетическому шаблону (генерируется в `tests/fixtures/`)."""
    path = FIXTURES_DIR / "synthetic_template.pptx"
    make_synthetic_template(path)
    return path
