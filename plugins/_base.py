"""Протокол плагина и структуры данных, которыми плагин обменивается с движком.

Это CORE-контракт: при добавлении новых плагинов этот файл НЕ менять. Плагин
работает только с `SlideBuildContext`, не импортирует `roadmap_generator/*`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Optional, Protocol

PluginKind = Literal["filter", "grouping", "annotation", "static", "collector"]
PluginScope = Literal["global", "product", "tier"]


@dataclass
class Bullet:
    """Один отображаемый bullet требования (уже языково-отфильтрованный)."""

    requirement_id: int
    text: str                          # MarketingTitle (RU) или MarketingTitleEn (EN)
    kbr: Optional[str]                 # "Yes" = Subject to Change (S2C); None = отсутствовало
    app_title: str                     # из Release, для apptitle_grouping
    quarter: str                       # "Qx YYYY", для группировки в колонки
    is_subject_to_change: bool
    release_id: int = 0                # из Release, для under_approval


@dataclass
class Group:
    """Подгруппа AppTitle внутри колонки (заполняется grouping-плагином)."""

    app_title: str
    bullets: List[Bullet] = field(default_factory=list)


@dataclass
class Column:
    """Колонка-квартал. До группировки — `bullets`, после — `groups` + `grouped`."""

    quarter: str
    bullets: List[Bullet] = field(default_factory=list)
    groups: List[Group] = field(default_factory=list)
    grouped: bool = False
    under_approval_badge: str = ""      # непусто, если в квартале есть релиз «под согласованием»


@dataclass
class SlideBuildContext:
    """Рабочий контекст построения слайда одного Tier — через него идут плагины."""

    product_name: str
    stream_name: str
    tier_name: str
    bullets: List[Bullet] = field(default_factory=list)
    columns: List[Column] = field(default_factory=list)


class RoadmapPlugin(Protocol):
    id: str
    label: str
    kind: PluginKind
    scope: PluginScope

    def default_settings(self) -> dict: ...

    def apply(self, context: "SlideBuildContext", settings: dict) -> "SlideBuildContext": ...
