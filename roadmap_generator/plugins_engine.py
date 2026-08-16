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
from roadmap_generator.approval import is_under_approval
from roadmap_generator.labels import get_apptitle_label
from roadmap_generator.ordering import (
    SEPARATOR,
    get_effective_order,
    get_tier_inheritance_flag,
    resolve_apptitle_order,
)
from roadmap_generator.schema import RoadmapModel
from roadmap_generator.deck_meta import get_deck_meta
from roadmap_generator.static_slides import get_static_slides
from roadmap_generator.strings import get_service_string

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"

_PLUGIN_ATTRS = ("id", "label", "kind", "scope", "default_settings", "apply")

# Гибкая раскладка: максимум фич в одной колонке-квартале (v1-прокси «сколько влезает»).
# При переполнении квартал занимает несколько колонок. Позже может стать текст-зависимым
# (fit_bullets_dynamic) или настраиваться в админке как «фиксированный лимит» (ТЗ v4 §4.2 п.8).
MAX_BULLETS_PER_COLUMN = 10


@dataclass
class RoadmapSlide:
    product: str
    stream: str
    tier: str
    columns: List[Column]
    continuation: bool
    has_subject_to_change: bool = False
    footnote: str = ""
    inheritance_note: str = ""
    language: str = "ru"


@dataclass
class DividerSlide:
    divider_type: str  # "product" | "stream"
    title: str


@dataclass
class TitleSlide:
    title: str
    year: str
    version: str


@dataclass
class ThankYouSlide:
    text: str


@dataclass
class StaticSlide:
    name: str
    pptx: str = ""


@dataclass
class SlidePlan:
    slides: List[Union[TitleSlide, ThankYouSlide, DividerSlide, RoadmapSlide, StaticSlide]] = field(default_factory=list)
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
    product_decks: List[Tuple[str, List[Union[DividerSlide, RoadmapSlide]]]] = []

    for pname in get_effective_order("", [p.name for p in model.products]):
        product = products_by_name[pname]
        deck_items: List[Union[DividerSlide, RoadmapSlide]] = []

        for sname in get_effective_order(pname, [s.name for s in product.streams]):
            stream = next(s for s in product.streams if s.name == sname)
            stream_slides: List[RoadmapSlide] = []
            tier_names = [t.name for t in stream.tiers]
            ordered_tiers = get_effective_order(f"{pname}{SEPARATOR}{sname}", tier_names)
            for idx, tname in enumerate(ordered_tiers):
                tier = next(t for t in stream.tiers if t.name == tname)
                tier_path = f"{pname}{SEPARATOR}{sname}{SEPARATOR}{tname}"
                inheritance_note = None
                if idx > 0 and get_tier_inheritance_flag(tier_path):
                    previous = ", ".join(ordered_tiers[:idx])
                    inheritance_note = f"{get_service_string('inheritance_prefix', model.language)} {previous}"
                stream_slides.extend(
                    _build_tier_slides(
                        model.language, pname, sname, tname, tier, filters, groupers, plugin_settings, inheritance_note,
                    )
                )
            if stream_slides:
                if sname != "-":
                    deck_items.append(DividerSlide("stream", sname))
                deck_items.extend(stream_slides)

        if deck_items:
            product_decks.append((pname, [DividerSlide("product", pname)] + deck_items))

    slides = _assemble_with_static(product_decks, get_static_slides())

    meta = get_deck_meta()
    deck: List[Union[TitleSlide, ThankYouSlide, DividerSlide, RoadmapSlide, StaticSlide]] = [
        TitleSlide(title=meta["title"], year=meta["year"], version=meta["version"]),
    ]
    deck.extend(slides)
    deck.append(ThankYouSlide(text=get_service_string("thank_you", model.language)))
    return SlidePlan(slides=deck, conflicts=conflicts)


def _assemble_with_static(product_decks, static_slides) -> List[Union[DividerSlide, RoadmapSlide, StaticSlide]]:
    """Вставляет статичные слайды по точкам: before:<P>, after:<P>, end."""
    result: List[Union[DividerSlide, RoadmapSlide, StaticSlide]] = []
    for pname, deck_items in product_decks:
        for ss in static_slides:
            if ss["position"] == f"before:{pname}":
                result.append(StaticSlide(name=ss["name"], pptx=ss.get("pptx", "")))
        result.extend(deck_items)
        for ss in static_slides:
            if ss["position"] == f"after:{pname}":
                result.append(StaticSlide(name=ss["name"], pptx=ss.get("pptx", "")))
    for ss in static_slides:
        if ss["position"] == "end":
            result.append(StaticSlide(name=ss["name"], pptx=ss.get("pptx", "")))
    return result


def _build_tier_slides(language, product, stream, tier, tier_obj, filters, groupers, plugin_settings, inheritance_note=None):
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
                release_id=release.id,
            ))

    context = SlideBuildContext(
        product_name=product, stream_name=stream, tier_name=tier, bullets=bullets,
    )

    for plugin in filters:
        plugin.apply(context, _resolve_plugin_settings(plugin, plugin_settings, product, parent_path))
    if not context.bullets:
        return []

    context.columns = _allocate_columns(context.bullets)
    _apply_under_approval(context.columns, language)

    for plugin in groupers:
        plugin.apply(context, _resolve_plugin_settings(plugin, plugin_settings, product, parent_path))

    _apply_group_order_and_labels(context.columns)

    return _paginate(product, stream, tier, context.columns, language, inheritance_note)


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


def _allocate_columns(bullets: List[Bullet]) -> List[Column]:
    """Гибкая раскладка: квартал с переполнением занимает несколько колонок.

    Пули группируются по кварталу хронологически; каждый квартал режется на колонки
    по `MAX_BULLETS_PER_COLUMN`, сохраняя порядок фич внутри квартала.
    """
    by_quarter: dict = defaultdict(list)
    for bullet in bullets:
        by_quarter[bullet.quarter].append(bullet)
    columns: List[Column] = []
    for quarter in sorted(by_quarter, key=_quarter_sort_key):
        quarter_bullets = by_quarter[quarter]
        for i in range(0, len(quarter_bullets), MAX_BULLETS_PER_COLUMN):
            columns.append(Column(quarter=quarter, bullets=quarter_bullets[i:i + MAX_BULLETS_PER_COLUMN]))
    return columns


def _quarter_sort_key(quarter: str) -> Tuple[int, int]:
    num_part, year_part = quarter.split()
    return (int(year_part), int(num_part[1:]))


def _apply_under_approval(columns: List[Column], language: str) -> None:
    """Помечает колонку-квартал бейджем, если в ней есть релиз «под согласованием»."""
    badge = get_service_string("under_approval_badge", language)
    for column in columns:
        if any(is_under_approval(b.release_id) for b in column.bullets):
            column.under_approval_badge = badge


def _apply_group_order_and_labels(columns: List[Column]) -> None:
    for column in columns:
        if column.grouped:
            ordered = resolve_apptitle_order([(g.app_title, len(g.bullets)) for g in column.groups])
            by_title = {g.app_title: g for g in column.groups}
            column.groups = [by_title[t] for t in ordered]
            for group in column.groups:
                group.app_title = get_apptitle_label(group.app_title)
                # сначала подтверждённые (false), затем «под вопросом» (true)
                group.bullets.sort(key=lambda b: b.is_subject_to_change)
        else:
            column.bullets.sort(key=lambda b: b.is_subject_to_change)


def _column_all_bullets(column: Column) -> List[Bullet]:
    if column.grouped:
        return [b for g in column.groups for b in g.bullets]
    return column.bullets


def _paginate(
    product: str,
    stream: str,
    tier: str,
    columns: List[Column],
    language: str,
    inheritance_note: str,
) -> List[RoadmapSlide]:
    slides: List[RoadmapSlide] = []
    for i in range(0, len(columns), 4):
        chunk = columns[i:i + 4]
        has_stc = any(b.is_subject_to_change for col in chunk for b in _column_all_bullets(col))
        footnote = get_service_string("subject_to_change_footnote", language) if has_stc else ""
        note = inheritance_note if (i == 0 and inheritance_note) else ""
        slides.append(RoadmapSlide(
            product=product, stream=stream, tier=tier,
            columns=chunk, continuation=(i > 0),
            has_subject_to_change=has_stc,
            footnote=footnote,
            inheritance_note=note,
            language=language,
        ))
    return slides


def build_tree(model: RoadmapModel) -> dict:
    """Упорядоченное дерево Product → Stream → Tier (с флагом наследования тира)."""
    products_by_name = {p.name: p for p in model.products}
    products = []
    for pname in get_effective_order("", [p.name for p in model.products]):
        product = products_by_name[pname]
        streams = []
        for sname in get_effective_order(pname, [s.name for s in product.streams]):
            stream = next(s for s in product.streams if s.name == sname)
            tiers = []
            for tname in get_effective_order(f"{pname}{SEPARATOR}{sname}", [t.name for t in stream.tiers]):
                tier_path = f"{pname}{SEPARATOR}{sname}{SEPARATOR}{tname}"
                tiers.append({"name": tname, "inheritance_flag": get_tier_inheritance_flag(tier_path)})
            streams.append({"name": sname, "tiers": tiers})
        products.append({"name": pname, "streams": streams})
    return {"products": products}


def list_releases(model: RoadmapModel) -> list:
    """Плоский список релизов (для UI пометки «под согласованием»)."""
    releases = []
    for product in model.products:
        for stream in product.streams:
            for tier in stream.tiers:
                for release in tier.releases:
                    releases.append({
                        "id": release.id,
                        "title": release.title,
                        "app_title": release.app_title,
                        "quarter": release.quarter,
                        "product": product.name,
                        "stream": stream.name,
                        "tier": tier.name,
                    })
    return releases
