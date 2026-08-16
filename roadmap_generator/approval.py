"""Флаги «Под согласованием» (Under approval) — project-scope, на уровне Release.

Хранится как множество Id релизов (в памяти; на этапе 7 переедет в проектный файл).
"""
from __future__ import annotations

from typing import Iterable, Set

_under_approval_ids: Set[int] = set()


def get_under_approval_ids() -> Set[int]:
    return set(_under_approval_ids)


def set_under_approval_ids(ids: Iterable[int]) -> None:
    _under_approval_ids.clear()
    _under_approval_ids.update(int(i) for i in ids)


def is_under_approval(release_id: int) -> bool:
    return release_id in _under_approval_ids


def export_state() -> list:
    return sorted(_under_approval_ids)


def import_state(ids) -> None:
    _under_approval_ids.clear()
    _under_approval_ids.update(int(i) for i in ids)


def _reset_state() -> None:
    _under_approval_ids.clear()
