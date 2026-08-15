"""Движок плагинов: загрузка, разрешение конфликтов, построение `SlidePlan`.

Не зависит от python-pptx — работает только на структурах данных. Один и тот же
`SlidePlan` используется и для UI-превью, и для финального рендера.
"""
from __future__ import annotations

import importlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Union

from plugins._base import Bullet, Column, RoadmapPlugin, SlideBuildContext
from roadmap_generator.labels import get_apptitle_label
from roadmap_generator.ordering import SEPARATOR, get_effective_order, resolve_apptitle_order
from roadmap_generator.schema import RoadmapModel

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"

_PLUGIN_ATTRS = ("id", "label", "kind", "scope", "default_settings", "apply")


@dataclass
class RoadmapSlide:
    product: str
    stream: str
    tier: str
    columns: List[Column]
    continuation: bool


@dataclass
class DividerSlide:
    divider_type: str  # "product" | "stream"
    title: str


@dataclass
class SlidePlan:
    slides: List[Union[DividerSlide, RoadmapSlide]] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)


def load_plugins() -> List[RoadmapPlugin]:
    """Обнаруживает плагины перебором `.py` в `plugins/` (кроме `_*`)."""
    plugins: List[RoadmapPlugin] = []
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module = importlib.import_module(f"plugins.{path.stem}")
        for obj in vars(module).values():
            if _is_plugin_class(obj, module.__name__):
                plugins.append(obj())
    return plugins


def _is_plugin_class(obj, module_name: str) -> bool:
    return (
        isinstance(obj, type)
        and obj.__module__ == module_name
        and all(hasattr(obj, attr) for attr in _PLUGIN_ATTRS)
    )


def resolve_conflicts(active: List[RoadmapPlugin]) -> Tuple[List[RoadmapPlugin], List[str]]:
    """Возвращает (применимые_плагины, тексты_конфликтов).

    Два плагина одного `kind` несовместимы: оба исключаются из `применимых`,
    конфликт попадает в тексты для UI-алерта (рендер остальной колоды не блокируется).
    """
    by_kind: dict = defaultdict(list)
    for plugin in active:
        by_kind[plugin.kind].append(plugin)

    applicable: List[RoadmapPlugin] = []
    conflicts: List[str] = []
    for kind, plugins in by_kind.items():
        if len(plugins) > 1:
            labels = ", ".join(sorted(p.label for p in plugins))
            conflicts.append(f"Конфликт плагинов ({kind}): {labels} — оставьте один")
        else:
            applicable.append(plugins[0])
    return applicable, conflicts


def build_slide_plan(model: RoadmapModel, plugin_settings: dict) -> SlidePlan:
    """Строит план слайдов (Product/Stream-divider + roadmap-слайды).

    Порядок узлов — через `ordering.get_effective_order` на каждом уровне.
    Титульный/финальный/статические слайды добавляются на более поздних этапах.
    """
    applicable, conflicts = resolve_conflicts(load_plugins())
    filters = [p for p in applicable if p.kind == "filter"]
    groupers = [p for p in applicable if p.kind == "grouping"]
    # annotation/static/collector — подключаются на этапах 6+.

    products_by_name = {p.name: p for p in model.products}
    slides: List[Union[DividerSlide, RoadmapSlide]] = []

    for pname in get_effective_order("", [p.name for p in model.products]):
        product = products_by_name[pname]
        deck_items: List[Union[DividerSlide, RoadmapSlide]] = []

        for sname in get_effective_order(pname, [s.name for s in product.streams]):
            stream = next(s for s in product.streams if s.name == sname)
            stream_slides: List[RoadmapSlide] = []
            tier_names = [t.name for t in stream.tiers]
            for tname in get_effective_order(f"{pname}{SEPARATOR}{sname}", tier_names):
                tier = next(t for t in stream.tiers if t.name == tname)
                stream_slides.extend(
                    _build_tier_slides(model.language, pname, sname, tname, tier, filters, groupers, plugin_settings)
                )
            if stream_slides:
                if sname != "-":
                    deck_items.append(DividerSlide("stream", sname))
                deck_items.extend(stream_slides)

        if deck_items:
            slides.append(DividerSlide("product", pname))
            slides.extend(deck_items)

    return SlidePlan(slides=slides, conflicts=conflicts)


def _build_tier_slides(language, product, stream, tier, tier_obj, filters, groupers, plugin_settings):
    parent_path = f"{product}{SEPARATOR}{stream}{SEPARATOR}{tier}"

    bullets: List[Bullet] = []
    for release in tier_obj.releases:
        for req in release.requirements:
            text = (req.marketing_title_en or req.marketing_title) if language == "en" else req.marketing_title
            bullets.append(Bullet(
                requirement_id=req.id,
                text=text,
                kbr=req.kbr,
                app_title=release.app_title,
                quarter=release.quarter,
                is_subject_to_change=req.is_subject_to_change,
            ))

    context = SlideBuildContext(
        product_name=product, stream_name=stream, tier_name=tier, bullets=bullets,
    )

    for plugin in filters:
        plugin.apply(context, _resolve_plugin_settings(plugin, plugin_settings, product, parent_path))
    if not context.bullets:
        return []

    context.columns = _group_by_quarter(context.bullets)

    for plugin in groupers:
        plugin.apply(context, _resolve_plugin_settings(plugin, plugin_settings, product, parent_path))

    _apply_group_order_and_labels(context.columns)

    return _paginate(product, stream, tier, context.columns)


def _resolve_plugin_settings(plugin, plugin_settings, product_name, parent_path) -> dict:
    """Слои: default → global → product → tier. Для apptitle_grouping дефолт
    `enabled` резолвится per-product («Next» в имени), если не задан явно."""
    settings = dict(plugin.default_settings())
    layers = [
        plugin_settings.get("global", {}),
        plugin_settings.get("products", {}).get(product_name, {}),
        plugin_settings.get("tiers", {}).get(parent_path, {}),
    ]
    enabled_explicit = False
    for layer in layers:
        if plugin.id in layer:
            settings.update(layer[plugin.id])
            if "enabled" in layer[plugin.id]:
                enabled_explicit = True
    if plugin.id == "apptitle_grouping" and not enabled_explicit:
        settings["enabled"] = "Next" in product_name
    return settings


def _group_by_quarter(bullets: List[Bullet]) -> List[Column]:
    by_quarter: dict = defaultdict(list)
    for bullet in bullets:
        by_quarter[bullet.quarter].append(bullet)
    return [Column(quarter=q, bullets=by_quarter[q]) for q in sorted(by_quarter, key=_quarter_sort_key)]


def _quarter_sort_key(quarter: str) -> Tuple[int, int]:
    num_part, year_part = quarter.split()
    return (int(year_part), int(num_part[1:]))


def _apply_group_order_and_labels(columns: List[Column]) -> None:
    for column in columns:
        if not column.grouped:
            continue
        ordered = resolve_apptitle_order([(g.app_title, len(g.bullets)) for g in column.groups])
        by_title = {g.app_title: g for g in column.groups}
        column.groups = [by_title[t] for t in ordered]
        for group in column.groups:
            group.app_title = get_apptitle_label(group.app_title)


def _paginate(product: str, stream: str, tier: str, columns: List[Column]) -> List[RoadmapSlide]:
    slides: List[RoadmapSlide] = []
    for i in range(0, len(columns), 4):
        slides.append(RoadmapSlide(
            product=product, stream=stream, tier=tier,
            columns=columns[i:i + 4], continuation=(i > 0),
        ))
    return slides
