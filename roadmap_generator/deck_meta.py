"""Метаданные титульного слайда (заголовок/год/версия) — вводит пользователь."""
from __future__ import annotations

from typing import Dict

_deck_meta: Dict[str, str] = {"title": "", "year": "", "version": ""}


def get_deck_meta() -> Dict[str, str]:
    return dict(_deck_meta)


def save_deck_meta(title: str = "", year: str = "", version: str = "") -> None:
    _deck_meta["title"] = title or ""
    _deck_meta["year"] = year or ""
    _deck_meta["version"] = version or ""


def export_state() -> Dict[str, str]:
    return dict(_deck_meta)


def import_state(state: Dict[str, str]) -> None:
    _deck_meta["title"] = state.get("title", "") or ""
    _deck_meta["year"] = state.get("year", "") or ""
    _deck_meta["version"] = state.get("version", "") or ""


def _reset_state() -> None:
    _deck_meta.update({"title": "", "year": "", "version": ""})
