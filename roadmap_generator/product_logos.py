"""Библиотека PNG-фонов продуктовых слайдов и логотипов тиров.

Фон Product-слайда хранится в `data/img/product/slide/{slug}.png` и подставляется
в `product_slide_image`/`_product_slide_image`. Логотип тира хранится в
`data/img/tier/logo/{slug}.*` и подставляется в `tier_logo`/`_tier_logo`.
`data/img/product/logo` и связанные функции оставлены только для обратной
совместимости API: генератор больше не использует эти логотипы на roadmap-слайдах.
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
PRODUCT_SLIDE_DIR = IMG_DIR / "product" / "slide" # PNG-фон Product-слайда
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


def prepare_product_slide_upload(data: bytes, ext: str) -> Tuple[bytes, str]:
    """Принимает только PNG-фон для продуктового слайда-заглушки."""
    normalized_ext = "." + ext.lstrip(".").lower()
    if normalized_ext != ".png":
        raise ValueError("Фон продуктового слайда должен быть в формате PNG")
    if not data:
        raise ValueError("Файл фона пуст")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Не удалось прочитать PNG-файл")
    return data, "png"


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
# PNG-фоны Product-слайдов-заглушек
# ---------------------------------------------------------------------------

def save_product_slide_image(product_name: str, data: bytes, ext: str = "png") -> str:
    return _save_logo(PRODUCT_SLIDE_DIR, product_name, data, ext)


def delete_product_slide_image(product_name: str) -> bool:
    return _delete_logo(PRODUCT_SLIDE_DIR, product_name)


def product_slide_image_path(product_name: str) -> Optional[Path]:
    return _logo_path(PRODUCT_SLIDE_DIR, product_name)


def product_slide_image_url(product_name: str) -> Optional[str]:
    return _logo_url(PRODUCT_SLIDE_DIR, "/img/product/slide", product_name)


def product_slide_status(products: List[str]) -> dict:
    return _status(PRODUCT_SLIDE_DIR, "/img/product/slide", products)


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


def tier_logo_key(product_name: str, tier_name: str) -> str:
    """Ключ библиотеки: Tier для Next/Symphony, иначе Product."""
    normalized_product = " ".join((product_name or "").casefold().split())
    is_next_family = normalized_product in {"next", "kaspersky next"}
    is_symphony_family = (
        normalized_product == "symphony"
        or normalized_product.startswith("kaspersky symphony")
    )
    if is_next_family or is_symphony_family:
        return tier_name
    return product_name


# ---------------------------------------------------------------------------
# Сброс (для тестов)
# ---------------------------------------------------------------------------

def reset_logo_state() -> None:
    """Сбрасывает библиотеки лого продуктов и тиров."""
    _reset(LOGO_DIR)
    _reset(PRODUCT_SLIDE_DIR)
    _reset(TIER_LOGO_DIR)
