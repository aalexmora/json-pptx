"""Тесты для `roadmap_generator/builder.py` (структурная проверка рендера)."""
from __future__ import annotations

import io

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.oxml.ns import qn
from pptx.util import Inches

from roadmap_generator.builder import build_presentation
from roadmap_generator.plugins_engine import RoadmapSlide, build_slide_plan
from roadmap_generator.schema import normalize_roadmap

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


def test_pagination_slide_count(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    # титульный + product + stream + 2 roadmap + спасибо = 6
    assert len(prs.slides) == 6


def test_dividers_render_titles(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    texts = _all_texts(prs)
    assert any("PRODUCT" in t and "Kaspersky Next" in t for t in texts)
    assert any("STREAM" in t and "Kaspersky Next Optimum" in t for t in texts)


def test_continuation_eyebrow(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    # RU-заголовок продолжения — «Роадмап (продолжение)»
    assert any("продолжение" in t for t in _all_texts(prs))


def test_flat_column_bullets(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    joined = "\n".join(_all_texts(prs))
    assert "Q1 2025" in joined
    assert "Feed X" in joined
    assert "Sandbox Z" in joined


def test_group_headers_rendered(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    assert any("Managed Detection and Response" in t for t in _all_texts(prs))


def test_single_quarter_60_features(load_fixture, synthetic_template_path):
    """60 фич в одном квартале → 6 колонок по 10 → 2 roadmap-слайда, фичи не теряются."""
    plan = _plan(load_fixture, "single_quarter_60_features.json")
    roadmap = [s for s in plan.slides if isinstance(s, RoadmapSlide)]
    assert len(roadmap) == 2
    # 4 колонки на первом слайде, 2 на продолжении
    assert len(roadmap[0].columns) == 4 and not roadmap[0].continuation
    assert len(roadmap[1].columns) == 2 and roadmap[1].continuation
    # ровно по 10 фич в колонке, все 60 на месте
    counts = [len(c.bullets) for s in roadmap for c in s.columns]
    assert counts == [10] * 6
    texts = "\n".join(_all_texts(build_presentation(plan)))
    for i in range(1, 61):
        assert f"Feature {i}" in texts


def test_inherits_slide_size(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "non_next_product_flat.json"))
    template = Presentation(str(synthetic_template_path))
    assert prs.slide_width == template.slide_width
    assert prs.slide_height == template.slide_height


def test_many_bullets_paginate_via_flexible_columns(load_fixture, synthetic_template_path):
    # 200 фич в одном квартале → 20 колонок → 5 roadmap-слайдов (гибкая раскладка)
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
    assert len(roadmap_slides) == 5  # 200/10 = 20 колонок → 5 слайдов
    prs = build_presentation(plan)
    # титульный + product + stream + 5 roadmap + спасибо = 9 слайдов
    assert len(prs.slides) == 9


def test_title_and_thank_you_slides(load_fixture, synthetic_template_path):
    prs = build_presentation(_plan(load_fixture, "pagination_5_quarters.json"))
    texts = _all_texts(prs)
    # первый слайд — титульный (дефолтный заголовок «Roadmap»), последний — «Спасибо!»
    assert "Roadmap" in texts[0]
    assert "Спасибо!" in texts[-1]


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


def test_logo_replaced_from_library(load_fixture, tmp_path, monkeypatch):
    """Плейсхолдер `_logo` подменяется лого продукта из библиотеки."""
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
    assert any(p.image.blob == blue for p in pics), "картинка должна быть заменена на лого из библиотеки"
