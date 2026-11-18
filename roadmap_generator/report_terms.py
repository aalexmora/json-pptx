"""Словарь терминов для отчёта «Only RU» и проверки ENG-названий.

Словарь хранится в профиле (`data/profile.json`, ключ `report_terms`). Если
ключа нет, используется стартовый набор; пустой список означает, что словарь
очищен намеренно, и стартовый набор не возвращается.
"""
from __future__ import annotations

import re
from typing import Iterable, List

DEFAULT_TERMS = (
    "ФСТЕК", "ФСТЭК", "FSTEC", "FSB", "ФСБ", "СБЕР", "SBER",
    "Yandex", "Яндекс", "Astra", "Астра",
)

_terms: List[str] = list(DEFAULT_TERMS)


def clean_terms(values: Iterable) -> List[str]:
    """Убирает пустые значения и повторы без учёта регистра, сохраняя порядок."""
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        term = re.sub(r"\s+", " ", value).strip()
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result


def get_terms() -> List[str]:
    return list(_terms)


def export_state() -> List[str]:
    return list(_terms)


def import_state(state) -> None:
    """`None` или не список — стартовый набор; список — очищенные значения из него."""
    if isinstance(state, list):
        _terms[:] = clean_terms(state)
    else:
        _terms[:] = DEFAULT_TERMS


def _reset_state() -> None:
    _terms[:] = DEFAULT_TERMS
