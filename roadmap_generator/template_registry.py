"""Реестр шаблонов и валидация именованных шейпов.

Состав обязательных шейпов читается из `config/template_contracts.yaml` (данные,
не код — ТЗ v4 раздел 10). Никаких хардкодов имён шейпов в `.py`.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import pptx
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_PATH = PROJECT_ROOT / "config" / "template_contracts.yaml"
MAPPING_PATH = PROJECT_ROOT / "config" / "template_mapping.yaml"
TEMPLATES_LIBRARY = PROJECT_ROOT / "templates_library"
ACTIVE_TEMPLATE_FILE = PROJECT_ROOT / "data" / "active_template.txt"


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
    """Возвращает путь к `.pptx`-шаблону: активный (загруженный) или дефолт из маппинга."""
    active = get_active_template_path()
    if active:
        return active
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


def _soffice() -> Optional[str]:
    return shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"


def _all_required_shapes() -> List[str]:
    contracts = load_contracts()
    names: List[str] = []
    for value in contracts.get("roadmap", {}).values():
        for name in value:
            if name not in names:
                names.append(name)
    return names


def save_template(filename: str, data: bytes) -> dict:
    """Сохраняет загруженный шаблон, валидирует и генерирует PNG-превью первого слайда."""
    TEMPLATES_LIBRARY.mkdir(parents=True, exist_ok=True)
    path = TEMPLATES_LIBRARY / filename
    path.write_bytes(data)

    missing = validate_template_shapes(str(path), _all_required_shapes())
    preview = generate_preview(filename)
    return {
        "filename": filename,
        "missing_shapes": missing,
        "valid": not missing,
        "preview": preview,
    }


def generate_preview(filename: str) -> Optional[str]:
    """Генерирует JPEG первого слайда через soffice + pdftoppm. Возвращает путь или None."""
    path = TEMPLATES_LIBRARY / filename
    if not path.exists():
        return None
    soffice = _soffice()
    if not soffice or not shutil.which("pdftoppm"):
        return None

    out_dir = TEMPLATES_LIBRARY / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(path)],
            check=False, capture_output=True, timeout=120,
        )
        pdf = Path(tmp) / f"{stem}.pdf"
        if not pdf.exists():
            return None
        subprocess.run(
            ["pdftoppm", "-jpeg", "-r", "90", "-f", "1", "-l", "1", str(pdf), str(out_dir / stem)],
            check=False, capture_output=True, timeout=120,
        )
    jpg = out_dir / f"{stem}-1.jpg"
    return str(jpg) if jpg.exists() else None


def preview_path(filename: str) -> Optional[str]:
    jpg = TEMPLATES_LIBRARY / "previews" / f"{Path(filename).stem}-1.jpg"
    return str(jpg) if jpg.exists() else None


def list_templates() -> List[dict]:
    """Список загруженных шаблонов с валидацией и превью."""
    result: List[dict] = []
    for path in sorted(TEMPLATES_LIBRARY.glob("*.pptx")):
        missing = validate_template_shapes(str(path), _all_required_shapes())
        result.append({
            "filename": path.name,
            "missing_shapes": missing,
            "valid": not missing,
            "preview": preview_path(path.name),
            "active": get_active_template_path() == str(path),
        })
    return result


def set_active_template(filename: Optional[str]) -> None:
    if filename:
        ACTIVE_TEMPLATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_TEMPLATE_FILE.write_text(filename, encoding="utf-8")
    else:
        ACTIVE_TEMPLATE_FILE.unlink(missing_ok=True)


def get_active_template_path() -> Optional[str]:
    if ACTIVE_TEMPLATE_FILE.exists():
        filename = ACTIVE_TEMPLATE_FILE.read_text(encoding="utf-8").strip()
        path = TEMPLATES_LIBRARY / filename
        if path.exists():
            return str(path)
    return None


def _reset_template_state() -> None:
    ACTIVE_TEMPLATE_FILE.unlink(missing_ok=True)
