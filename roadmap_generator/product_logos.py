"""Библиотека логотипов продуктов и тиров.

Файлы лежат на диске в `data/img/{product|tier}/logo/{slug}.png` и раздаются по
URL `/img/{product|tier}/logo/{slug}.png` (см. app.py — `IMG_DIR` смонтирован как
`/img`). Ключ лого = слаг канонического имени (продукта или тира) из дерева
(нормализация: нижний регистр, не-буквы/цифры → дефис).

Маппинг «имя → лого» задаётся самим именем файла: загрузили лого для продукта
«Kaspersky SD-WAN» → `product/logo/sd-wan.png` → билдер подставит его в плейсхолдер
`logo`/`_logo`; для тира «Kaspersky Next XDR Expert» → `tier/logo/kaspersky-next-xdr-expert.png`
→ плейсхолдер `logo_tier`/`_logo_tier`. Лого не обязательны: нет файла — плейсхолдер
просто копируется как в шаблоне.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

from cairosvg import svg2png

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = PROJECT_ROOT / "data" / "img"
LOGO_DIR = IMG_DIR / "product" / "logo"          # продукт (обратная совместимость)
TIER_LOGO_DIR = IMG_DIR / "tier" / "logo"        # тир

# Форматы, которые python-pptx может вставить напрямую. Загруженный SVG сначала
# безопасно растрируется в PNG, поэтому на диске хранятся только эти форматы.
LOGO_EXTS = (".png", ".jpg", ".jpeg", ".webp")
UPLOAD_EXTS = LOGO_EXTS + (".svg",)


def prepare_logo_upload(data: bytes, ext: str) -> Tuple[bytes, str]:
    """Проверяет формат и преобразует SVG в PNG для вставки через python-pptx."""
    normalized_ext = "." + ext.lstrip(".").lower()
    if normalized_ext not in UPLOAD_EXTS:
        allowed = ", ".join(UPLOAD_EXTS)
        raise ValueError(f"Неподдерживаемый формат логотипа. Допустимы: {allowed}")
    if not data:
        raise ValueError("Файл логотипа пуст")
    if normalized_ext != ".svg":
        return data, normalized_ext.lstrip(".")
    try:
        png = svg2png(bytestring=data, output_width=1600, unsafe=False)
    except Exception as exc:
        raise ValueError("Не удалось прочитать SVG-файл") from exc
    return png, "png"


def slugify(name: str) -> str:
    """Слаг канонического имени (продукта/тира) для имени файла лого."""
    s = unicodedata.normalize("NFKD", name or "").strip().lower()
    s = re.sub(r"[^\w\-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "logo"


# ---------------------------------------------------------------------------
# Общая логика (папка лого → файл/URL/статус)
# ---------------------------------------------------------------------------

def _save_logo(logo_dir: Path, name: str, data: bytes, ext: str = "png") -> str:
    logo_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(name)
    ext = ext.lstrip(".").lower()
    for old in logo_dir.glob(f"{slug}.*"):
        if old.suffix.lower() in LOGO_EXTS:
            old.unlink(missing_ok=True)
    filename = f"{slug}.{ext}"
    (logo_dir / filename).write_bytes(data)
    return filename


def _delete_logo(logo_dir: Path, name: str) -> bool:
    slug = slugify(name)
    removed = False
    for old in logo_dir.glob(f"{slug}.*"):
        if old.suffix.lower() in LOGO_EXTS:
            old.unlink(missing_ok=True)
            removed = True
    return removed


def _logo_path(logo_dir: Path, name: str) -> Optional[Path]:
    slug = slugify(name)
    for p in logo_dir.glob(f"{slug}.*"):
        if p.suffix.lower() in LOGO_EXTS:
            return p
    return None


def _logo_url(logo_dir: Path, url_prefix: str, name: str) -> Optional[str]:
    path = _logo_path(logo_dir, name)
    if not path:
        return None
    return f"{url_prefix}/{path.name}"


def _status(logo_dir: Path, url_prefix: str, names: List[str]) -> dict:
    return {
        name: ({"has_logo": True, "url": _logo_url(logo_dir, url_prefix, name)}
               if _logo_path(logo_dir, name) else {"has_logo": False, "url": None})
        for name in names
    }


def _list_all(logo_dir: Path, url_prefix: str) -> List[dict]:
    if not logo_dir.exists():
        return []
    return [
        {"filename": p.name, "url": f"{url_prefix}/{p.name}"}
        for p in sorted(logo_dir.iterdir())
        if p.is_file() and p.suffix.lower() in LOGO_EXTS
    ]


def _reset(logo_dir: Path) -> None:
    if logo_dir.exists():
        for p in logo_dir.iterdir():
            if p.is_file() and p.suffix.lower() in LOGO_EXTS:
                p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Логотипы продуктов
# ---------------------------------------------------------------------------

def save_logo(product_name: str, data: bytes, ext: str = "png") -> str:
    """Сохраняет лого продукта, удаляя предыдущие варианты с тем же слагом."""
    return _save_logo(LOGO_DIR, product_name, data, ext)


def delete_logo(product_name: str) -> bool:
    return _delete_logo(LOGO_DIR, product_name)


def logo_path(product_name: str) -> Optional[Path]:
    return _logo_path(LOGO_DIR, product_name)


def logo_url(product_name: str) -> Optional[str]:
    return _logo_url(LOGO_DIR, "/img/product/logo", product_name)


def status(products: List[str]) -> dict:
    return _status(LOGO_DIR, "/img/product/logo", products)


def list_all() -> List[dict]:
    return _list_all(LOGO_DIR, "/img/product/logo")


# ---------------------------------------------------------------------------
# Логотипы тиров
# ---------------------------------------------------------------------------

def save_tier_logo(tier_name: str, data: bytes, ext: str = "png") -> str:
    """Сохраняет лого тира, удаляя предыдущие варианты с тем же слагом."""
    return _save_logo(TIER_LOGO_DIR, tier_name, data, ext)


def delete_tier_logo(tier_name: str) -> bool:
    return _delete_logo(TIER_LOGO_DIR, tier_name)


def tier_logo_path(tier_name: str) -> Optional[Path]:
    return _logo_path(TIER_LOGO_DIR, tier_name)


def tier_logo_url(tier_name: str) -> Optional[str]:
    return _logo_url(TIER_LOGO_DIR, "/img/tier/logo", tier_name)


def tier_status(tiers: List[str]) -> dict:
    return _status(TIER_LOGO_DIR, "/img/tier/logo", tiers)


def list_tier_logos() -> List[dict]:
    return _list_all(TIER_LOGO_DIR, "/img/tier/logo")


# ---------------------------------------------------------------------------
# Сброс (для тестов)
# ---------------------------------------------------------------------------

def reset_logo_state() -> None:
    """Сбрасывает библиотеки лого продуктов и тиров."""
    _reset(LOGO_DIR)
    _reset(TIER_LOGO_DIR)
