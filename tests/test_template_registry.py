"""Тесты для `roadmap_generator/template_registry.py` (Этап 3)."""
from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Inches

from roadmap_generator import template_registry as tr


def test_get_required_shapes_base():
    # контракт шаблона-«конструктора»: одна колонка-прототип, columns/grouped не влияют
    assert tr.get_required_shapes("roadmap", 2, False) == ["col_header", "col_bullets"]
    assert tr.get_required_shapes("roadmap", 4, True) == ["col_header", "col_bullets"]


def test_layout_separator_names_come_from_contract():
    assert tr.get_layout_shape_names("separators") == [
        "col_separator_1",
        "col_separator_2",
        "col_separator_3",
    ]


def test_semantic_role_names_and_legacy_aliases_come_from_contract():
    assert tr.get_role_shape_names("product_name") == ["Product_Name", "product_name"]
    assert tr.get_role_shape_names("subject_to_change_footnote") == [
        "subject_to_change_footnote",
        "s2c",
    ]
    assert tr.get_role_shape_names("tier_inheritance_note") == [
        "tier_inheritance_note",
        "inheritance_note",
    ]


def test_synthetic_template_satisfies_all_contracts(synthetic_template_path):
    required = tr.get_required_shapes("roadmap", 3, False)
    missing = tr.validate_template_shapes(str(synthetic_template_path), required)
    assert missing == []


def test_validate_template_shapes_reports_missing(synthetic_template_path):
    missing = tr.validate_template_shapes(
        str(synthetic_template_path), ["col_header", "col_999_missing"],
    )
    assert missing == ["col_999_missing"]


def test_select_template_returns_existing_path(synthetic_template_path):
    for slide_type in ("roadmap", "roadmap_cont"):
        path = tr.select_template(slide_type, 2, False)
        assert path.endswith("synthetic_template.pptx")
        assert Path(path).exists()


def test_select_template_unknown_type_raises():
    with pytest.raises(KeyError):
        tr.select_template("bogus", 1, False)


def _template_with(tmp_path, name, names):
    """Собирает .pptx с текстовыми боксами заданных имён."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    for i, n in enumerate(names):
        box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5 + i * 0.5), Inches(2.9), Inches(0.4))
        box.name = n
    path = tmp_path / name
    prs.save(str(path))
    return str(path)


def test_validate_full_reports_duplicates_with_hints(tmp_path):
    path = _template_with(tmp_path, "dup.pptx", ["col_header", "col_bullets", "col_bullets"])
    check = tr.validate_template_full(path)
    assert check["duplicate_shapes"] == ["col_bullets"]
    assert check["missing_shapes"] == []
    joined = "\n".join(check["issues"])
    assert "col_bullets" in joined
    # подсказка дизайнеру: что сделать с лишними шейпами
    assert "_sample" in joined or "eyebrow" in joined
    assert "Префикс «_»" in joined


def test_validate_full_reports_missing_with_hints(tmp_path):
    path = _template_with(tmp_path, "missing.pptx", ["eyebrow"])
    check = tr.validate_template_full(path)
    assert check["missing_shapes"] == ["col_header", "col_bullets"]
    joined = "\n".join(check["issues"])
    assert "Нет шейпа «col_bullets»" in joined
    assert "Нет шейпа «col_header»" in joined
    assert "назовите ровно col_bullets" in joined


def test_validate_full_clean_template_has_no_issues(synthetic_template_path):
    check = tr.validate_template_full(str(synthetic_template_path))
    assert check["missing_shapes"] == []
    assert check["duplicate_shapes"] == []
    assert check["issues"] == []


def test_list_templates_skips_lock_files(tmp_path, monkeypatch):
    """Блокировки PowerPoint (`~$…`) не должны ломать список шаблонов."""
    lib = tmp_path / "lib"
    lib.mkdir()
    # реальный шаблон
    real = tr.validate_template_full(str(_template_with(tmp_path, "real.pptx", ["col_header", "col_bullets"])))
    # не-pptx «блокировка»
    (lib / "~$real.pptx").write_bytes(b"not a real pptx")

    monkeypatch.setattr(tr, "TEMPLATES_LIBRARY", lib)
    # копируем реальный шаблон в lib
    import shutil
    shutil.copy(_template_with(tmp_path, "real.pptx", ["col_header", "col_bullets"]), lib / "real.pptx")

    result = tr.list_templates()
    filenames = [t["filename"] for t in result]
    assert "~$real.pptx" not in filenames
    assert "real.pptx" in filenames
    # валидный шаблон — без замечаний
    real_item = next(t for t in result if t["filename"] == "real.pptx")
    assert real_item["valid"] is True
