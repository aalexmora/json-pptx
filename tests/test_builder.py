"""Тесты для `roadmap_generator/builder.py` (структурная проверка рендера)."""
from __future__ import annotations

import io
import posixpath
import zipfile
from datetime import date
from xml.etree import ElementTree as ET

import pytest
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from roadmap_generator import ordering, static_slides, tier_names
from roadmap_generator.builder import (
    _bullet_text,
    _template_feature_text,
    build_presentation,
)
from plugins._base import Bullet
from roadmap_generator.plugins_engine import (
    RoadmapSlide,
    SlidePlan,
    StaticSlide,
    ThankYouSlide,
    TitleSlide,
    build_slide_plan,
)
from roadmap_generator.schema import normalize_roadmap
from roadmap_generator.template_registry import get_layout_shape_names

# 1x1 прозрачный PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415478da63f8cfc0f01f0005000182a1e6b70000000049454e44ae426082"
)
# 10x10 красный SVG
SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    b'<rect width="10" height="10" fill="red"/></svg>'
)
# namespace asvg (SVG-расширение blip)
NS_ASVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"


def _make_template(tmp_path, name, add_picture=None, skip_name=None):
    """Собирает шаблон с обязательными шейпами и опциональной картинкой/сервис-шейпом."""
    tpl = Presentation()
    tpl.slide_width = Inches(13.333)
    tpl.slide_height = Inches(7.5)
    slide = tpl.slides.add_slide(tpl.slide_layouts[6])
    header = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(3), Inches(0.4))
    header.name = "col_header"
    bullets = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(2.9), Inches(5))
    bullets.name = "col_bullets"
    if add_picture:
        add_picture(slide)
    if skip_name:
        guide = slide.shapes.add_textbox(Inches(0.5), Inches(6.0), Inches(3), Inches(0.4))
        guide.name = skip_name
        guide.text_frame.text = "THIS SHOULD NOT APPEAR"
    path = tmp_path / name
    tpl.save(str(path))
    return str(path)


def _plan(load_fixture, name: str):
    return build_slide_plan(normalize_roadmap(load_fixture(name), language="ru"), {})


def _slide_text(slide) -> str:
    chunks = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _all_texts(prs) -> list:
    return [_slide_text(s) for s in prs.slides]


def _assert_no_dangling_package_relationships(path) -> None:
    """Каждая внутренняя OOXML relationship должна вести в существующий part."""
    relationship_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for rels_name in (name for name in names if name.endswith(".rels")):
            if rels_name == "_rels/.rels":
                source_part = ""
            else:
                directory, rels_file = posixpath.split(rels_name)
                source_directory = posixpath.dirname(directory)
                source_part = posixpath.join(source_directory, rels_file[:-5])
            relationships = ET.fromstring(archive.read(rels_name))
            for relationship in relationships.findall(f"{{{relationship_ns}}}Relationship"):
                if relationship.get("TargetMode") == "External":
                    continue
                target = relationship.get("Target")
                assert target
                resolved = (
                    posixpath.normpath(target.lstrip("/"))
                    if target.startswith("/")
                    else posixpath.normpath(
                        posixpath.join(posixpath.dirname(source_part), target)
                    )
                )
                assert resolved in names, f"{rels_name}: missing {resolved}"


def _sparse_quarters_data(quarter_count: int) -> list:
    months = [1, 4, 7, 10][:quarter_count]
    releases = []
    for index, month in enumerate(months, start=1):
        releases.append({
            "Id": index,
            "AppTitle": f"Application {index}",
            "TrDate": f"15.{month:02d}.2026 21:00:00",
            "Requirements": [{
                "Id": 1000 + index,
                "Kbr": "Yes",
                "MarketingTitle": f"Feature {index}",
            }],
        })
    return [{
        "Product": "Product",
        "Streams": [{
            "Stream": "Stream",
            "Tiers": [{"Tier": "Tier", "Releases": releases}],
        }],
    }]


def test_pagination_slide_count(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    # титульный + product + stream + 2 roadmap + спасибо = 6
    assert len(prs.slides) == 6


def test_single_column_continuation_spans_full_slide(load_fixture, synthetic_template_path):
    plan = _plan(load_fixture, "pagination_5_quarters.json")
    prs = build_presentation(plan)
    roadmap_slides = [
        slide for slide in prs.slides
        if any(shape.name == "col_header" for shape in slide.shapes)
    ]
    assert len(roadmap_slides) == 2
    continuation_bodies = [
        shape for shape in roadmap_slides[1].shapes if shape.name == "col_bullets"
    ]
    assert len(continuation_bodies) == 1
    assert continuation_bodies[0].width.inches == pytest.approx(
        prs.slide_width.inches - continuation_bodies[0].left.inches - 0.5
    )


def test_dividers_render_titles(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    texts = _all_texts(prs)
    assert any("PRODUCT" in t and "Kaspersky Next" in t for t in texts)
    assert any("STREAM" in t and "Kaspersky Next Optimum" in t for t in texts)


def test_roadmap_title_falls_back_to_product_when_stream_and_tier_are_dash(
    synthetic_template_path,
):
    data = [{
        "Product": "Standalone Product",
        "Streams": [{"Stream": "-", "Tiers": [{"Tier": "-", "Releases": [{
            "Id": 1,
            "AppTitle": "Standalone Product",
            "TrDate": "15.01.2026 21:00:00",
            "Requirements": [{"Id": 11, "Kbr": "Yes", "MarketingTitle": "Feature A"}],
        }]}]}],
    }]

    prs = build_presentation(build_slide_plan(normalize_roadmap(data, language="ru"), {}))
    slide = _roadmap_slide(prs)

    assert slide is not None
    assert "Standalone Product" in _slide_text(slide)
    assert "Feature A" in _slide_text(slide)


def test_three_slide_template_clones_product_stream_artwork_and_fills_names(
    load_fixture, tmp_path, monkeypatch,
):
    tpl = Presentation()
    tpl.slide_width = Inches(13.333)
    tpl.slide_height = Inches(7.5)
    blank = tpl.slide_layouts[6]

    product_slide = tpl.slides.add_slide(blank)
    product_marker = product_slide.shapes.add_textbox(Inches(0), Inches(0), Inches(0.1), Inches(0.1))
    product_marker.name = "_slide_type_product"
    product_name = product_slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
    product_name.name = "product_name"
    product_name.text_frame.text = "PRODUCT PLACEHOLDER"
    product_art = product_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(10), Inches(1), Inches(2), Inches(2))
    product_art.name = "product_artwork"

    stream_slide = tpl.slides.add_slide(blank)
    stream_marker = stream_slide.shapes.add_textbox(Inches(0), Inches(0), Inches(0.1), Inches(0.1))
    stream_marker.name = "_slide_type_stream"
    stream_name = stream_slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(1))
    stream_name.name = "stream_name"
    stream_name.text_frame.text = "STREAM PLACEHOLDER"
    stream_art = stream_slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(10), Inches(1), Inches(2), Inches(2))
    stream_art.name = "stream_artwork"

    roadmap_slide = tpl.slides.add_slide(blank)
    roadmap_marker = roadmap_slide.shapes.add_textbox(Inches(0), Inches(0), Inches(0.1), Inches(0.1))
    roadmap_marker.name = "_slide_type_roadmap"
    header = roadmap_slide.shapes.add_textbox(Inches(0.5), Inches(1), Inches(2.9), Inches(0.4))
    header.name = "col_header"
    bullets = roadmap_slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(2.9), Inches(5))
    bullets.name = "col_bullets"
    bullets.text_frame.text = "feature"

    path = tmp_path / "typed-template.pptx"
    tpl.save(path)
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: str(path))

    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    product_result = next(slide for slide in prs.slides if any(s.name == "product_artwork" for s in slide.shapes))
    stream_result = next(slide for slide in prs.slides if any(s.name == "stream_artwork" for s in slide.shapes))
    assert "Kaspersky Next" in _slide_text(product_result)
    assert "Kaspersky Next Optimum" in _slide_text(stream_result)
    assert not any(s.name.startswith("_slide_type_") for slide in prs.slides for s in slide.shapes)


def test_continuation_is_pure_table(load_fixture, synthetic_template_path):
    """Слайд-продолжение = только таблица (без заголовка роадмапа/легенды, TOR v2)."""
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    joined = "\n".join(_all_texts(prs))
    # нет ярлыка «Роадмап (продолжение)» — на продолжении остаются только слоты
    assert "продолжение" not in joined
    assert "Q1 2026" in joined


def test_flat_column_bullets(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    joined = "\n".join(_all_texts(prs))
    assert "Q1 2025" in joined
    assert "Feed X" in joined
    assert "Sandbox Z" in joined


@pytest.mark.parametrize(
    ("text", "is_subject_to_change", "expected"),
    [
        ("Поддержка Android 17", True, "Поддержка Android\u00a017\u00a0*"),
        ("Новый коррелятор 2.0", False, "Новый коррелятор\u00a02.0"),
        ("Feature v1.2.3", True, "Feature\u00a0v1.2.3\u00a0*"),
        ("Текст без номера", True, "Текст без номера\u00a0*"),
    ],
)
def test_terminal_version_and_subject_marker_stay_with_feature_word(
    text, is_subject_to_change, expected,
):
    bullet = Bullet(
        requirement_id=1,
        text=text,
        kbr=None,
        app_title="App",
        quarter="Q1 2026",
        is_subject_to_change=is_subject_to_change,
    )

    assert _bullet_text(bullet) == f"• {expected}"
    assert _template_feature_text(bullet, (None, None, False)) == f"• {expected}"
    assert _template_feature_text(bullet, (None, None, True)) == expected


def test_group_headers_rendered(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    assert any("Managed Detection and Response" in t for t in _all_texts(prs))


@pytest.mark.parametrize("quarter_count", [1, 2, 3, 4])
def test_sparse_single_slide_columns_keep_template_geometry(quarter_count, synthetic_template_path):
    """Размер шейпа берётся из шаблона, а его слот зависит от числа колонок."""
    plan = build_slide_plan(normalize_roadmap(_sparse_quarters_data(quarter_count), language="ru"), {})
    prs = build_presentation(plan)
    slide = _roadmap_slide(prs)
    assert slide is not None

    bodies = [shape for shape in slide.shapes if shape.name == "col_bullets"]
    slot_width = (prs.slide_width.inches - 1.0) / quarter_count
    assert len(bodies) == quarter_count
    expected_widths = (
        [prs.slide_width.inches - bodies[0].left.inches - 0.5]
        if quarter_count == 1 else [2.9] * quarter_count
    )
    assert [shape.width.inches for shape in bodies] == pytest.approx(expected_widths)
    assert [shape.left.inches for shape in bodies] == pytest.approx([
        0.5 + index * slot_width for index in range(quarter_count)
    ])

    separator_names = get_layout_shape_names("separators")
    separators = {shape.name: shape for shape in slide.shapes if shape.name in separator_names}
    assert [separators[name].left.inches for name in separator_names[:quarter_count - 1]] == pytest.approx([
        0.5 + index * slot_width for index in range(1, quarter_count)
    ])
    assert all(
        separators[name].left.inches > prs.slide_width.inches
        for name in separator_names[quarter_count - 1:]
    )


def test_single_quarter_60_features(load_fixture, synthetic_template_path):
    """60 фич в одном квартале → 3 слота по вместимости (~21/слот), фичи не теряются."""
    plan = _plan(load_fixture, "single_quarter_60_features.json")
    roadmap = [s for s in plan.slides if isinstance(s, RoadmapSlide)]
    assert len(roadmap) == 1
    assert len(roadmap[0].columns) == 3 and not roadmap[0].continuation
    counts = [
        sum(len(g.bullets) for g in c.groups) if c.grouped else len(c.bullets)
        for c in roadmap[0].columns
    ]
    assert counts == [21, 21, 18]
    prs = build_presentation(plan)
    slide = _roadmap_slide(prs)
    bodies = [shape for shape in slide.shapes if shape.name == "col_bullets"]
    assert [shape.width.inches for shape in bodies] == pytest.approx([2.9] * 3)
    texts = "\n".join(_all_texts(build_presentation(plan))).replace("\u00a0", " ")
    for i in range(1, 61):
        assert f"Feature {i}" in texts


def test_inherits_slide_size(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    template = Presentation(str(synthetic_template_path))
    assert prs.slide_width == template.slide_width
    assert prs.slide_height == template.slide_height


def test_quarter_header_is_not_duplicated_across_subslots(load_fixture, tmp_path, monkeypatch):
    """Заголовок квартала остаётся только в первой подколонке."""
    tpl_path = _template_with_named_shapes(tmp_path, "hdr_template.pptx", [])
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [{"Id": 1000 + i, "Kbr": "Yes", "MarketingTitle": f"f{i}"} for i in range(25)],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    prs = build_presentation(plan)
    headers = [
        sh.text_frame.text
        for s in prs.slides for sh in s.shapes
        if sh.name == "col_header"
    ]
    assert headers == ["Q1 2025", ""]


def test_quarter_marker_is_not_duplicated_for_overflow_columns(tmp_path, monkeypatch):
    """Подколонки одного квартала используют один quarter_marker на слайде."""
    tpl = Presentation()
    source = tpl.slides.add_slide(tpl.slide_layouts[6])
    header = source.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(1.2), Inches(0.3))
    header.name = "col_header"
    bullets = source.shapes.add_textbox(Inches(0.9), Inches(2.5), Inches(2.7), Inches(3.1))
    bullets.name = "col_bullets"
    marker = source.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(0.96), Inches(1.3), Inches(0.2), Inches(0.2),
    )
    marker.name = "quarter_marker"
    path = tmp_path / "overflow-marker.pptx"
    tpl.save(path)
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: str(path))

    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1,
            "AppTitle": "A",
            "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 1000 + i, "Kbr": "Yes", "MarketingTitle": f"f{i}"}
                for i in range(25)
            ],
        }]}]}],
    }]
    slide = _roadmap_slide(build_presentation(
        build_slide_plan(normalize_roadmap(data, language="ru"), {}),
    ))

    headers = [shape for shape in slide.shapes if shape.name == "col_header"]
    markers = [shape for shape in slide.shapes if shape.name == "quarter_marker"]
    assert len(headers) == 2
    assert len(markers) == 1


def test_template_geometry_markers_and_product_name(tmp_path, monkeypatch):
    tpl = Presentation()
    tpl.slide_width = Inches(13.333)
    tpl.slide_height = Inches(7.5)
    source = tpl.slides.add_slide(tpl.slide_layouts[6])

    header = source.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(1.2), Inches(0.3))
    header.name = "col_header"
    header.text_frame.text = "Q1 2026"
    bullets = source.shapes.add_textbox(Inches(0.9), Inches(2.5), Inches(2.7), Inches(3.1))
    bullets.name = "col_bullets"
    bullets.text_frame.text = "• feature"
    marker = source.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(0.96), Inches(1.3), Inches(0.2), Inches(0.2),
    )
    marker.name = "quarter_marker"
    product_name = source.shapes.add_textbox(Inches(9.5), Inches(0.3), Inches(3), Inches(0.4))
    product_name.name = "Product_Name"
    product_name.text_frame.text = "PRODUCT PLACEHOLDER"

    path = tmp_path / "geometry.pptx"
    tpl.save(path)
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: str(path))

    prs = build_presentation(build_slide_plan(
        normalize_roadmap(_sparse_quarters_data(3), language="ru"),
        {},
    ))
    slide = _roadmap_slide(prs)
    headers = [shape for shape in slide.shapes if shape.name == "col_header"]
    bodies = [shape for shape in slide.shapes if shape.name == "col_bullets"]
    markers = [shape for shape in slide.shapes if shape.name == "quarter_marker"]
    slot_width = (prs.slide_width.inches - 1.0) / 3

    assert len(headers) == len(bodies) == len(markers) == 3
    assert [shape.width.inches for shape in headers] == pytest.approx([1.2] * 3)
    assert [shape.width.inches for shape in bodies] == pytest.approx([2.7] * 3)
    assert [shape.height.inches for shape in bodies] == pytest.approx([3.1] * 3)
    assert [shape.left.inches for shape in headers] == pytest.approx([
        1.0 + index * slot_width for index in range(3)
    ])
    assert [shape.left.inches for shape in markers] == pytest.approx([
        shape.left.inches - 0.04 for shape in headers
    ])
    assert all(
        marker_shape.top.inches < header_shape.top.inches
        for marker_shape, header_shape in zip(markers, headers)
    )
    assert _shape_text_by_name(slide, "Product_Name") == "Product"


def test_group_and_feature_fonts_are_inherited_separately(tmp_path, monkeypatch):
    tpl = Presentation()
    tpl.slide_width = Inches(13.333)
    tpl.slide_height = Inches(7.5)
    source = tpl.slides.add_slide(tpl.slide_layouts[6])
    header = source.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(1.2), Inches(0.3))
    header.name = "col_header"
    header.text_frame.text = "Q1 2026"
    bullets = source.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(2.6), Inches(4.0))
    bullets.name = "col_bullets"
    group_paragraph = bullets.text_frame.paragraphs[0]
    group_paragraph.text = "Group heading"
    group_paragraph.runs[0].font.size = Pt(18)
    group_paragraph.runs[0].font.name = "Header Font"
    group_paragraph.runs[0].font.bold = True
    feature_paragraph = bullets.text_frame.add_paragraph()
    feature_paragraph.text = "• Feature"
    feature_paragraph.runs[0].font.size = Pt(10)
    feature_paragraph.runs[0].font.name = "Feature Font"
    feature_paragraph.runs[0].font.bold = False
    path = tmp_path / "paragraph-styles.pptx"
    tpl.save(path)
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: str(path))

    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [
            {
                "Id": 1,
                "AppTitle": "Application A",
                "TrDate": "15.01.2026 21:00:00",
                "Requirements": [{"Id": 1, "Kbr": "Yes", "MarketingTitle": "Feature A"}],
            },
            {
                "Id": 2,
                "AppTitle": "Application B",
                "TrDate": "15.01.2026 21:00:00",
                "Requirements": [{"Id": 2, "Kbr": "Yes", "MarketingTitle": "Feature B"}],
            },
        ]}]}],
    }]
    prs = build_presentation(build_slide_plan(normalize_roadmap(data, language="ru"), {}))
    slide = _roadmap_slide(prs)
    rendered = next(shape for shape in slide.shapes if shape.name == "col_bullets")
    paragraphs = [paragraph for paragraph in rendered.text_frame.paragraphs if paragraph.text]

    assert [paragraph.text for paragraph in paragraphs] == [
        "Application A", "• Feature A", "Application B", "• Feature B",
    ]
    assert [paragraph.runs[0].font.size.pt for paragraph in paragraphs] == [18, 10, 18, 10]
    assert [paragraph.runs[0].font.name for paragraph in paragraphs] == [
        "Header Font", "Feature Font", "Header Font", "Feature Font",
    ]
    assert [paragraph.runs[0].font.bold for paragraph in paragraphs] == [True, False, True, False]


def test_many_bullets_paginate_via_flexible_columns(load_fixture, synthetic_template_path):
    # 200 фич в одном квартале → 10 слотов → 3 слайда (4+4+2), квартал растягивается
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 1000 + i, "Kbr": "Yes", "MarketingTitle": f"feature number {i}"}
                for i in range(200)
            ],
        }]}]}],
    }]
    plan = build_slide_plan(normalize_roadmap(data, language="ru"), {})
    roadmap_slides = [s for s in plan.slides if isinstance(s, RoadmapSlide)]
    assert len(roadmap_slides) == 3
    assert [len(s.columns) for s in roadmap_slides] == [4, 4, 2]
    assert [s.continuation for s in roadmap_slides] == [False, True, True]
    prs = build_presentation(plan)
    # титульный + product + stream + 3 roadmap + спасибо = 7 слайдов
    assert len(prs.slides) == 7

    titles = [
        shape.text
        for rendered_slide in prs.slides
        for shape in rendered_slide.shapes
        if shape.name == "slide_title"
    ]
    assert titles == ["T"] * 3


def test_slide_title_uses_original_tier_name_without_override(load_fixture):
    plan = build_slide_plan(normalize_roadmap(load_fixture("en_with_content.json"), language="ru"), {})
    prs = build_presentation(plan)
    titles = [
        shape.text
        for rendered_slide in prs.slides
        for shape in rendered_slide.shapes
        if shape.name == "slide_title"
    ]
    assert titles
    assert set(titles) == {"Kaspersky Next EDR Foundations"}


def test_slide_title_uses_english_tier_brand(load_fixture):
    plan = build_slide_plan(normalize_roadmap(load_fixture("en_with_content.json"), language="en"), {})
    prs = build_presentation(plan)
    titles = [
        shape.text
        for rendered_slide in prs.slides
        for shape in rendered_slide.shapes
        if shape.name == "slide_title"
    ]
    assert titles
    assert set(titles) == {"Kaspersky Next EDR Foundations"}


@pytest.mark.parametrize(
    ("language", "custom"),
    [("ru", "Kaspersky Symphony EDR Foundations"), ("en", "Custom English Tier")],
)
def test_slide_title_uses_language_specific_override(load_fixture, language, custom):
    original = "Kaspersky Next EDR Foundations"
    tier_names.import_state({original: {language: custom}})
    plan = build_slide_plan(normalize_roadmap(load_fixture("en_with_content.json"), language=language), {})
    prs = build_presentation(plan)
    titles = [
        shape.text
        for rendered_slide in prs.slides
        for shape in rendered_slide.shapes
        if shape.name == "slide_title"
    ]
    assert titles
    assert set(titles) == {custom}


def test_title_and_thank_you_slides(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    texts = _all_texts(prs)
    # первый слайд — титульный (дефолтный заголовок «Roadmap»), последний — «Спасибо!»
    assert "Roadmap" in texts[0]
    for slide in (prs.slides[0], prs.slides[-1]):
        runs = [
            run
            for shape in slide.shapes if shape.has_text_frame
            for paragraph in shape.text_frame.paragraphs
            for run in paragraph.runs
        ]
        assert runs
        assert all(run.font.color.rgb == RGBColor(255, 255, 255) for run in runs)
    assert "Спасибо!" in texts[-1]


def test_static_slide_keeps_source_formatting(tmp_path, monkeypatch, synthetic_template_path):
    source = Presentation()
    source_slide = source.slides.add_slide(source.slide_layouts[5])
    expected_layout_name = source_slide.slide_layout.name
    source_slide.background.fill.solid()
    source_slide.background.fill.fore_color.rgb = RGBColor(0x12, 0x34, 0x56)
    box = source_slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    box.name = "formatted_source"
    run = box.text_frame.paragraphs[0].add_run()
    run.text = "Keep source formatting"
    run.font.name = "Arial"
    run.font.size = Pt(27)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0xAA, 0x22, 0x33)
    source_path = tmp_path / "static-source.pptx"
    source.save(source_path)
    monkeypatch.setattr(static_slides, "STATIC_SLIDES_DIR", tmp_path)

    rendered = build_presentation(SlidePlan(slides=[StaticSlide(name="Static", pptx=source_path.name)]))
    rendered_slide = rendered.slides[0]
    rendered_box = next(shape for shape in rendered_slide.shapes if shape.name == "formatted_source")
    rendered_run = rendered_box.text_frame.paragraphs[0].runs[0]

    assert rendered_slide.background.fill.fore_color.rgb == RGBColor(0x12, 0x34, 0x56)
    assert rendered_run.font.name == "Arial"
    assert rendered_run.font.size == Pt(27)
    assert rendered_run.font.bold is True
    assert rendered_run.font.color.rgb == RGBColor(0xAA, 0x22, 0x33)
    assert rendered_slide.slide_layout.name == expected_layout_name

    output = tmp_path / "rendered-static.pptx"
    rendered.save(output)
    reopened = Presentation(output)
    assert reopened.slides[0].slide_layout.name == expected_layout_name
    assert len(reopened.slide_masters) == 2
    assert reopened.slides[0].slide_layout.slide_master.part is reopened.slide_masters[1].part
    _assert_no_dangling_package_relationships(output)


def test_all_generated_slides_use_uploaded_template_layout(load_fixture, tmp_path, monkeypatch):
    template = Presentation()
    template.slide_width = Inches(13.333)
    template.slide_height = Inches(7.5)
    source = template.slides.add_slide(template.slide_layouts[5])
    expected_layout_name = source.slide_layout.name
    header = source.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(3), Inches(0.4))
    header.name = "col_header"
    bullets = source.shapes.add_textbox(Inches(0.5), Inches(1), Inches(3), Inches(5))
    bullets.name = "col_bullets"
    template_path = tmp_path / "layout-template.pptx"
    template.save(template_path)
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: str(template_path))

    rendered = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    output = tmp_path / "rendered-layouts.pptx"
    rendered.save(output)
    reopened = Presentation(output)

    assert reopened.slides
    assert {slide.slide_layout.name for slide in reopened.slides} == {expected_layout_name}
    assert len(reopened.slide_masters) == 1
    assert all(
        slide.slide_layout.slide_master.part is reopened.slide_masters[0].part
        for slide in reopened.slides
    )
    _assert_no_dangling_package_relationships(output)


def test_title_and_thank_you_use_layout_from_first_template_slide(
    load_fixture, tmp_path, monkeypatch,
):
    template = Presentation()
    first_slide = template.slides.add_slide(template.slide_layouts[0])
    first_layout_name = first_slide.slide_layout.name
    roadmap_slide = template.slides.add_slide(template.slide_layouts[5])
    roadmap_layout_name = roadmap_slide.slide_layout.name
    header = roadmap_slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(3), Inches(0.4))
    header.name = "col_header"
    bullets = roadmap_slide.shapes.add_textbox(Inches(0.5), Inches(1), Inches(3), Inches(5))
    bullets.name = "col_bullets"
    template_path = tmp_path / "separate-intro-layouts.pptx"
    template.save(template_path)
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: str(template_path))

    rendered = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    output = tmp_path / "separate-intro-layouts-rendered.pptx"
    rendered.save(output)
    reopened = Presentation(output)

    assert reopened.slides[0].slide_layout.name == first_layout_name
    assert reopened.slides[-1].slide_layout.name == first_layout_name
    assert any(slide.slide_layout.name == roadmap_layout_name for slide in list(reopened.slides)[1:-1])
    _assert_no_dangling_package_relationships(output)


def test_static_slides_keep_source_layout_and_plan_position(
    tmp_path, monkeypatch, synthetic_template_path,
):
    source = Presentation()
    source_layout = source.slide_layouts[5]
    for text in ("Static one", "Static two"):
        source_slide = source.slides.add_slide(source_layout)
        source_slide.shapes.add_textbox(
            Inches(1), Inches(1), Inches(4), Inches(1),
        ).text_frame.text = text
    source_path = tmp_path / "two-static-slides.pptx"
    source.save(source_path)
    monkeypatch.setattr(static_slides, "STATIC_SLIDES_DIR", tmp_path)

    rendered = build_presentation(SlidePlan(slides=[
        TitleSlide(title="Before", year="", version=""),
        StaticSlide(name="Static", pptx=source_path.name),
        ThankYouSlide(text="After"),
    ]))
    output = tmp_path / "static-order.pptx"
    rendered.save(output)
    reopened = Presentation(output)

    assert ["Before", "Static one", "Static two", "After"] == [
        _slide_text(slide) for slide in reopened.slides
    ]
    assert len(reopened.slide_masters) == 2
    assert all(
        reopened.slides[index].slide_layout.slide_master.part
        is reopened.slide_masters[1].part
        for index in (1, 2)
    )
    _assert_no_dangling_package_relationships(output)


def test_date_placeholders_use_current_system_date(load_fixture, tmp_path, monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2031, 2, 3)

    template_path = _template_with_named_shapes(
        tmp_path,
        "date_placeholders.pptx",
        [
            {"name": "roadmap_year", "kind": "text", "text": "YEAR"},
            {"name": "roadmap_version", "kind": "text", "text": "VERSION"},
        ],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: template_path)
    monkeypatch.setattr("roadmap_generator.builder.date", FixedDate)

    rendered = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    roadmap_slide = _roadmap_slide(rendered)
    assert roadmap_slide is not None
    assert _shape_text_by_name(roadmap_slide, "roadmap_year") == "2031"
    assert _shape_text_by_name(roadmap_slide, "roadmap_version") == "Version 03.02.31"


def test_template_with_linked_picture_does_not_crash(load_fixture, tmp_path, monkeypatch):
    """Картинка шаблона без встроенного образа (`r:link`) не роняет рендер.

    Регрессия на `ValueError: no embedded image` из `_clone_slide`: у связанной
    картинки blob достаётся через relationship и перевстраивается, слайд клонируется.
    """
    def add_linked(slide):
        pic = slide.shapes.add_picture(io.BytesIO(PNG), Inches(9), Inches(0.2), Inches(2), Inches(1.5))
        pic.name = "linked_logo"
        blip = pic._element.blipFill.blip
        r_id = blip.rEmbed
        blip.attrib.pop(qn("r:embed"), None)
        blip.set(qn("r:link"), r_id)

    tpl_path = _make_template(tmp_path, "linked_pic.pptx", add_picture=add_linked)
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))

    # картинка пересоздана через add_picture (со встроенным образом), а не упала
    pics = [
        sh for s in prs.slides
        for sh in s.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE
    ]
    assert pics, "связанная картинка шаблона должна быть перенесена на слайды"
    assert all(pic.image.blob == PNG for pic in pics)


def test_template_with_svg_logo_does_not_crash(load_fixture, tmp_path, monkeypatch):
    """SVG-логотип (`asvg:svgBlip` без `r:embed` на `a:blip`) переносится как media part.

    python-pptx не умеет SVG в `add_picture` — картинка копируется через
    перенос медиа-part и relationship, без `ValueError: no embedded image`.
    """
    tpl = Presentation()
    tpl.slide_width = Inches(13.333)
    tpl.slide_height = Inches(7.5)
    slide = tpl.slides.add_slide(tpl.slide_layouts[6])
    header = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(3), Inches(0.4))
    header.name = "col_header"
    bullets = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(2.9), Inches(5))
    bullets.name = "col_bullets"

    pic = slide.shapes.add_picture(io.BytesIO(PNG), Inches(9), Inches(0.2), Inches(2), Inches(1.5))
    pic.name = "logo"
    pkg = tpl.part.package
    svg_part = Part(pkg.next_media_partname("svg"), "image/svg+xml", pkg, SVG)
    svg_r_id = slide.part.relate_to(svg_part, RT.IMAGE)
    blip = pic._element.blipFill.blip
    blip.attrib.pop(qn("r:embed"), None)
    svg_blip = blip.makeelement("{%s}svgBlip" % NS_ASVG, {qn("r:embed"): svg_r_id})
    blip.append(svg_blip)

    tpl_path = tmp_path / "svg_template.pptx"
    tpl.save(str(tpl_path))

    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))

    pics = [
        sh for s in prs.slides
        for sh in s.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE
    ]
    assert pics, "SVG-логотип шаблона должен быть перенесён на слайды"


def test_underscore_named_shapes_are_skipped(load_fixture, tmp_path, monkeypatch):
    """Шейпы шаблона с префиксом `_` (сервисные/направляющие) в слайд не копируются."""
    tpl_path = _make_template(tmp_path, "skip_template.pptx", skip_name="_guide_sample")
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    assert not any("THIS SHOULD NOT APPEAR" in t for t in _all_texts(prs))


def _png_rgb(r: int, g: int, b: int) -> bytes:
    """Генерирует валидный 1x1 PNG заданного цвета (для различимых лого в тестах)."""
    import struct
    import zlib

    def chunk(typ: bytes, data: bytes) -> bytes:
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" + bytes([r, g, b]))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _template_with_named_shapes(tmp_path, name, shapes):
    """Шаблон с обязательными шейпами и дополнительными именованными (текст/картинка).

    `shapes` — список dict: {"name": ..., "kind": "text"|"picture", "text": ...,
    "bytes": ...}. Возвращает путь к .pptx.
    """
    tpl = Presentation()
    tpl.slide_width = Inches(13.333)
    tpl.slide_height = Inches(7.5)
    slide = tpl.slides.add_slide(tpl.slide_layouts[6])
    header = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(3), Inches(0.4))
    header.name = "col_header"
    bullets = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(2.9), Inches(5))
    bullets.name = "col_bullets"
    for spec in shapes:
        if spec["kind"] == "picture":
            pic = slide.shapes.add_picture(
                io.BytesIO(spec["bytes"]), Inches(9), Inches(0.2), Inches(2), Inches(1.5),
            )
            pic.name = spec["name"]
        else:
            box = slide.shapes.add_textbox(Inches(0.5), Inches(6.0), Inches(3), Inches(0.4))
            box.name = spec["name"]
            box.text_frame.text = spec.get("text", "")
    path = tmp_path / name
    tpl.save(str(path))
    return str(path)


def _shape_text_by_name(slide, name: str):
    for sh in slide.shapes:
        if sh.name == name and sh.has_text_frame:
            return sh.text_frame.text
    return None


def _roadmap_slide(prs):
    """Первый слайд с заголовком квартала (т.е. рендер roadmap-слайда из шаблона)."""
    for s in prs.slides:
        if any(sh.name == "col_header" for sh in s.shapes):
            return s
    return None


def test_static_roadmap_label_not_overwritten(load_fixture, tmp_path, monkeypatch):
    """Ярлык `_roadmap` в шаблоне статичный — билдер не заменяет его текст."""
    tpl_path = _template_with_named_shapes(
        tmp_path, "roadmap_label.pptx",
        [{"name": "_roadmap", "kind": "text", "text": "Roadmap"}],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    slide = _roadmap_slide(prs)
    assert slide is not None
    assert _shape_text_by_name(slide, "_roadmap") == "Roadmap"


def test_s2c_footnote_shown_once(load_fixture, tmp_path, monkeypatch):
    """Сноска Subject to Change заполняется в `_s2c` ОДИН раз, без дубля-текстбокса."""
    tpl_path = _template_with_named_shapes(
        tmp_path, "s2c_template.pptx",
        [{"name": "_s2c", "kind": "text", "text": "PLACEHOLDER S2C"}],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "subject_to_change_mixed.json"))

    footnote = "* Могут быть внесены изменения"
    slide = _roadmap_slide(prs)
    assert slide is not None
    # плейсхолдер-текст заменён на сноску, и сноска встречается ровно один раз
    assert _shape_text_by_name(slide, "_s2c") == footnote
    all_text = "\n".join(_all_texts(prs))
    assert all_text.count(footnote) == 1
    assert "PLACEHOLDER S2C" not in all_text


def test_s2c_duplicate_alias_placeholders_are_cleared(load_fixture, tmp_path, monkeypatch):
    """Даже при двух S2C-шейпах текст остаётся только в каноническом плейсхолдере."""
    tpl_path = _template_with_named_shapes(
        tmp_path,
        "duplicate_s2c_template.pptx",
        [
            {"name": "subject_to_change_footnote", "kind": "text", "text": "CANONICAL"},
            {"name": "_s2c", "kind": "text", "text": "LEGACY"},
        ],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "subject_to_change_mixed.json"))

    footnote = "* Могут быть внесены изменения"
    slide = _roadmap_slide(prs)
    assert slide is not None
    texts = [shape.text for shape in slide.shapes if shape.has_text_frame]
    assert sum(text.count(footnote) for text in texts) == 1
    assert "CANONICAL" not in texts
    assert "LEGACY" not in texts


def test_retired_inheritance_placeholder_is_always_cleared(load_fixture, tmp_path, monkeypatch):
    tpl_path = _template_with_named_shapes(
        tmp_path,
        "inheritance_template.pptx",
        [{"name": "tier_inheritance_note", "kind": "text", "text": "INHERITANCE PLACEHOLDER"}],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    ordering.save_product_inheritance_flag("Kaspersky Next", True)
    prs = build_presentation(_plan(load_fixture, "tier_hierarchy_next.json"))

    placeholders = [
        shape.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.name == "tier_inheritance_note" and shape.has_text_frame
    ]
    assert placeholders
    assert set(placeholders) == {""}


def test_number_placeholder_filled_with_ordinal(load_fixture, tmp_path, monkeypatch):
    """Плейсхолдер `_number` заполняется порядковым номером слайда (1-based)."""
    tpl_path = _template_with_named_shapes(
        tmp_path, "number_template.pptx",
        [{"name": "_number", "kind": "text", "text": "1"}],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    slide = _roadmap_slide(prs)
    assert slide is not None
    expected = str(list(prs.slides).index(slide) + 1)
    assert _shape_text_by_name(slide, "_number") == expected


def test_product_logo_is_not_replaced_on_roadmap_slide(load_fixture, tmp_path, monkeypatch):
    """Библиотека старых логотипов больше не влияет на roadmap-слайды."""
    blue = _png_rgb(0, 0, 255)
    red = _png_rgb(255, 0, 0)

    logo_dir = tmp_path / "logos"
    monkeypatch.setattr("roadmap_generator.product_logos.LOGO_DIR", logo_dir)
    from roadmap_generator import product_logos

    product_logos.save_logo("Kaspersky Threat Intelligence", blue, "png")

    tpl_path = _template_with_named_shapes(
        tmp_path, "logo_template.pptx",
        [{"name": "_logo", "kind": "picture", "bytes": red}],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))

    slide = _roadmap_slide(prs)
    assert slide is not None
    pics = [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert pics, "логотип должен остаться картинкой на слайде"
    assert not any(p.image.blob == blue for p in pics), "логотип продукта не должен подставляться"
    assert any(p.image.blob == red for p in pics), "картинка из шаблона должна остаться без замены"


def test_tier_logo_replaced_from_library(load_fixture, tmp_path, monkeypatch):
    """Плейсхолдер `_logo_tier` подменяется лого тира из библиотеки."""
    blue = _png_rgb(0, 0, 255)
    red = _png_rgb(255, 0, 0)

    logo_dir = tmp_path / "tier_logos"
    monkeypatch.setattr("roadmap_generator.product_logos.TIER_LOGO_DIR", logo_dir)
    from roadmap_generator import product_logos

    product_logos.save_tier_logo("Kaspersky Threat Intelligence", blue, "png")

    tpl_path = _template_with_named_shapes(
        tmp_path, "tier_logo_template.pptx",
        [{"name": "_logo_tier", "kind": "picture", "bytes": red}],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))

    slide = _roadmap_slide(prs)
    assert slide is not None
    pics = [sh for sh in slide.shapes if sh.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert any(p.image.blob == blue for p in pics), "картинка должна быть заменена на лого тира"


def test_product_slide_image_replaces_product_divider_placeholder(load_fixture, tmp_path, monkeypatch):
    blue = _png_rgb(0, 0, 255)
    red = _png_rgb(255, 0, 0)
    image_dir = tmp_path / "product_slide_images"
    monkeypatch.setattr("roadmap_generator.product_logos.PRODUCT_SLIDE_DIR", image_dir)
    from roadmap_generator import product_logos

    product_logos.save_product_slide_image("Kaspersky Threat Intelligence", blue, "png")
    tpl_path = _template_with_named_shapes(
        tmp_path,
        "product_slide_image_template.pptx",
        [
            {"name": "_slide_type_product", "kind": "text", "text": ""},
            {"name": "Product_Name", "kind": "text", "text": "Product"},
            {"name": "_product_slide_image", "kind": "picture", "bytes": red},
        ],
    )
    monkeypatch.setattr("roadmap_generator.builder.select_template", lambda *a, **k: tpl_path)

    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    product_slide = next(
        slide for slide in prs.slides
        if any(shape.name == "Product_Name" for shape in slide.shapes)
    )
    pictures = [shape for shape in product_slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert any(picture.image.blob == blue for picture in pictures)
