"""Видимость продукта по языкам (RU/EN).

По умолчанию продукт показывается во всех версиях. Пользователь может исключить
продукт из одной или обеих версий. Хранится в глобальном профиле по имени продукта.
"""
from __future__ import annotations

from typing import Dict

_product_languages: Dict[str, Dict[str, bool]] = {}


def is_product_visible(name: str, language: str) -> bool:
    langs = _product_languages.get(name)
    if langs is None:
        return True  # дефолт: обе версии
    return langs.get(language, True)


def get_product_languages() -> Dict[str, Dict[str, bool]]:
    return {name: dict(langs) for name, langs in _product_languages.items()}


def save_product_languages(state) -> None:
    _product_languages.clear()
    for name, langs in state.items():
        _product_languages[name] = {
            "ru": bool(langs.get("ru", True)),
            "en": bool(langs.get("en", True)),
        }


def export_state() -> Dict[str, Dict[str, bool]]:
    return {name: dict(langs) for name, langs in _product_languages.items()}


def import_state(state) -> None:
    save_product_languages(state)


def _reset_state() -> None:
    _product_languages.clear()
