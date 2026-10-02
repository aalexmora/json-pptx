"""Служебные RU/EN строки (ТЗ v4 §7.4).

Дефолтные значения + пользовательские переопределения (редактируются в админке,
хранятся в глобальном профиле). `get_service_string` возвращает override, если
задан, иначе дефолт.
"""
from __future__ import annotations

from typing import Dict

DEFAULTS: Dict[str, Dict[str, str]] = {
    "subject_to_change_footnote": {"ru": "* Могут быть внесены изменения", "en": "* Subject to Change"},
    "under_approval_badge": {"ru": "На согласовании", "en": "In the approval process"},
    "thank_you": {"ru": "Спасибо!", "en": "Thank you!"},
    "roadmap_title": {"ru": "Роадмап", "en": "Roadmap"},
    "roadmap_cont_title": {"ru": "Роадмап (продолжение)", "en": "Roadmap (cont.)"},
}

_overrides: Dict[str, Dict[str, str]] = {}


def get_service_string(key: str, language: str) -> str:
    value = _overrides.get(key, {}).get(language)
    if value:
        return value
    return DEFAULTS[key][language]


def get_service_strings() -> Dict[str, Dict[str, str]]:
    """Полный набор (дефолты + override) для UI/профиля."""
    result = {k: dict(v) for k, v in DEFAULTS.items()}
    for key, langs in _overrides.items():
        for lang, val in langs.items():
            if key in result and val:
                result[key][lang] = val
    return result


def save_service_strings(strings: Dict[str, Dict[str, str]]) -> None:
    _overrides.clear()
    for key, langs in strings.items():
        _overrides[key] = {"ru": langs.get("ru", ""), "en": langs.get("en", "")}


def export_state() -> Dict[str, Dict[str, str]]:
    return {k: dict(v) for k, v in _overrides.items()}


def import_state(state: Dict[str, Dict[str, str]]) -> None:
    _overrides.clear()
    for key, langs in state.items():
        _overrides[key] = {"ru": langs.get("ru", ""), "en": langs.get("en", "")}


def _reset_state() -> None:
    _overrides.clear()
