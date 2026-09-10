"""Языковые отображаемые названия Tier для `slide_title`.

Ключом остаётся исходное каноническое имя Tier. Пустое переименование означает
fallback на исходное имя, поэтому настройки не влияют на ordering и логотипы.
"""
from __future__ import annotations

from typing import Dict

_tier_names: Dict[str, Dict[str, str]] = {}


def get_tier_name(original: str, language: str) -> str:
    value = _tier_names.get(original, {}).get(language, "").strip()
    return value or original


def export_state() -> Dict[str, Dict[str, str]]:
    return {name: dict(localized) for name, localized in _tier_names.items()}


def import_state(state) -> None:
    _tier_names.clear()
    if not isinstance(state, dict):
        return
    for name, localized in state.items():
        if not isinstance(name, str) or not isinstance(localized, dict):
            continue
        values = {
            "ru": str(localized.get("ru") or "").strip(),
            "en": str(localized.get("en") or "").strip(),
        }
        if values["ru"] or values["en"]:
            _tier_names[name] = values


def _reset_state() -> None:
    _tier_names.clear()
