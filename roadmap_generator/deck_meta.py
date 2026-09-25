"""Метаданные титульного слайда (заголовок/год/версия) — вводит пользователь."""
from __future__ import annotations

from typing import Any, Dict

_DEFAULTS: Dict[str, Any] = {
    "title": "",
    "year": "",
    "version": "",
    "include_title_slide": True,
    "include_thank_you_slide": True,
}
_deck_meta: Dict[str, Any] = dict(_DEFAULTS)


def get_deck_meta() -> Dict[str, Any]:
    return dict(_deck_meta)


def save_deck_meta(title: str = "", year: str = "", version: str = "") -> None:
    _deck_meta["title"] = title or ""
    _deck_meta["year"] = year or ""
    _deck_meta["version"] = version or ""


def export_state() -> Dict[str, Any]:
    return dict(_deck_meta)


def import_state(state: Dict[str, Any]) -> None:
    _deck_meta["title"] = state.get("title", "") or ""
    _deck_meta["year"] = state.get("year", "") or ""
    _deck_meta["version"] = state.get("version", "") or ""
    _deck_meta["include_title_slide"] = state.get("include_title_slide", True) is not False
    _deck_meta["include_thank_you_slide"] = state.get("include_thank_you_slide", True) is not False


def _reset_state() -> None:
    _deck_meta.clear()
    _deck_meta.update(_DEFAULTS)
