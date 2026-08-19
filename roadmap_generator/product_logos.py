"""Библиотека логотипов продуктов.

Файлы лежат на диске в `data/img/product/logo/{slug}.png` и раздаются по URL
`/img/product/logo/{slug}.png`. Ключ лого = слаг канонического имени продукта
из дерева (нормализация: нижний регистр, не-буквы/цифры → дефис).

Маппинг «продукт → лого» задаётся самим именем файла: загрузили лого для
продукта «Kaspersky SD-WAN» → `sd-wan.png` → билдер подставит его в плейсхолдер
`logo`/`_logo` на слайде этого продукта. Лого не обязательны: нет файла —
плейсхолдер просто копируется как в шаблоне.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Монтируется в FastAPI как StaticFiles по адресу /img (см. app.py), поэтому
# файл logo/{slug}.png соответствует URL /img/product/logo/{slug}.png.
IMG_DIR = PROJECT_ROOT / "data" / "img"
LOGO_DIR = IMG_DIR / "product" / "logo"

# Расширения, которые считаем изображением лого (допустимы для вставки в pptx).
LOGO_EXTS = (".png", ".jpg", ".jpeg", ".webp")


def slugify(name: str) -> str:
    """Слаг канонического имени продукта для имени файла лого."""
    s = unicodedata.normalize("NFKD", name or "").strip().lower()
    s = re.sub(r"[^\w\-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "logo"


def save_logo(product_name: str, data: bytes, ext: str = "png") -> str:
    """Сохраняет лого продукта, удаляя предыдущие варианты с тем же слагом.

    Возвращает имя файла (например `sd-wan.png`).
    """
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(product_name)
    ext = ext.lstrip(".").lower()
    for old in LOGO_DIR.glob(f"{slug}.*"):
        if old.suffix.lower() in LOGO_EXTS:
            old.unlink(missing_ok=True)
    filename = f"{slug}.{ext}"
    (LOGO_DIR / filename).write_bytes(data)
    return filename


def delete_logo(product_name: str) -> bool:
    """Удаляет лого продукта. Возвращает True, если файл был."""
    slug = slugify(product_name)
    removed = False
    for old in LOGO_DIR.glob(f"{slug}.*"):
        if old.suffix.lower() in LOGO_EXTS:
            old.unlink(missing_ok=True)
            removed = True
    return removed


def logo_path(product_name: str) -> Optional[Path]:
    """Путь к файлу лого продукта (по сдагу) или None, если лого нет."""
    slug = slugify(product_name)
    for p in LOGO_DIR.glob(f"{slug}.*"):
        if p.suffix.lower() in LOGO_EXTS:
            return p
    return None


def logo_url(product_name: str) -> Optional[str]:
    """URL лого для фронтенда или None."""
    path = logo_path(product_name)
    if not path:
        return None
    return f"/img/product/logo/{path.name}"


def status(products: List[str]) -> dict:
    """Для каждого продукта: есть ли лого и по какому URL."""
    return {
        product: ({"has_logo": True, "url": logo_url(product)} if logo_path(product) else {"has_logo": False, "url": None})
        for product in products
    }


def list_all() -> List[dict]:
    """Все загруженные лого (имя файла + URL)."""
    if not LOGO_DIR.exists():
        return []
    return [
        {"filename": p.name, "url": f"/img/product/logo/{p.name}"}
        for p in sorted(LOGO_DIR.iterdir())
        if p.is_file() and p.suffix.lower() in LOGO_EXTS
    ]


def reset_logo_state() -> None:
    """Сбрасывает библиотеку (для тестов)."""
    if LOGO_DIR.exists():
        for p in LOGO_DIR.iterdir():
            if p.is_file() and p.suffix.lower() in LOGO_EXTS:
                p.unlink(missing_ok=True)
