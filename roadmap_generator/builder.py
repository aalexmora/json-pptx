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

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from roadmap_generator import product_logos, static_slides
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

    Слоты задают только точки привязки: размеры шейпов остаются шаблонными.
    Если квартал расщеплён либо у тира есть продолжение, используется сетка 4×25%.
    """
    used_columns = len(slide.columns)
    has_subcolumns = len({column.quarter for column in slide.columns}) != used_columns
    if tier_slide_count == 1 and 1 <= used_columns <= 4 and not has_subcolumns:
        return used_columns
    return 4


def build_presentation(plan: SlidePlan) -> Presentation:
    """Рендерит план слайдов в объект `Presentation` (ещё не сохранённый)."""
    template = Presentation(select_template("roadmap", 4, False))
    master_slide = _find_master_slide(template)
    prs = Presentation()
    # размер слайда наследуется из шаблона (ТЗ v4 §10)
    prs.slide_width = template.slide_width
    prs.slide_height = template.slide_height

    blank = prs.slide_layouts[6]
    w = prs.slide_width.inches
    h = prs.slide_height.inches
    roadmap_counts = Counter(
        _roadmap_key(item) for item in plan.slides if isinstance(item, RoadmapSlide)
    )

    for item in plan.slides:
        if isinstance(item, TitleSlide):
            _render_title(prs, blank, item, w, h)
        elif isinstance(item, ThankYouSlide):
            _render_thank_you(prs, blank, item, w, h)
        elif isinstance(item, DividerSlide):
            _render_divider(prs, blank, item, w, h)
        elif isinstance(item, StaticSlide):
            _render_static(prs, blank, item, w, h)
        elif isinstance(item, RoadmapSlide):
            column_count = _rendered_column_count(item, roadmap_counts[_roadmap_key(item)])
            _render_roadmap_from_template(prs, master_slide, blank, item, w, h, column_count)
    return prs


def _find_master_slide(template_prs):
    """Первый слайд шаблона с шейпом `col_header` (иначе первый слайд)."""
    for slide in template_prs.slides:
        if any(sh.name == "col_header" for sh in slide.shapes):
            return slide
    return template_prs.slides[0] if len(template_prs.slides) else None


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
    new_slide = prs.slides.add_slide(prs.slide_layouts[6])
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
    """Возвращает брендовое имя тира для выбранной языковой версии колоды."""
    if language == "ru" and (tier == "Kaspersky Next" or tier.startswith("Kaspersky Next ")):
        return tier.replace("Kaspersky Next", "Kaspersky Symphony", 1)
    return tier


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
        _tier_display_name(slide.tier, slide.language),
    )

    # Порядковый номер слайда (слайд уже добавлен в prs — len включает его).
    number = _first_shape_for_role(text_by_name, "slide_number")
    if number is not None:
        _set_text(number, str(len(prs.slides)))

    # Логотип продукта из библиотеки (плейсхолдер logo/_logo в шаблоне).
    logo_shape = _first_shape_for_role(all_by_name, "product_logo")
    if logo_shape is not None and logo_shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        _replace_picture(new_slide, logo_shape, product_logos.logo_path(slide.product))

    # Логотип тира из библиотеки (плейсхолдер logo_tier/_logo_tier в шаблоне).
    tier_logo_shape = _first_shape_for_role(all_by_name, "tier_logo")
    if tier_logo_shape is not None and tier_logo_shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        _replace_picture(new_slide, tier_logo_shape, product_logos.tier_logo_path(slide.tier))

    header_proto = text_by_name.get("col_header")
    bullets_proto = text_by_name.get("col_bullets")
    if header_proto is None or bullets_proto is None:
        return

    # Логические слоты распределяются по ширине слайда, но размеры и взаимные
    # смещения header/bullets/marker полностью наследуются из шаблона.
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

        if marker_proto is not None:
            marker = marker_proto if i == 0 else _clone_shape(new_slide, marker_proto)
            marker.left = header.left + marker_header_offset
        # Каждая колонка, включая подколонки переполненного квартала, должна
        # оставаться самодостаточной: квартал заполняется в каждом col_header.
        header_text = col.quarter + (f"\n{col.under_approval_badge}" if col.under_approval_badge else "")
        _set_text(header, header_text)
        _fill_bullets_shape(bullets, col)

    inheritance_shapes = _text_shapes_for_role(text_shapes_by_name, "tier_inheritance_note")
    if slide.inheritance_note:
        if inheritance_shapes:
            _set_text(inheritance_shapes[0], slide.inheritance_note)
            for shape in inheritance_shapes[1:]:
                _clear(shape)
        else:
            line_count = slide.inheritance_note.count("\n") + 1
            note_height = min(1.8, max(0.45, line_count * 0.2))
            _set_paragraph(
                new_slide.shapes.add_textbox(
                    Inches(MARGIN), Inches(h - 0.5 - note_height),
                    Inches(w - 2 * MARGIN), Inches(note_height),
                ),
                slide.inheritance_note, 10, bold=False,
            )
    else:
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
    blank = prs.slide_layouts[6]
    for source_slide in source.slides:
        new_slide = prs.slides.add_slide(blank)
        for shape in source_slide.shapes:
            _append_shape(new_slide, shape)


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
        _tier_display_name(slide.tier, slide.language), TITLE_FONT_PT, bold=True,
    )

    top = 1.0
    if slide.inheritance_note:
        _set_paragraph(
            s.shapes.add_textbox(Inches(MARGIN), Inches(0.88), Inches(w - 2 * MARGIN), Inches(0.3)),
            slide.inheritance_note, 12, bold=False,
        )
        top = 1.25

    col_w = (w - 2 * MARGIN - (column_count - 1) * GAP) / column_count
    body_h = h - top - MARGIN
    x = MARGIN

    overflow: list = []
    for col in slide.columns:
        header = col.quarter + (f"\n{col.under_approval_badge}" if col.under_approval_badge else "")
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
        _tier_display_name(slide.tier, slide.language), TITLE_FONT_PT, bold=True,
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
