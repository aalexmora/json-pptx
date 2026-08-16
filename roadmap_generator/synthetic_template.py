"""Генерация синтетического шаблона разработки (ТЗ v4 §12).

Создаёт `.pptx` с textbox'ом на каждое имя из `config/template_contracts.yaml`,
чтобы шаблон заведомо удовлетворял контракту. Используется до появления
финального размеченного дизайн-шаблона.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from roadmap_generator.template_registry import load_contracts

SYNTHETIC_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "synthetic_template.pptx"
)


def make_synthetic_template(path) -> None:
    contracts = load_contracts()
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


def ensure_synthetic_template(path=None) -> Path:
    """Генерирует синтетический шаблон, если его ещё нет. Возвращает путь."""
    path = Path(path) if path else SYNTHETIC_TEMPLATE_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        make_synthetic_template(path)
    return path
