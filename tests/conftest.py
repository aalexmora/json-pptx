"""Общие фикстуры и хелперы для тестов.

Пути резолвятся относительно расположения этого файла, поэтому тесты работают
независимо от текущей рабочей директории.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest
from pptx import Presentation
from pptx.util import Inches

from roadmap_generator import labels, ordering, template_registry

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
REAL_DATA_PATH = PROJECT_ROOT / "Requirements" / "product-tiers-data.json"


@pytest.fixture(autouse=True)
def _reset_state():
    """Сбрасывает in-memory хранилища ordering/labels между тестами."""
    ordering._reset_state()
    labels._reset_state()
    yield
    ordering._reset_state()
    labels._reset_state()


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


def make_synthetic_template(path: Path) -> None:
    """Генерирует синтетический шаблон разработки (ТЗ v4 §12).

    Создаёт по textbox'у на каждое имя из `template_contracts.yaml` — шаблон
    заведомо удовлетворяет контракту. Используется для тестов этапов 3–4,
    пока нет финального размеченного шаблона.
    """
    contracts = template_registry.load_contracts()
    names: list = []
    for section in ("roadmap", "annotations"):
        for value in contracts.get(section, {}).values():
            for name in value:
                if name not in names:
                    names.append(name)

    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9 widescreen
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    for i, name in enumerate(names):
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3 + i * 0.4), Inches(4.0), Inches(0.3))
        box.name = name
        box.text_frame.text = name
    prs.save(str(path))


@pytest.fixture(scope="session")
def synthetic_template_path() -> Path:
    """Путь к синтетическому шаблону (генерируется в `tests/fixtures/`)."""
    path = FIXTURES_DIR / "synthetic_template.pptx"
    make_synthetic_template(path)
    return path
