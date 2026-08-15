"""Служебные RU/EN строки.

Пока это дефолтные значения; на этапе 8 они станут редактируемой таблицей админки
(ТЗ v4 §7.4), а этот модуль — источником дефолтов.
"""
from __future__ import annotations

from typing import Dict

# Сноска к слайду, если на нём есть хотя бы один `IsSubjectToChange`-bullet.
SUBJECT_TO_CHANGE_FOOTNOTE: Dict[str, str] = {
    "ru": "* Могут быть внесены изменения",
    "en": "* Subject to Change",
}

# Префикс заметки наследования тира (ТЗ v4 §4.2 п.7). RU-дефолт — для сверки.
INHERITANCE_PREFIX: Dict[str, str] = {
    "ru": "вкл. все фичи предыдущих тиров:",
    "en": "inc. all features of previous tier(s):",
}
