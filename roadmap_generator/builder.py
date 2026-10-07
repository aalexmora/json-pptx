"""Рендер `SlidePlan` в `.pptx`.

Наследует размер слайда из шаблона (ТЗ v4 §10). До появления финального
размеченного дизайн-шаблона слайды отрисовываются программно из `SlidePlan`
(публичный API python-pptx, без клонирования слайдов/приватных полей). Заполнение
именованных шейпов шаблона подключается при разметке реального шаблона (ТЗ v4 §12).
"""
from __future__ import annotations

import copy
import io
from collections import Counter, defaultdict
from datetime import date
from pathlib import PurePosixPath

from pptx import Presentation
from pptx.enum.dml import MSO_FILL_TYPE
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.packuri import PackURI
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from roadmap_generator import product_logos, static_slides, tier_names
from roadmap_generator.layout import fit_bullets_dynamic
from roadmap_generator.strings import get_service_string
from roadmap_generator.plugins_engine import (
    DividerSlide,
    RoadmapSlide,
    SlidePlan,
    StaticSlide,
    ThankYouSlide,
    TitleSlide,
)
from roadmap_generator.template_registry import (
    get_layout_shape_names,
    get_role_shape_names,
    get_slide_type_markers,
    placeholder_names,
    select_template,
)

MARGIN = 0.5
GAP = 0.25
BASE_FONT_PT = 14
EYEBROW_FONT_PT = 12
TITLE_FONT_PT = 20
HEADER_FONT_PT = 14

# Все известные плейсхолдеры шаблона (с префиксом «_» и без) — читаются из
# template_contracts.yaml. Базовые (без «_») используются для распознавания:
# шейп «_roadmap» — это плейсхолдер «roadmap».
_PLACEHOLDER_NAMES = set(placeholder_names())
_PLACEHOLDER_BASE = {n for n in _PLACEHOLDER_NAMES if not n.startswith("_")}


def _roadmap_key(slide: RoadmapSlide) -> tuple[str, str, str]:
    return (slide.product, slide.stream, slide.tier)


def _rendered_column_count(slide: RoadmapSlide, tier_slide_count: int) -> int:
    """Число равных логических слотов: адаптивно для простого roadmap.

    Одиночная колонка всегда занимает всю ширину. Если квартал расщеплён либо у
    тира есть продолжение с несколькими колонками, используется сетка 4×25%.
    """
    used_columns = len(slide.columns)
    if used_columns == 1:
        return 1
    has_subcolumns = len({column.quarter for column in slide.columns}) != used_columns
    if tier_slide_count == 1 and 1 <= used_columns <= 4 and not has_subcolumns:
        return used_columns
    return 4


def build_presentation(plan: SlidePlan) -> Presentation:
    """Рендерит план слайдов в объект `Presentation` (ещё не сохранённый)."""
    template = Presentation(select_template("roadmap", 4, False))
    template_slides = _find_template_slides(template)
    prs = Presentation()
    # размер слайда наследуется из шаблона (ТЗ v4 §10)
    prs.slide_width = template.slide_width
    prs.slide_height = template.slide_height

    # Все создаваемые слайды должны сохранять layout/master загруженного PPTX.
    # Partname исходного пакета получает уникальный суффикс, чтобы его layout,
    # master и theme не конфликтовали с одноимёнными частями нового пакета.
    _namespace_source_package(template, prs, "roadmap_template")

    roadmap_template_slide = template_slides.get("roadmap")
    template_layout = (
        roadmap_template_slide.slide_layout
        if roadmap_template_slide is not None
        else template.slide_layouts[0]
    )
    w = prs.slide_width.inches
    h = prs.slide_height.inches
    roadmap_counts = Counter(
        _roadmap_key(item) for item in plan.slides if isinstance(item, RoadmapSlide)
    )

    current_product = ""
    for item_index, item in enumerate(plan.slides):
        if isinstance(item, TitleSlide):
            _render_title(prs, template_layout, item, w, h)
        elif isinstance(item, ThankYouSlide):
            _render_thank_you(prs, template_layout, item, w, h)
        elif isinstance(item, DividerSlide):
            if item.divider_type == "product":
                current_product = item.title
            else:
                current_product = _next_roadmap_product(plan.slides, item_index) or current_product
            source = template_slides.get(item.divider_type)
            if source is None:
                _render_divider(prs, template_layout, item, w, h)
            else:
                _render_divider_from_template(prs, source, item, current_product)
        elif isinstance(item, StaticSlide):
            _render_static(prs, template_layout, item, w, h)
        elif isinstance(item, RoadmapSlide):
            column_count = _rendered_column_count(item, roadmap_counts[_roadmap_key(item)])
            _render_roadmap_from_template(
                prs, roadmap_template_slide, template_layout, item, w, h, column_count,
            )
    _clear_retired_inheritance_placeholders(prs)
    _fill_global_placeholders(prs)
    return prs


def _namespace_source_package(source: Presentation, target: Presentation, token: str) -> None:
    """Даёт частям внешнего PPTX уникальные имена перед подключением layout.

    `slides.add_slide(source_slide.slide_layout)` — публичный API python-pptx,
    который сохраняет relationship к исходным layout/master/theme. Без смены
    partname стандартные имена вроде `slideLayout1.xml` конфликтуют с частями
    целевого пакета. Relationships остаются объектными и при сохранении сами
    получают корректные относительные Target.
    """
    used = {str(part.partname) for part in target.part.package.iter_parts()}
    for part in list(source.part.package.iter_parts()):
        original = PurePosixPath(str(part.partname))
        candidate = original.with_name(f"{original.stem}_{token}{original.suffix}")
        sequence = 2
        while str(candidate) in used:
            candidate = original.with_name(
                f"{original.stem}_{token}_{sequence}{original.suffix}"
            )
            sequence += 1
        part.partname = PackURI(str(candidate))
        used.add(str(candidate))


def _fill_global_placeholders(prs: Presentation, today: date | None = None) -> None:
    """Заполняет общие плейсхолдеры даты и номера на каждом слайде."""
    current = today or date.today()
    values = {
        "roadmap_year": f"{current:%Y}",
        "roadmap_version": f"Version {current:%d.%m.%y}",
    }
    for ordinal, slide in enumerate(prs.slides, start=1):
        text_shapes_by_name: dict[str, list] = defaultdict(list)
        for shape in slide.shapes:
            if shape.has_text_frame:
                text_shapes_by_name[_normalize_name(shape.name)].append(shape)
        for role, value in values.items():
            for shape in _text_shapes_for_role(text_shapes_by_name, role):
                _set_text(shape, value)
        for shape in _text_shapes_for_role(text_shapes_by_name, "slide_number"):
            _set_text(shape, str(ordinal))


def _clear_retired_inheritance_placeholders(prs: Presentation) -> None:
    """Удаляет текст legacy-наследования со всех типов слайдов."""
    for slide in prs.slides:
        text_shapes_by_name: dict[str, list] = {}
        for shape in slide.shapes:
            if shape.has_text_frame:
                text_shapes_by_name.setdefault(_normalize_name(shape.name), []).append(shape)
        for shape in _text_shapes_for_role(text_shapes_by_name, "tier_inheritance_note"):
            _clear(shape)


def _next_roadmap_product(items: list, current_index: int) -> str:
    """Имя Product для Stream-разделителя, даже если Product-слайд скрыт."""
    for candidate in items[current_index + 1:]:
        if isinstance(candidate, RoadmapSlide):
            return candidate.product
        if isinstance(candidate, DividerSlide) and candidate.divider_type == "product":
            break
    return ""


def _find_template_slides(template_prs) -> dict:
    """Находит Product/Stream/Roadmap-слайды по маркерам из YAML.

    Без маркеров Roadmap берётся с первого слайда с `col_header`,
    а Product/Stream по-прежнему рисуются кодом.
    """
    found = {}
    for slide in template_prs.slides:
        names = {shape.name for shape in slide.shapes}
        for slide_type in ("product", "stream", "roadmap"):
            if names.intersection(get_slide_type_markers(slide_type)):
                found.setdefault(slide_type, slide)
    if "roadmap" not in found:
        for slide in template_prs.slides:
            if any(sh.name == "col_header" for sh in slide.shapes):
                found["roadmap"] = slide
                break
    if "roadmap" not in found and len(template_prs.slides):
        found["roadmap"] = template_prs.slides[0]
    return found


def _first_blip_r_id(shape):
    """Первый `r:embed`/`r:link` в дереве blip (включая SVG-расширение `asvg:svgBlip`)."""
    try:
        blip = shape._element.blipFill.blip
    except AttributeError:
        return None
    if blip is None:
        return None
    for el in blip.iter():
        for attr in (qn("r:embed"), qn("r:link")):
            r_id = el.get(attr)
            if r_id:
                return r_id
    return None


def _picture_blob(shape):
    """Байты картинки шейпа: встроенной или связанной (`r:link` на локальный файл).

    `shape.image.blob` падает, когда ссылка на образ живёт не на самом `a:blip`
    (связанная картинка или SVG-расширение `asvg:svgBlip`) — тогда blob достаём
    через relationship. Если и это не удалось — возвращает None.
    """
    try:
        return shape.image.blob
    except ValueError:
        pass
    r_id = _first_blip_r_id(shape)
    if not r_id:
        return None
    try:
        return shape.part.related_part(r_id).blob
    except (KeyError, NotImplementedError, OSError, ValueError):
        return None


def _copy_picture_with_media_part(new_slide, shape):
    """Переносит картинку вместе с медиа-part (SVG и прочие не-растровые).

    `add_picture` умеет только растр; для остальных создаём в целевом пакете
    новый part, связываем слайд с ним и подменяем rId на скопированном элементе.
    """
    r_id = _first_blip_r_id(shape)
    if not r_id:
        return False
    try:
        src_part = shape.part.related_part(r_id)
    except (KeyError, ValueError):
        return False
    blob = src_part.blob
    if not blob:
        return False
    pkg = new_slide.part.package
    ext = (src_part.partname.ext or ".svg").lstrip(".")
    media_part = Part(pkg.next_media_partname(ext), src_part.content_type, pkg, blob)
    new_r_id = new_slide.part.relate_to(media_part, RT.IMAGE)

    el = copy.deepcopy(shape._element)
    for sub in el.blipFill.blip.iter():
        for attr in (qn("r:embed"), qn("r:link")):
            if sub.get(attr) == r_id:
                sub.set(attr, new_r_id)
    new_slide.shapes._spTree.append(el)
    return True


def _append_shape(new_slide, shape):
    """Копирует шейп на слайд, пересоздавая картинки через add_picture.

    Растровые картинки перевстраиваются; SVG и прочие не-растровые переносятся
    как media part; если образ недоступен вовсе — копируем XML как есть.
    """
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        blob = _picture_blob(shape)
        if blob is not None:
            try:
                pic = new_slide.shapes.add_picture(
                    io.BytesIO(blob), shape.left, shape.top, shape.width, shape.height,
                )
                pic.name = shape.name
                return
            except (ValueError, OSError):
                if _copy_picture_with_media_part(new_slide, shape):
                    return
    new_slide.shapes._spTree.append(copy.deepcopy(shape._element))


def _is_skipped(shape) -> bool:
    """Сервисные шейпы с префиксом «_» в слайд не копируются — кроме плейсхолдеров.

    Префикс «_» = сервисный/направляющий (не попадает в слайд), НО если имя после
    «_» совпадает с известным плейсхолдером («_roadmap», «_logo», «_dot», «_s2c»,
    «_number») — шейп копируется и обрабатывается билдером.
    """
    name = shape.name
    if not name.startswith("_"):
        return False
    return name[1:] not in _PLACEHOLDER_BASE


def _normalize_name(name: str) -> str:
    """«_roadmap» → «roadmap»: префикс «_» не мешает поиску плейсхолдера."""
    if name.startswith("_") and name[1:] in _PLACEHOLDER_BASE:
        return name[1:]
    return name


def _first_shape_for_role(shapes_by_name: dict, role: str):
    for name in get_role_shape_names(role):
        shape = shapes_by_name.get(name)
        if shape is not None:
            return shape
    return None


def _text_shapes_for_role(text_shapes_by_name: dict, role: str) -> list:
    return [
        shape
        for name in get_role_shape_names(role)
        for shape in text_shapes_by_name.get(name, [])
    ]


def _replace_picture(new_slide, shape, path) -> bool:
    """Подменяет картинку-шейп картинкой из файла `path`.

    Возвращает True, если подставилось. Сохраняет позицию, размер и z-order
    исходного шейпа. Если файла нет — шейп шаблона остаётся как есть.
    """
    if path is None:
        return False
    try:
        pic = new_slide.shapes.add_picture(
            io.BytesIO(path.read_bytes()), shape.left, shape.top, shape.width, shape.height,
        )
    except (ValueError, OSError):
        return False
    sp = shape._element
    parent = sp.getparent()
    index = list(parent).index(sp)
    parent.remove(sp)
    parent.insert(index, pic._element)
    return True


def _clone_slide(prs, source_slide):
    """Клонирует слайд шаблона в целевую презентацию (картинки — через add_picture)."""
    new_slide = prs.slides.add_slide(source_slide.slide_layout)
    for shape in source_slide.shapes:
        if _is_skipped(shape):
            continue
        _append_shape(new_slide, shape)
    return new_slide


def _base_format(tf):
    """Формат (размер, имя шрифта, жирность, RGB-цвет) первого run'а — для сохранения стиля."""
    if tf.paragraphs and tf.paragraphs[0].runs:
        r = tf.paragraphs[0].runs[0]
        color = None
        try:
            if r.font.color and r.font.color.rgb:
                color = r.font.color.rgb
        except Exception:
            color = None
        return (
            r.font.size.pt if r.font.size else None,
            r.font.name,
            r.font.bold,
            color,
        )
    return None, None, None, None


def _paragraph_format(paragraph):
    """Формат первого run конкретного абзаца шаблона."""
    if not paragraph.runs:
        return None, None, None, None
    run = paragraph.runs[0]
    color = None
    try:
        if run.font.color and run.font.color.rgb:
            color = run.font.color.rgb
    except Exception:
        color = None
    return (
        run.font.size.pt if run.font.size else None,
        run.font.name,
        run.font.bold,
        color,
    )


def _paragraph_has_native_bullet(paragraph) -> bool:
    """Есть ли у абзаца шаблона нативный маркер PowerPoint."""
    properties = paragraph._p.pPr
    if properties is None:
        return False
    return any(
        properties.find(qn(tag)) is not None
        for tag in ("a:buChar", "a:buAutoNum", "a:buBlip")
    )


def _apply_format(run, size, name, bold, color):
    if size:
        run.font.size = Pt(size)
    if name:
        run.font.name = name
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _set_text(shape, text: str) -> None:
    if shape is None:
        return
    tf = shape.text_frame
    size, name, bold, color = _base_format(tf)
    tf.text = text
    for paragraph in tf.paragraphs:
        for run in paragraph.runs:
            _apply_format(run, size, name, bold, color)


def _clear(shape) -> None:
    if shape is not None:
        shape.text_frame.text = ""


def _fill_bullets_shape(shape, col) -> None:
    if shape is None:
        return
    tf = shape.text_frame
    tf.word_wrap = True
    source_paragraphs = list(tf.paragraphs)
    header_source = source_paragraphs[0]
    feature_source = source_paragraphs[1] if len(source_paragraphs) > 1 else header_source
    prototypes = {
        "header": (
            copy.deepcopy(header_source._p),
            _paragraph_format(header_source),
            _paragraph_has_native_bullet(header_source),
        ),
        "feature": (
            copy.deepcopy(feature_source._p),
            _paragraph_format(feature_source),
            _paragraph_has_native_bullet(feature_source),
        ),
    }

    paragraphs: list[tuple[str, str]] = []
    if col.grouped:
        for group in col.groups:
            paragraphs.append((group.app_title, "header"))
            for b in group.bullets:
                paragraphs.append((_template_feature_text(b, prototypes["feature"]), "feature"))
    else:
        for b in col.bullets:
            paragraphs.append((_template_feature_text(b, prototypes["feature"]), "feature"))

    if not paragraphs:
        tf.text = ""
        return

    # Разрешённое исключение ТЗ v4 §10: клонируем XML абзацев-прототипов,
    # чтобы сохранить раздельные paragraph styles заголовка группы и фичи.
    tf.clear()
    empty_paragraph = tf.paragraphs[0]._p
    cursor = empty_paragraph
    for _, kind in paragraphs:
        paragraph_xml = copy.deepcopy(prototypes[kind][0])
        cursor.addnext(paragraph_xml)
        cursor = paragraph_xml
    empty_paragraph.getparent().remove(empty_paragraph)

    for paragraph, (text, kind) in zip(tf.paragraphs, paragraphs):
        paragraph.text = text
        size, name, bold, color = prototypes[kind][1]
        for run in paragraph.runs:
            _apply_format(run, size, name, bold, color)


def _template_feature_text(bullet, feature_prototype) -> str:
    """Текст фичи без двойного маркера, если bullet уже задан в шаблоне."""
    _, _, native_bullet = feature_prototype
    prefix = "" if native_bullet else "• "
    suffix = " *" if bullet.is_subject_to_change else ""
    return f"{prefix}{bullet.text}{suffix}"


def _tier_display_name(tier: str, language: str) -> str:
    """Возвращает настроенное в интерфейсе имя или исходное имя тира."""
    return tier_names.get_tier_name(tier, language)


def _roadmap_display_name(slide: RoadmapSlide) -> str:
    """Заголовок Roadmap: Tier, затем Stream, затем Product."""
    if slide.tier and slide.tier != "-":
        return _tier_display_name(slide.tier, slide.language)
    if slide.stream and slide.stream != "-":
        return slide.stream
    return slide.product


def _render_roadmap_from_template(
    prs,
    master_slide,
    blank,
    slide: RoadmapSlide,
    w: float,
    h: float,
    column_count: int,
) -> None:
    if master_slide is None:
        _render_roadmap(prs, blank, slide, w, h, column_count)
        return
    new_slide = _clone_slide(prs, master_slide)

    # Поиск плейсхолдеров без учёта префикса «_»: «_roadmap» == «roadmap».
    # setdefault — первый встреченный шейп (прототип), чтобы дубли не ломали вёрстку.
    all_by_name: dict = {}
    text_by_name: dict = {}
    text_shapes_by_name: dict = defaultdict(list)
    for sh in new_slide.shapes:
        norm = _normalize_name(sh.name)
        all_by_name.setdefault(norm, sh)
        if sh.has_text_frame:
            text_by_name.setdefault(norm, sh)
            text_shapes_by_name[norm].append(sh)

    product_name = _first_shape_for_role(text_by_name, "product_name")
    if product_name is not None:
        _set_text(product_name, slide.product)

    # На continuation-слайде скрываем только eyebrow. Название тира обязательно
    # повторяется: ни один roadmap-слайд не должен оставаться без slide_title.
    if slide.continuation:
        _clear(text_by_name.get("eyebrow"))
    else:
        eyebrow = get_service_string("roadmap_title", slide.language)
        _set_text(text_by_name.get("eyebrow"), eyebrow)
    _set_text(
        text_by_name.get("slide_title"),
        _roadmap_display_name(slide),
    )

    # Порядковый номер слайда (слайд уже добавлен в prs — len включает его).
    number = _first_shape_for_role(text_by_name, "slide_number")
    if number is not None:
        _set_text(number, str(len(prs.slides)))

    # Логотип тира из библиотеки (плейсхолдер logo_tier/_logo_tier в шаблоне).
    tier_logo_shape = _first_shape_for_role(all_by_name, "tier_logo")
    if tier_logo_shape is not None and tier_logo_shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        tier_key = product_logos.tier_logo_key(slide.product, slide.tier)
        _replace_picture(new_slide, tier_logo_shape, product_logos.tier_logo_path(tier_key))

    header_proto = text_by_name.get("col_header")
    bullets_proto = text_by_name.get("col_bullets")
    if header_proto is None or bullets_proto is None:
        return

    # Логические слоты распределяются по ширине слайда. Одиночная колонка
    # получает colspan на всю доступную ширину; остальные сохраняют размеры
    # прототипов шаблона и меняют только точки привязки.
    slot_width_in = (w - 2 * MARGIN) / column_count
    header_left = header_proto.left
    bullets_left = bullets_proto.left
    marker_proto = _first_shape_for_role(all_by_name, "quarter_marker")
    marker_header_offset = marker_proto.left - header_left if marker_proto is not None else 0
    _position_column_separators(all_by_name, column_count, w)

    for i, col in enumerate(slide.columns):
        if i == 0:
            header, bullets = header_proto, bullets_proto
        else:
            header = _clone_shape(new_slide, header_proto)
            bullets = _clone_shape(new_slide, bullets_proto)
        offset = Inches(i * slot_width_in)
        header.left = header_left + offset
        bullets.left = bullets_left + offset
        if column_count == 1:
            header.width = Inches(w - MARGIN) - header.left
            bullets.width = Inches(w - MARGIN) - bullets.left

        first_column_for_quarter = i == 0 or slide.columns[i - 1].quarter != col.quarter
        if marker_proto is not None and first_column_for_quarter:
            marker = marker_proto if i == 0 else _clone_shape(new_slide, marker_proto)
            marker.left = header.left + marker_header_offset
        # Подколонки одного квартала не дублируют его заголовок.
        header_text = (
            col.quarter + (f"\n{col.under_approval_badge}" if col.under_approval_badge else "")
            if first_column_for_quarter
            else ""
        )
        _set_text(header, header_text)
        _fill_bullets_shape(bullets, col)

    # Наследование Tier выведено из использования. Очищаем legacy-плейсхолдеры,
    # чтобы старый шаблон не показывал текст-заглушку.
    inheritance_shapes = _text_shapes_for_role(text_shapes_by_name, "tier_inheritance_note")
    for shape in inheritance_shapes:
        _clear(shape)

    # Сноска Subject to Change — показывается ОДИН раз в шейпе s2c/_s2c.
    # Текстовый блок поверх — только если такого плейсхолдера в шаблоне нет.
    s2c_shapes = _text_shapes_for_role(text_shapes_by_name, "subject_to_change_footnote")
    if s2c_shapes:
        if slide.footnote:
            _set_text(s2c_shapes[0], slide.footnote)
            for shape in s2c_shapes[1:]:
                _clear(shape)
        else:
            for shape in s2c_shapes:
                _clear(shape)
    elif slide.footnote:
        _set_paragraph(
            new_slide.shapes.add_textbox(Inches(MARGIN), Inches(h - 0.45), Inches(w - 2 * MARGIN), Inches(0.3)),
            slide.footnote, 10, bold=False,
        )


def _position_column_separators(all_by_name: dict, column_count: int, slide_width_in: float) -> None:
    """Ставит именованные разделители на границы колонок, лишние уводит за слайд."""
    separator_names = get_layout_shape_names("separators")
    slot_width_in = (slide_width_in - 2 * MARGIN) / column_count
    for index, name in enumerate(separator_names):
        separator = all_by_name.get(name)
        if separator is None:
            continue
        if index < column_count - 1:
            separator.left = Inches(MARGIN + (index + 1) * slot_width_in)
        else:
            separator.left = Inches(slide_width_in + 1)


def _clone_shape(slide, source_shape):
    """Клонирует фигуру в слайд (deepcopy + _spTree) и возвращает новый Shape."""
    slide.shapes._spTree.append(copy.deepcopy(source_shape._element))
    return list(slide.shapes)[-1]


def _render_static(prs, layout, slide: StaticSlide, w: float, h: float) -> None:
    if slide.pptx:
        path = static_slides.static_slide_pptx_path(slide.pptx)
        if path.exists():
            _copy_slides_from(prs, str(path))
            return
    s = prs.slides.add_slide(layout)
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.6), Inches(w - 2 * MARGIN), Inches(0.8)),
        slide.name, 28, bold=True,
    )


def _copy_slides_from(prs, source_path: str) -> None:
    """Копирует слайды `.pptx`-заготовки в целевую презентацию.

    Картинки пересоздаются через публичный `add_picture` (с их blob'ом), чтобы не
    было «битых» ссылок; остальные шейпы — `copy.deepcopy` + `_spTree`.
    """
    source = Presentation(source_path)
    _namespace_source_package(source, prs, f"static_{len(prs.slides) + 1}")
    for source_slide in source.slides:
        new_slide = prs.slides.add_slide(source_slide.slide_layout)
        _copy_slide_background(source_slide, new_slide)
        for shape in source_slide.shapes:
            _append_shape(new_slide, shape)


def _copy_slide_background(source_slide, target_slide) -> None:
    """Сохраняет явный одноцветный фон статичного слайда публичным API."""
    if source_slide.follow_master_background:
        return
    source_fill = source_slide.background.fill
    if source_fill.type != MSO_FILL_TYPE.SOLID:
        return
    target_fill = target_slide.background.fill
    target_fill.solid()
    if source_fill.fore_color.rgb is not None:
        target_fill.fore_color.rgb = source_fill.fore_color.rgb
    elif source_fill.fore_color.theme_color is not None:
        target_fill.fore_color.theme_color = source_fill.fore_color.theme_color
        target_fill.fore_color.brightness = source_fill.fore_color.brightness


def _render_title(prs, layout, slide: TitleSlide, w: float, h: float) -> None:
    s = prs.slides.add_slide(layout)
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(h / 2 - 0.9), Inches(w - 2 * MARGIN), Inches(1.2)),
        slide.title or "Roadmap", 40, bold=True, align=PP_ALIGN.CENTER,
    )
    subtitle = " ".join(x for x in (slide.year, slide.version) if x)
    if subtitle:
        _set_paragraph(
            s.shapes.add_textbox(Inches(MARGIN), Inches(h / 2 + 0.4), Inches(w - 2 * MARGIN), Inches(0.5)),
            subtitle, 18, bold=False, align=PP_ALIGN.CENTER,
        )


def _render_thank_you(prs, layout, slide: ThankYouSlide, w: float, h: float) -> None:
    s = prs.slides.add_slide(layout)
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(h / 2 - 0.6), Inches(w - 2 * MARGIN), Inches(1.2)),
        slide.text, 40, bold=True, align=PP_ALIGN.CENTER,
    )


def _render_divider(prs, layout, slide: DividerSlide, w: float, h: float) -> None:
    s = prs.slides.add_slide(layout)
    label = "PRODUCT" if slide.divider_type == "product" else "STREAM"

    title = s.shapes.add_textbox(Inches(MARGIN), Inches(h / 2 - 0.7), Inches(w - 2 * MARGIN), Inches(1.2))
    _set_paragraph(title, slide.title, 40, bold=True, align=PP_ALIGN.CENTER)

    sub = s.shapes.add_textbox(Inches(MARGIN), Inches(h / 2 + 0.6), Inches(w - 2 * MARGIN), Inches(0.4))
    _set_paragraph(sub, label, 14, bold=False, align=PP_ALIGN.CENTER)


def _render_divider_from_template(prs, source_slide, slide: DividerSlide, product: str) -> None:
    """Клонирует Product/Stream-слайд и заполняет его заголовки."""
    new_slide = _clone_slide(prs, source_slide)
    text_by_name = {
        _normalize_name(shape.name): shape
        for shape in new_slide.shapes
        if shape.has_text_frame
    }
    if slide.divider_type == "product":
        _set_text(_first_shape_for_role(text_by_name, "product_name"), slide.title)
        all_by_name = {_normalize_name(shape.name): shape for shape in new_slide.shapes}
        image_shape = _first_shape_for_role(all_by_name, "product_slide_image")
        if image_shape is None:
            image_shape = _first_shape_for_role(all_by_name, "product_logo")
        if image_shape is not None and image_shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            _replace_picture(
                new_slide,
                image_shape,
                product_logos.product_slide_image_path(slide.title),
            )
    else:
        _set_text(_first_shape_for_role(text_by_name, "stream_name"), slide.title)
        _set_text(_first_shape_for_role(text_by_name, "product_name"), product)
    number = _first_shape_for_role(text_by_name, "slide_number")
    if number is not None:
        _set_text(number, str(len(prs.slides)))


def _render_roadmap(
    prs,
    layout,
    slide: RoadmapSlide,
    w: float,
    h: float,
    column_count: int,
) -> None:
    s = prs.slides.add_slide(layout)

    eyebrow = get_service_string("roadmap_cont_title" if slide.continuation else "roadmap_title", slide.language)
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.15), Inches(w - 2 * MARGIN), Inches(0.3)),
        eyebrow, EYEBROW_FONT_PT, bold=False,
    )
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.42), Inches(w - 2 * MARGIN), Inches(0.45)),
        _roadmap_display_name(slide), TITLE_FONT_PT, bold=True,
    )

    top = 1.0

    col_w = (w - 2 * MARGIN - (column_count - 1) * GAP) / column_count
    body_h = h - top - MARGIN
    x = MARGIN

    overflow: list = []
    for index, col in enumerate(slide.columns):
        first_column_for_quarter = index == 0 or slide.columns[index - 1].quarter != col.quarter
        header = (
            col.quarter + (f"\n{col.under_approval_badge}" if col.under_approval_badge else "")
            if first_column_for_quarter
            else ""
        )
        _set_paragraph(
            s.shapes.add_textbox(Inches(x), Inches(top), Inches(col_w), Inches(0.5)),
            header, HEADER_FONT_PT, bold=True,
        )
        body_top = top + 0.55
        box = s.shapes.add_textbox(Inches(x), Inches(body_top), Inches(col_w), Inches(body_h - 0.55))
        overflow.extend(_fill_column_body(box, col, body_h - 0.55, col_w))
        x += col_w + GAP

    if slide.footnote:
        _set_paragraph(
            s.shapes.add_textbox(Inches(MARGIN), Inches(h - 0.45), Inches(w - 2 * MARGIN), Inches(0.35)),
            slide.footnote, 10, bold=False,
        )

    if overflow:
        _render_overflow(prs, layout, slide, overflow, w, h)


def _fill_column_body(box, col, body_h_in: float, col_w_in: float) -> list:
    bullets = _column_bullets(col)
    texts = [b.text for b in bullets]
    font_pt, fitting, overflow = fit_bullets_dynamic(texts, body_h_in, col_w_in, BASE_FONT_PT)
    fit_count = len(fitting)

    tf = box.text_frame
    tf.word_wrap = True
    written = 0

    def add(text: str, bold: bool) -> None:
        nonlocal written
        p = tf.paragraphs[0] if written == 0 else tf.add_paragraph()
        _style_paragraph(p, text, font_pt, bold=bold)
        written += 1

    remaining = fit_count
    if col.grouped:
        for group in col.groups:
            if remaining <= 0:
                break
            take = min(len(group.bullets), remaining)
            if take == 0:
                continue
            add(group.app_title, True)
            for bullet in group.bullets[:take]:
                add(_bullet_text(bullet), False)
            remaining -= take
    else:
        for bullet in bullets[:fit_count]:
            add(_bullet_text(bullet), False)

    return overflow


def _bullet_text(bullet) -> str:
    text = f"• {bullet.text}"
    if bullet.is_subject_to_change:
        text += " *"
    return text


def _render_overflow(prs, layout, slide: RoadmapSlide, overflow: list, w: float, h: float) -> None:
    s = prs.slides.add_slide(layout)
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.15), Inches(w - 2 * MARGIN), Inches(0.3)),
        get_service_string("roadmap_cont_title", slide.language), EYEBROW_FONT_PT, bold=False,
    )
    _set_paragraph(
        s.shapes.add_textbox(Inches(MARGIN), Inches(0.42), Inches(w - 2 * MARGIN), Inches(0.45)),
        _roadmap_display_name(slide), TITLE_FONT_PT, bold=True,
    )
    box = s.shapes.add_textbox(Inches(MARGIN), Inches(1.0), Inches(w - 2 * MARGIN), Inches(h - 1.5))
    tf = box.text_frame
    tf.word_wrap = True
    for i, text in enumerate(overflow):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        _style_paragraph(p, f"• {text}", BASE_FONT_PT, bold=False)


def _column_bullets(col):
    if col.grouped:
        out = []
        for group in col.groups:
            out.extend(group.bullets)
        return out
    return col.bullets


def _set_paragraph(box, text: str, size: int, bold: bool, align=None) -> None:
    tf = box.text_frame
    tf.word_wrap = True
    tf.text = text
    p = tf.paragraphs[0]
    if align is not None:
        p.alignment = align
    _style_paragraph(p, text, size, bold)


def _style_paragraph(p, text: str, size: int, bold: bool) -> None:
    p.text = text
    for run in p.runs:
        run.font.size = Pt(size)
        run.font.bold = bold
