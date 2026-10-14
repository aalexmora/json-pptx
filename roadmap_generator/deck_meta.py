"""Метаданные титульного слайда (заголовок/год/версия) — вводит пользователь."""
from __future__ import annotations

from typing import Any, Dict

_DEFAULTS: Dict[str, Any] = {
    "title": "",
    "year": "",
    "version": "",
    "include_title_slide": True,
    "include_thank_you_slide": True,
    "thank_you_text": {"ru": "Спасибо!", "en": "Thank you!"},
}
_deck_meta: Dict[str, Any] = dict(_DEFAULTS)


def get_deck_meta() -> Dict[str, Any]:
    return {**_deck_meta, "thank_you_text": dict(_deck_meta["thank_you_text"])}


def save_deck_meta(title: str = "", year: str = "", version: str = "") -> None:
    _deck_meta["title"] = title or ""
    _deck_meta["year"] = year or ""
    _deck_meta["version"] = version or ""


def export_state() -> Dict[str, Any]:
    return {**_deck_meta, "thank_you_text": dict(_deck_meta["thank_you_text"])}


def import_state(
    state: Dict[str, Any],
    legacy_thank_you_text: Dict[str, str] | None = None,
) -> None:
    _deck_meta["title"] = state.get("title", "") or ""
    _deck_meta["year"] = state.get("year", "") or ""
    _deck_meta["version"] = state.get("version", "") or ""
    _deck_meta["include_title_slide"] = state.get("include_title_slide", True) is not False
    _deck_meta["include_thank_you_slide"] = state.get("include_thank_you_slide", True) is not False
    thank_you_text = state.get("thank_you_text")
    if not isinstance(thank_you_text, dict):
        thank_you_text = {}
    legacy_thank_you_text = legacy_thank_you_text or {}
    normalized_text = {}
    for language in ("ru", "en"):
        value = thank_you_text.get(language)
        if value is None:
            value = legacy_thank_you_text.get(language)
        if value is None:
            value = _DEFAULTS["thank_you_text"][language]
        normalized_text[language] = str(value)
    _deck_meta["thank_you_text"] = normalized_text


def _reset_state() -> None:
    _deck_meta.clear()
    _deck_meta.update({**_DEFAULTS, "thank_you_text": dict(_DEFAULTS["thank_you_text"])})
