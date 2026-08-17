"""Тесты для `roadmap_generator/schema.py` (Этап 1).

Покрывают валидацию, нормализацию, вычисление календарных кварталов, EN-фильтр
и мягкие fallback'и опциональных полей на реальных данных и синтетических
фикстурах (ТЗ v4 раздел 11).
"""
from __future__ import annotations

from roadmap_generator.schema import (
    _normalize_name,
    normalize_roadmap,
    validate_roadmap,
)


# ---------------------------------------------------------------------------
# Валидация
# ---------------------------------------------------------------------------

def test_validate_real_data_has_no_errors(real_data):
    assert validate_roadmap(real_data) == []


def test_validate_all_fixtures_pass(load_fixture):
    names = [
        "pagination_5_quarters.json",
        "subject_to_change_mixed.json",
        "non_next_product_flat.json",
        "en_with_content.json",
        "missing_optional_fields.json",
        "tier_hierarchy_next.json",
    ]
    for name in names:
        errors = validate_roadmap(load_fixture(name))
        assert errors == [], f"фикстура {name} должна быть валидна, ошибки: {errors}"


def test_validate_rejects_non_list():
    assert validate_roadmap({"Product": "X"}) != []


def test_validate_rejects_empty_list():
    assert validate_roadmap([]) != []


def test_validate_missing_product_name():
    errors = validate_roadmap([{"Streams": []}])
    assert any("Product" in e for e in errors)


def test_validate_bad_trdate():
    data = [
        {
            "Product": "P",
            "Streams": [
                {
                    "Stream": "S",
                    "Tiers": [
                        {
                            "Tier": "T",
                            "Releases": [
                                {
                                    "Id": 1,
                                    "AppTitle": "A",
                                    "TrDate": "not-a-date",
                                    "Requirements": [
                                        {"Id": 10, "MarketingTitle": "ok"}
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    errors = validate_roadmap(data)
    assert any("TrDate" in e for e in errors)


def test_validate_duplicate_release_id():
    data = [
        {
            "Product": "P",
            "Streams": [
                {
                    "Stream": "S",
                    "Tiers": [
                        {
                            "Tier": "T",
                            "Releases": [
                                {
                                    "Id": 1,
                                    "AppTitle": "A",
                                    "TrDate": "15.01.2025 21:00:00",
                                    "Requirements": [{"Id": 10, "MarketingTitle": "ok"}],
                                },
                                {
                                    "Id": 1,
                                    "AppTitle": "B",
                                    "TrDate": "15.01.2025 21:00:00",
                                    "Requirements": [{"Id": 11, "MarketingTitle": "ok"}],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    errors = validate_roadmap(data)
    assert any("дублируется" in e for e in errors)


def test_validate_missing_marketing_title():
    data = [
        {
            "Product": "P",
            "Streams": [
                {
                    "Stream": "S",
                    "Tiers": [
                        {
                            "Tier": "T",
                            "Releases": [
                                {
                                    "Id": 1,
                                    "AppTitle": "A",
                                    "TrDate": "15.01.2025 21:00:00",
                                    "Requirements": [{"Id": 10, "MarketingTitle": ""}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    errors = validate_roadmap(data)
    assert any("MarketingTitle" in e for e in errors)


def test_validate_collects_all_errors_in_one_pass():
    """Все ошибки собираются за один проход, а не падают на первой."""
    data = [
        {
            "Product": "",  # ошибка: пустое имя
            "Streams": [
                {
                    "Stream": "S",
                    "Tiers": [
                        {
                            "Tier": "T",
                            "Releases": [
                                {
                                    "Id": 1,
                                    "AppTitle": "A",
                                    "TrDate": "bad-date",  # ошибка: дата
                                    "Requirements": [
                                        {"Id": 10, "MarketingTitle": ""}  # ошибка: текст
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    errors = validate_roadmap(data)
    assert len(errors) == 3


# ---------------------------------------------------------------------------
# Нормализация: кварталы
# ---------------------------------------------------------------------------

def test_normalize_computes_calendar_quarters(real_data):
    model = normalize_roadmap(real_data, language="ru")
    tier = model.products[0].streams[0].tiers[0]
    quarters = {r.quarter for r in tier.releases}
    # TrDate 29.06.2025 -> Q2 2025 ; 27.02.2025 -> Q1 2025
    assert "Q2 2025" in quarters
    assert "Q1 2025" in quarters


def test_quarter_boundaries():
    cases = {
        "01.01.2025 00:00:00": "Q1 2025",
        "31.03.2025 00:00:00": "Q1 2025",
        "01.04.2025 00:00:00": "Q2 2025",
        "30.06.2025 00:00:00": "Q2 2025",
        "01.07.2025 00:00:00": "Q3 2025",
        "30.09.2025 00:00:00": "Q3 2025",
        "01.10.2025 00:00:00": "Q4 2025",
        "31.12.2025 00:00:00": "Q4 2025",
        "01.01.2026 00:00:00": "Q1 2026",
    }
    for trdate, expected in cases.items():
        data = [
            {
                "Product": "P",
                "Streams": [
                    {
                        "Stream": "S",
                        "Tiers": [
                            {
                                "Tier": "T",
                                "Releases": [
                                    {
                                        "Id": 1,
                                        "AppTitle": "A",
                                        "TrDate": trdate,
                                        "Requirements": [{"Id": 10, "MarketingTitle": "x"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        model = normalize_roadmap(data, language="ru")
        assert model.products[0].streams[0].tiers[0].releases[0].quarter == expected


def test_pagination_fixture_yields_5_distinct_quarters(load_fixture):
    model = normalize_roadmap(load_fixture("pagination_5_quarters.json"), language="ru")
    tier = model.products[0].streams[0].tiers[0]
    quarters = [r.quarter for r in tier.releases]
    assert quarters == ["Q1 2025", "Q2 2025", "Q3 2025", "Q4 2025", "Q1 2026"]


# ---------------------------------------------------------------------------
# Нормализация: EN-фильтр
# ---------------------------------------------------------------------------

def test_normalize_en_drops_null_marketing_title_en(load_fixture):
    ru = normalize_roadmap(load_fixture("en_with_content.json"), language="ru")
    en = normalize_roadmap(load_fixture("en_with_content.json"), language="en")
    ru_req_count = sum(len(r.requirements) for r in ru.products[0].streams[0].tiers[0].releases)
    en_req_count = sum(len(r.requirements) for r in en.products[0].streams[0].tiers[0].releases)
    # фикстура: 3 требования, у одного MarketingTitleEn == null
    assert ru_req_count == 3
    assert en_req_count == 2
    assert en_req_count <= ru_req_count


def test_normalize_ru_keeps_null_marketing_title_en(load_fixture):
    ru = normalize_roadmap(load_fixture("en_with_content.json"), language="ru")
    reqs = ru.products[0].streams[0].tiers[0].releases[0].requirements
    # в RU-версии null-требование не отбрасывается
    assert len(reqs) == 3
    assert any(r.marketing_title_en is None for r in reqs)


# ---------------------------------------------------------------------------
# Нормализация: мягкие fallback'и опциональных полей
# ---------------------------------------------------------------------------

def test_normalize_kbr_s2c_fallbacks(load_fixture):
    model = normalize_roadmap(load_fixture("missing_optional_fields.json"), language="ru")
    reqs = model.products[0].streams[0].tiers[0].releases[0].requirements
    by_id = {r.id: r for r in reqs}

    assert by_id[10001].kbr == "No"
    assert by_id[10001].is_subject_to_change is False

    assert by_id[10002].kbr == "Yes"
    assert by_id[10002].is_subject_to_change is True

    # нет Kbr -> None -> не S2C
    assert by_id[10003].kbr is None
    assert by_id[10003].is_subject_to_change is False

    assert by_id[10004].kbr is None
    assert by_id[10004].is_subject_to_change is False

    # warning: 2 без Kbr
    assert any("Kbr" in w for w in model.warnings)


def test_normalize_real_data_kbr_yes_means_s2c(real_data):
    model = normalize_roadmap(real_data, language="ru")
    next_tier = model.products[0].streams[0].tiers[0]
    for release in next_tier.releases:
        for req in release.requirements:
            assert req.is_subject_to_change is True


def test_normalize_stc_absent_is_not_validation_error(load_fixture):
    data = load_fixture("missing_optional_fields.json")
    assert validate_roadmap(data) == []


# ---------------------------------------------------------------------------
# Структура на реальных данных (интеграционный smoke)
# ---------------------------------------------------------------------------

def test_normalize_real_data_shape(real_data):
    model = normalize_roadmap(real_data, language="ru")
    # 20 продуктов в реальном файле
    assert len(model.products) == 20
    # только у Kaspersky Next есть контентные релизы
    next_product = next(p for p in model.products if p.name == "Kaspersky Next")
    opt_stream = next(s for s in next_product.streams if s.name == "Kaspersky Next Optimum")
    # Optimum: 4 тира (EDR Foundations / EDR Optimum / XDR Optimum / MXDR Optimum)
    assert len(opt_stream.tiers) == 4
    # Stream == "-" сохраняется как есть (используется в build_slide_plan)
    hcs = next(p for p in model.products if p.name == "Kaspersky Hybrid Cloud Security")
    assert hcs.streams[0].name == "-"


# ---------------------------------------------------------------------------
# Нормализация имён (канонический источник — Products list.xlsx)
# ---------------------------------------------------------------------------

def test_normalize_name_hyphen_spaces():
    assert _normalize_name("Kaspersky SD - WAN") == "Kaspersky SD-WAN"
    assert _normalize_name("Kaspersky Anti - Virus SDK") == "Kaspersky Anti-Virus SDK"


def test_normalize_name_collapses_whitespace_and_trims():
    assert _normalize_name("  Kaspersky   SD  -   WAN  ") == "Kaspersky SD-WAN"
    assert _normalize_name("Kaspersky Automated Security Awareness Platform ") == (
        "Kaspersky Automated Security Awareness Platform"
    )


def test_normalize_name_preserves_dash_sentinel():
    assert _normalize_name("-") == "-"


def test_normalize_applies_to_all_name_fields():
    data = [
        {
            "Product": "Kaspersky Anti - Virus SDK",
            "Streams": [
                {
                    "Stream": "Some - Stream",
                    "Tiers": [
                        {
                            "Tier": "Some - Tier",
                            "Releases": [
                                {
                                    "Id": 1,
                                    "AppTitle": "App - Title",
                                    "TrDate": "15.01.2025 21:00:00",
                                    "Requirements": [{"Id": 10, "MarketingTitle": "x"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    model = normalize_roadmap(data, language="ru")
    p = model.products[0]
    assert p.name == "Kaspersky Anti-Virus SDK"
    assert p.streams[0].name == "Some-Stream"
    tier = p.streams[0].tiers[0]
    assert tier.name == "Some-Tier"
    assert tier.releases[0].app_title == "App-Title"


def test_normalize_real_data_matches_canonical_names(real_data):
    model = normalize_roadmap(real_data, language="ru")
    names = {p.name for p in model.products}
    # канонические написания из Products list.xlsx (без пробелов вокруг дефиса)
    assert "Kaspersky SD-WAN" in names
    assert "Kaspersky Anti-Virus SDK" in names
    assert "Kaspersky SD - WAN" not in names
    assert "Kaspersky Anti - Virus SDK" not in names
