"""Тесты для `roadmap_generator/template_registry.py` (Этап 3)."""
from __future__ import annotations

from pathlib import Path

import pytest

from roadmap_generator import template_registry as tr


def test_get_required_shapes_flat():
    assert tr.get_required_shapes("roadmap", 2, False) == [
        "col_1_header", "col_1_bullets", "col_2_header", "col_2_bullets",
    ]


def test_get_required_shapes_grouped():
    assert tr.get_required_shapes("roadmap", 2, True) == [
        "col_1_header", "col_1_bullets", "col_1_group_1_header",
        "col_2_header", "col_2_bullets", "col_2_group_1_header",
    ]


def test_synthetic_template_satisfies_all_contracts(synthetic_template_path):
    for columns in (1, 2, 3, 4):
        for grouped in (False, True):
            required = tr.get_required_shapes("roadmap", columns, grouped)
            missing = tr.validate_template_shapes(str(synthetic_template_path), required)
            assert missing == [], f"columns={columns} grouped={grouped} missing={missing}"


def test_validate_template_shapes_reports_missing(synthetic_template_path):
    missing = tr.validate_template_shapes(
        str(synthetic_template_path), ["col_1_header", "col_999_missing"],
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
