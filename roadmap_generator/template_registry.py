"""Реестр шаблонов и валидация именованных шейпов.

Состав обязательных шейпов читается из `config/template_contracts.yaml` (данные,
не код — ТЗ v4 раздел 10). Никаких хардкодов имён шейпов в `.py`.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import pptx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_PATH = PROJECT_ROOT / "config" / "template_contracts.yaml"
MAPPING_PATH = PROJECT_ROOT / "config" / "template_mapping.yaml"


def load_contracts() -> dict:
    """Читает состав обязательных именованных шейпов из `template_contracts.yaml`."""
    with open(CONTRACTS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_required_shapes(slide_type: str, columns_count: int, grouped_by_apptitle: bool) -> List[str]:
    """Обязательные шейпы для комбинации `columns_count × grouped`.

    `slide_type` (`roadmap`/`roadmap_cont`) принят для fidelity сигнатуры, но оба
    типа делят один и тот же контракт разметки roadmap-слайда.
    """
    contracts = load_contracts()
    grouping = "grouped" if grouped_by_apptitle else "flat"
    key = f"columns_{columns_count}_{grouping}"
    return list(contracts["roadmap"][key])


def validate_template_shapes(template_path: str, required_shape_names: List[str]) -> List[str]:
    """Проверяет наличие обязательных именованных шейпов в `.pptx`.

    Возвращает список отсутствующих; пустой список = шаблон валиден.
    """
    prs = pptx.Presentation(template_path)
    present: set = set()
    for slide in prs.slides:
        for shape in slide.shapes:
            present.add(shape.name)
    return [name for name in required_shape_names if name not in present]


def select_template(slide_type: str, columns_count: int, grouped_by_apptitle: bool) -> str:
    """Возвращает путь к `.pptx`-шаблону согласно таблице маппинга.

    `columns_count`/`grouped_by_apptitle` приняты для fidelity сигнатуры; выбор
    файла по ним включается, когда таблица станет гранулярной (ТЗ v4 §7.1).
    """
    mapping = _load_mapping()
    if slide_type not in mapping:
        raise KeyError(f"нет шаблона для slide_type='{slide_type}'")
    path = Path(mapping[slide_type])
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


def _load_mapping() -> dict:
    with open(MAPPING_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
