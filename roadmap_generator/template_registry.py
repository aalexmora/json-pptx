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
    """Обязательные шейпы шаблона-«конструктора» (одна колонка-прототип).

    `columns_count`/`grouped` приняты для fidelity сигнатуры, но контракт один:
    builder сам клонирует колонку под каждый квартал.
    """
    return list(load_contracts()["roadmap"]["base"])


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


# Понятные дизайнеру подсказки: что за шейп и зачем он нужен
_SHAPE_HINTS = {
    "eyebrow": "маленький ярлык над заголовком («Roadmap») — легаси, лучше назвать roadmap",
    "slide_title": "заголовок слайда — название тира/продукта",
    "col_header": "заголовок квартала (Q1, Q2, …)",
    "col_bullets": "список фич колонки",
    "roadmap": "статичный ярлык «Roadmap» — текст билдер не меняет",
    "logo": "картинка-логотип — билдер подставит лого продукта из библиотеки",
    "dot": "декоративная точка-отсечка квартала",
    "s2c": "сноска Subject to Change — показывается один раз",
    "number": "порядковый номер слайда",
}


def _consulted_shapes() -> List[str]:
    """Все имена шейпов, которые билдер ищет по имени (обязательные + опциональные)."""
    cfg = load_contracts()["roadmap"]
    return list(cfg.get("base", [])) + list(cfg.get("optional", []))


def placeholder_names() -> List[str]:
    """Имена плейсхолдеров + их варианты с префиксом `_` (напр. `_roadmap`).

    Префикс «_» в имени шейпа делает его сервисным/направляющим и он не попадает
    в слайд — КРОМЕ случаев, когда имя после «_» совпадает с плейсхолдером:
    такие шейпы копируются и заполняются билдером.
    """
    return list(_consulted_shapes()) + ["_" + n for n in _consulted_shapes()]


def _normalize_placeholder(name: str) -> str:
    """Сводит `_roadmap` → `roadmap`: префикс «_» не мешает распознаванию плейсхолдера."""
    if name.startswith("_") and name[1:] in _consulted_shapes():
        return name[1:]
    return name


def validate_template_full(template_path: str) -> dict:
    """Проверяет шаблон и возвращает готовые замечания для дизайнера.

    Возвращает:
    - `missing_shapes` — отсутствующие обязательные шейпы;
    - `duplicate_shapes` — имена, встречающиеся больше одного раза;
    - `issues` — человекочитаемые строки-инструкции на русском (что исправить).
    """
    prs = pptx.Presentation(template_path)
    names: List[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            names.append(_normalize_placeholder(shape.name))

    from collections import Counter
    counts = Counter(names)
    required = list(load_contracts()["roadmap"]["base"])
    consulted = _consulted_shapes()

    missing = [name for name in required if counts.get(name, 0) == 0]
    duplicates = sorted(name for name in consulted if counts.get(name, 0) > 1)

    issues: List[str] = []
    if not missing and not duplicates:
        return {"missing_shapes": missing, "duplicate_shapes": duplicates, "issues": issues}

    issues.append(
        "Шаблон не пройдёт автоматическую вёрстку. Исправьте шейпы и загрузите снова. "
        "Переименование: выделить фигуру → «Главная» → «Упорядочить» → «Область выделения» (Alt+F10). "
        "Префикс «_» в начале имени — сервисный шейп (не попадает в слайд), НО если после «_» "
        "стоит имя плейсхолдера (например «_roadmap») — шейп обрабатывается билдером."
    )
    for name in missing:
        hint = _SHAPE_HINTS.get(name, "")
        issues.append(
            f"Нет шейпа «{name}»{(' — ' + hint) if hint else ''}. "
            f"Добавьте его и назовите ровно {name}."
        )
    for name in duplicates:
        hint = _SHAPE_HINTS.get(name, "")
        issues.append(_duplicate_message(name, counts[name], hint))
    return {"missing_shapes": missing, "duplicate_shapes": duplicates, "issues": issues}


def _duplicate_message(name: str, count: int, hint: str) -> str:
    what = f" — это {hint}" if hint else ""
    base = f"Имя «{name}» встречается {count} раза, а нужен ровно один шейп{what}."
    if name == "col_bullets":
        fix = (
            " Оставьте один (прототип со списком фич), а лишние переименуйте: "
            "ярлык-заголовок («Roadmap») → eyebrow, примеры содержания → _sample, "
            "декоративные → _dot."
        )
    elif name == "col_header":
        fix = (
            " Оставьте один (прототип заголовка квартала), а лишние переименуйте: "
            "декоративные → _dot, примеры → _sample."
        )
    else:
        fix = " Оставьте один, лишние переименуйте (например _sample, _dot)."
    return base + fix


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
    return list(load_contracts()["roadmap"]["base"])


def save_template(filename: str, data: bytes) -> dict:
    """Сохраняет загруженный шаблон, валидирует и генерирует PNG-превью первого слайда."""
    TEMPLATES_LIBRARY.mkdir(parents=True, exist_ok=True)
    path = TEMPLATES_LIBRARY / filename
    path.write_bytes(data)

    check = validate_template_full(str(path))
    preview = generate_preview(filename)
    return {
        "filename": filename,
        "missing_shapes": check["missing_shapes"],
        "duplicate_shapes": check["duplicate_shapes"],
        "issues": check["issues"],
        "valid": not check["missing_shapes"] and not check["duplicate_shapes"],
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


def _is_ignored_template(path: Path) -> bool:
    """Пропускает служебные файлы: блокировки PowerPoint (`~$…`) и прочие не-шаблоны."""
    return path.name.startswith("~$") or path.name.startswith(".")


def list_templates() -> List[dict]:
    """Список загруженных шаблонов с валидацией и превью."""
    result: List[dict] = []
    for path in sorted(TEMPLATES_LIBRARY.glob("*.pptx")):
        if _is_ignored_template(path):
            continue
        try:
            check = validate_template_full(str(path))
        except pptx.exc.PackageNotFoundError:
            # повреждённый/не-pptx файл не должен ронять весь список
            check = {
                "missing_shapes": [],
                "duplicate_shapes": [],
                "issues": ["Файл повреждён или не является .pptx — удалите его."],
            }
        result.append({
            "filename": path.name,
            "missing_shapes": check["missing_shapes"],
            "duplicate_shapes": check["duplicate_shapes"],
            "issues": check["issues"],
            "valid": not check["missing_shapes"] and not check["duplicate_shapes"] and not check["issues"],
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


def delete_template(filename: str) -> None:
    """Удаляет шаблон (и его превью); если он активен — сбрасывает активность."""
    path = TEMPLATES_LIBRARY / filename
    if get_active_template_path() == str(path):
        set_active_template(None)
    path.unlink(missing_ok=True)
    (TEMPLATES_LIBRARY / "previews" / f"{Path(filename).stem}-1.jpg").unlink(missing_ok=True)


def get_active_template_path() -> Optional[str]:
    if ACTIVE_TEMPLATE_FILE.exists():
        filename = ACTIVE_TEMPLATE_FILE.read_text(encoding="utf-8").strip()
        path = TEMPLATES_LIBRARY / filename
        if path.exists():
            return str(path)
    return None


def _reset_template_state() -> None:
    ACTIVE_TEMPLATE_FILE.unlink(missing_ok=True)
