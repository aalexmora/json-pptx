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

from plugins._base import Bullet, Column, Group, RoadmapPlugin, SlideBuildContext
from roadmap_generator.approval import is_under_approval
from roadmap_generator.labels import get_apptitle_label
from roadmap_generator.product_languages import is_product_visible
from roadmap_generator.ordering import (
    SEPARATOR,
    get_effective_order,
    get_product_inheritance_flag,
    get_product_slide_hidden_flag,
    resolve_apptitle_order,
)
from roadmap_generator.schema import RoadmapModel
from roadmap_generator.deck_meta import get_deck_meta
from roadmap_generator.static_slides import get_static_slides
from roadmap_generator.strings import get_service_string
from roadmap_generator.layout import estimate_bullet_height_pt, estimate_group_height_pt

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"

_PLUGIN_ATTRS = ("id", "label", "kind", "scope", "default_settings", "apply")

# Геометрия слота для оценки вместимости (TOR v2 §3: ровно 4 фикс. слота, высота по
# тексту). Точные размеры уточняются в builder'е по реальному шаблону; здесь — оценки
# для плана/превью (слайд 16:9, шапка/сноска/поля вычтены приблизительно).
SLOT_WIDTH_IN = 3.0   # ≈ (13.333 − 2×0.5) / 4
SLOT_HEIGHT_IN = 5.0  # тело слайда (7.5 − шапка ~1.0 − сноска ~0.4 − поля)
BASE_FONT_PT = 14


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
    prompt: str = ""
    language: str = "ru"
    position: str = "end"


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
        if not is_product_visible(pname, model.language):
            continue
        product = products_by_name[pname]
        product_inheritance = get_product_inheritance_flag(pname)
        deck_items: List[Union[DividerSlide, RoadmapSlide]] = []
        # Эти две истории намеренно создаются заново внутри цикла Product:
        # наследование действует между Stream/Tier одного продукта и никогда
        # не пересекает границу следующего продукта в колоде.
        product_seen_req_ids: set[int] = set()
        product_previous_tiers: List[str] = []

        for sname in get_effective_order(pname, [s.name for s in product.streams]):
            stream = next(s for s in product.streams if s.name == sname)
            stream_slides: List[RoadmapSlide] = []
            tier_names = [t.name for t in stream.tiers]
            ordered_tiers = get_effective_order(f"{pname}{SEPARATOR}{sname}", tier_names)
            for tname in ordered_tiers:
                tier = next(t for t in stream.tiers if t.name == tname)
                inherit = bool(product_previous_tiers) and product_inheritance
                inheritance_note = None
                if inherit:
                    previous = "\n".join(f"• {tier_name}" for tier_name in product_previous_tiers)
                    inheritance_note = f"{get_service_string('inheritance_prefix', model.language)}\n{previous}"
                slides, shown_ids = _build_tier_slides(
                    model.language, pname, sname, tname, tier, filters, groupers, plugin_settings,
                    inheritance_note, exclude_req_ids=(product_seen_req_ids if inherit else None),
                )
                product_seen_req_ids.update(shown_ids)
                product_previous_tiers.append(f"{sname} / {tname}")
                stream_slides.extend(slides)
            if stream_slides:
                if sname != "-":
                    deck_items.append(DividerSlide("stream", sname))
                deck_items.extend(stream_slides)

        if deck_items:
            product_intro = [] if get_product_slide_hidden_flag(pname) else [DividerSlide("product", pname)]
            product_decks.append((pname, product_intro + deck_items))

    configured_static = get_static_slides(model.language)
    slides = _assemble_with_static(product_decks, configured_static)

    meta = get_deck_meta()
    deck: List[Union[TitleSlide, ThankYouSlide, DividerSlide, RoadmapSlide, StaticSlide]] = [
        _to_static_slide(ss) for ss in configured_static if ss["position"] == "first"
    ]
    if meta.get("include_title_slide", True):
        deck.append(TitleSlide(title=meta["title"], year=meta["year"], version=meta["version"]))
    deck.extend(slides)
    if meta.get("include_thank_you_slide", True):
        deck.append(ThankYouSlide(text=get_service_string("thank_you", model.language)))
    return SlidePlan(slides=deck, conflicts=conflicts)


def _assemble_with_static(product_decks, static_slides) -> List[Union[DividerSlide, RoadmapSlide, StaticSlide]]:
    """Вставляет статичные слайды по точкам: before:<P>, after:<P>, end."""
    result: List[Union[DividerSlide, RoadmapSlide, StaticSlide]] = []
    for pname, deck_items in product_decks:
        for ss in static_slides:
            if ss["position"] == f"before:{pname}":
                result.append(_to_static_slide(ss))
        result.extend(deck_items)
        for ss in static_slides:
            if ss["position"] == f"after:{pname}":
                result.append(_to_static_slide(ss))
    for ss in static_slides:
        if ss["position"] == "end":
            result.append(_to_static_slide(ss))
    return result


def _to_static_slide(slide: dict) -> StaticSlide:
    return StaticSlide(
        name=slide["name"],
        pptx=slide.get("pptx", ""),
        prompt=slide.get("prompt", ""),
        language=slide["language"],
        position=slide.get("position", "end"),
    )


def _build_tier_slides(language, product, stream, tier, tier_obj, filters, groupers, plugin_settings, inheritance_note=None, exclude_req_ids=None):
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
        return [], set()

    # Наследование (дедупликация): скрыть фичи, чей Id уже показывался в предыдущих
    # Tier любого Stream того же Product. Заметка при этом остаётся на слайде.
    if exclude_req_ids:
        context.bullets = [b for b in context.bullets if b.requirement_id not in exclude_req_ids]
    if not context.bullets:
        return [], set()

    # 1) одна колонка-прототип на квартал; группировка по AppTitle плагином.
    quarter_columns = _group_by_quarter(context.bullets)
    context.columns = quarter_columns
    for plugin in groupers:
        plugin.apply(context, _resolve_plugin_settings(plugin, plugin_settings, product, parent_path))

    # 2) атомарная упаковка групп/фич в слоты по высоте (TOR v2 §4 шаг 1).
    columns = _pack_quarters(context.columns)

    _apply_under_approval(columns, language)
    _apply_group_order_and_labels(columns)

    slides = _paginate(product, stream, tier, columns, language, inheritance_note)
    shown_ids = {b.requirement_id for b in context.bullets}
    return slides, shown_ids


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
    """Одна колонка-прототип на квартал (хронологически q1..q4) — до группировки/упаковки."""
    by_quarter: dict = defaultdict(list)
    for bullet in bullets:
        by_quarter[bullet.quarter].append(bullet)
    return [
        Column(quarter=quarter, bullets=by_quarter[quarter])
        for quarter in sorted(by_quarter, key=_quarter_sort_key)
    ]


def _quarter_sort_key(quarter: str) -> Tuple[int, int]:
    num_part, year_part = quarter.split()
    return (int(year_part), int(num_part[1:]))


def _pack_quarters(quarter_columns: List[Column]) -> List[Column]:
    """Атомарная упаковка (TOR v2 §4 шаг 1): квартал → 1..N слотов по высоте.

    Группы (AppTitle) атомарны — не рвутся между слотами; исключение — группа выше
    целого пустого слота разрывается по фичам (fallback). Плоский список фич упаковывается
    по высоте ячеек, а не фиксированным числом фич.
    """
    slot_height_pt = SLOT_HEIGHT_IN * 72.0
    slots: List[Column] = []
    for quarter_col in quarter_columns:
        quarter = quarter_col.quarter
        if quarter_col.grouped:
            for groups in _pack_groups(quarter_col.groups, slot_height_pt):
                slots.append(Column(quarter=quarter, groups=groups, grouped=True))
        else:
            for bullets in _pack_bullets(quarter_col.bullets, slot_height_pt):
                slots.append(Column(quarter=quarter, bullets=bullets))
    return slots


def _pack_groups(groups: List[Group], slot_height_pt: float) -> List[List[Group]]:
    """Упаковывает атомарные группы в слоты по высоте."""
    slots: List[List[Group]] = []
    current: List[Group] = []
    current_height = 0.0
    for group in groups:
        gh = estimate_group_height_pt([b.text for b in group.bullets], SLOT_WIDTH_IN, BASE_FONT_PT)
        if gh > slot_height_pt:
            # группа выше целого слота → принудительный разрыв (fallback)
            if current:
                slots.append(current)
                current = []
                current_height = 0.0
            slots.extend(_split_oversized_group(group, slot_height_pt))
        elif current and current_height + gh > slot_height_pt:
            slots.append(current)
            current = [group]
            current_height = gh
        else:
            current.append(group)
            current_height += gh
    if current:
        slots.append(current)
    return slots


def _split_oversized_group(group: Group, slot_height_pt: float) -> List[List[Group]]:
    """Разрывает слишком высокую группу на слоты по одной фиче (с тем же AppTitle)."""
    result: List[List[Group]] = []
    current: List[Group] = []
    current_height = 0.0
    for bullet in group.bullets:
        bh = estimate_bullet_height_pt(bullet.text, SLOT_WIDTH_IN, BASE_FONT_PT)
        if current and current_height + bh > slot_height_pt:
            result.append(current)
            current = []
            current_height = 0.0
        if current and current[-1].app_title == group.app_title:
            current[-1].bullets.append(bullet)
        else:
            current.append(Group(app_title=group.app_title, bullets=[bullet]))
        current_height += bh
    if current:
        result.append(current)
    return result


def _pack_bullets(bullets: List[Bullet], slot_height_pt: float) -> List[List[Bullet]]:
    """Упаковывает плоский список фич в слоты по высоте ячеек."""
    slots: List[List[Bullet]] = []
    current: List[Bullet] = []
    current_height = 0.0
    for bullet in bullets:
        bh = estimate_bullet_height_pt(bullet.text, SLOT_WIDTH_IN, BASE_FONT_PT)
        if current and current_height + bh > slot_height_pt:
            slots.append(current)
            current = []
            current_height = 0.0
        current.append(bullet)
        current_height += bh
    if current:
        slots.append(current)
    return slots


def _apply_under_approval(columns: List[Column], language: str) -> None:
    """Бейдж «под согласованием» — на первом слоте квартала, где есть такой релиз."""
    badge = get_service_string("under_approval_badge", language)
    first_of_quarter: dict = {}
    for column in columns:
        if column.quarter not in first_of_quarter:
            first_of_quarter[column.quarter] = column
        if any(is_under_approval(b.release_id) for b in _column_all_bullets(column)):
            first_of_quarter[column.quarter].under_approval_badge = badge


def _apply_group_order_and_labels(columns: List[Column]) -> None:
    for column in columns:
        if column.grouped:
            # уникальные заголовки в порядке первого появления; счёт = сумма по дублям
            titles = list(dict.fromkeys(g.app_title for g in column.groups))
            counts = {t: sum(len(g.bullets) for g in column.groups if g.app_title == t) for t in titles}
            ordered = resolve_apptitle_order([(t, counts[t]) for t in titles])
            rank = {t: i for i, t in enumerate(ordered)}
            # стабильная сортировка: неконсекутивные группы одного заголовка идут подряд
            column.groups.sort(key=lambda g: rank[g.app_title])
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
    """TOR v2 §4 шаг 2: раскладка слотов по слайдам (ровно 4 слота на слайд).

    Квартал переносится целиком (не рвётся между слайдами), кроме случая, когда квартал
    сам больше целого слайда (>4 слотов) — тогда он растягивается на несколько слайдов
    подряд, и имя квартала показывается на каждом.
    """
    runs: List[Tuple[str, List[Column]]] = []
    for col in columns:
        if runs and runs[-1][0] == col.quarter:
            runs[-1][1].append(col)
        else:
            runs.append((col.quarter, [col]))

    slides: List[RoadmapSlide] = []
    current: List[Column] = []

    def make_slide(slots: List[Column], continuation: bool) -> RoadmapSlide:
        has_stc = any(b.is_subject_to_change for col in slots for b in _column_all_bullets(col))
        footnote = get_service_string("subject_to_change_footnote", language) if has_stc else ""
        note = inheritance_note if (not continuation and inheritance_note) else ""
        return RoadmapSlide(
            product=product, stream=stream, tier=tier,
            columns=slots, continuation=continuation,
            has_subject_to_change=has_stc,
            footnote=footnote,
            inheritance_note=note,
            language=language,
        )

    def flush() -> None:
        nonlocal current
        if current:
            slides.append(make_slide(current, continuation=len(slides) > 0))
            current = []

    for _, slots in runs:
        if len(slots) > 4:
            # квартал больше целого слайда → свои слайды по 4 слота, имя квартала на каждом
            flush()
            for i in range(0, len(slots), 4):
                slides.append(make_slide(slots[i:i + 4], continuation=len(slides) > 0))
            continue
        if len(current) + len(slots) > 4:
            flush()
        current.extend(slots)
    flush()
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
                tiers.append({"name": tname})
            streams.append({"name": sname, "tiers": tiers})
        products.append({
            "name": pname,
            "inheritance_flag": get_product_inheritance_flag(pname),
            "streams": streams,
        })
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
