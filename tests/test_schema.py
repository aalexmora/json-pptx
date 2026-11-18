"""Тесты для `roadmap_generator/schema.py` (Этап 1).

Покрывают валидацию, нормализацию, вычисление календарных кварталов, EN-фильтр
и мягкие fallback'и опциональных полей на реальных данных и синтетических
фикстурах (ТЗ v4 раздел 11).
"""
from __future__ import annotations

from roadmap_generator.schema import (
    SERVICE_PRODUCT_NAME,
    _normalize_name,
    is_service_product,
    normalize_roadmap,
    validate_roadmap,
)


def _service_product_node() -> dict:
    """Служебный узел экспортёра в том виде, в котором он приходит последним в массиве."""
    return {
        "Product": SERVICE_PRODUCT_NAME,
        "Streams": [{"Stream": "-", "Tiers": [{"Tier": "-", "Releases": [{
            "Id": 900, "Title": "Release without product", "AppId": 9, "AppTitle": "App X",
            "TrDate": "2/26/2026 12:00:00 AM", "CrDate": None,
            "Requirements": [{"Id": 9001, "Title": "Orphan", "ApplicableForProduct": None}],
        }]}]}],
    }


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


def test_console_type_is_optional_and_normalized():
    data = [{
        "Product": "Kaspersky Next",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1, "AppTitle": "A", "TrDate": "15.01.2025 21:00:00",
            "Requirements": [
                {"Id": 10, "MarketingTitle": "Expert", "ConsoleType": " Expert View "},
                {"Id": 11, "MarketingTitle": "Legacy"},
            ],
        }]}]}],
    }]

    assert validate_roadmap(data) == []
    requirements = normalize_roadmap(data, language="ru").products[0].streams[0].tiers[0].releases[0].requirements
    assert [requirement.console_type for requirement in requirements] == ["Expert View", None]


def test_validate_rejects_non_list():
    assert validate_roadmap({"Product": "X"}) != []


def test_validate_rejects_empty_list():
    assert validate_roadmap([]) != []


def test_service_product_node_is_recognized_by_exact_name():
    assert is_service_product(_service_product_node())
    assert is_service_product({"Product": f"  {SERVICE_PRODUCT_NAME} "})
    assert not is_service_product({"Product": "Kaspersky Next"})
    assert not is_service_product("not a product")


def test_service_product_node_is_skipped_by_validation_and_normalization(load_fixture):
    data = load_fixture("pagination_5_quarters.json")
    broken_service_node = _service_product_node()
    # Служебный узел не проверяется: даже без обязательных полей ошибок нет.
    del broken_service_node["Streams"][0]["Tiers"][0]["Releases"][0]["AppTitle"]
    with_node = data + [broken_service_node]

    assert validate_roadmap(with_node) == []
    plain = normalize_roadmap(data, language="ru")
    model = normalize_roadmap(with_node, language="ru")
    assert [product.name for product in model.products] == [product.name for product in plain.products]
    assert model.quality_issues == plain.quality_issues
    assert model.warnings == plain.warnings


def test_json_with_only_service_product_node_is_rejected():
    errors = validate_roadmap([_service_product_node()])

    assert len(errors) == 1
    assert SERVICE_PRODUCT_NAME in errors[0]


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


def test_validate_allows_duplicate_release_id():
    """Общие релизы повторяются в разных Streams/Tiers — неуникальный Id не ошибка."""
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
                                    "Requirements": [{"Id": 10, "MarketingTitle": "ok"}],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    assert validate_roadmap(data) == []
    model = normalize_roadmap(data, language="ru")
    assert any("неуникальными Id" in w for w in model.warnings)


def test_validate_parses_us_12h_date():
    """Продакшен-выгрузка присылает US-дату «6/29/2026 9:00:00 PM» — должна парситься."""
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
                                    "TrDate": "6/29/2026 9:00:00 PM",
                                    "Requirements": [{"Id": 10, "MarketingTitle": "ok"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    assert validate_roadmap(data) == []
    model = normalize_roadmap(data, language="ru")
    # 29.06.2026 → Q2 2026
    assert model.products[0].streams[0].tiers[0].releases[0].quarter == "Q2 2026"


def test_crdate_defines_display_quarter_instead_of_trdate():
    data = [{
        "Product": "P",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1,
            "Title": "RPP release",
            "AppTitle": "A",
            "TrDate": "29.06.2026 21:00:00",
            "CrDate": "01.07.2026 21:00:00",
            "Requirements": [{"Id": 10, "MarketingTitle": "ok"}],
        }]}]}],
    }]

    assert validate_roadmap(data) == []
    model = normalize_roadmap(data, language="ru")
    release = model.products[0].streams[0].tiers[0].releases[0]
    assert release.quarter == "Q3 2026"
    assert release.cr_date is not None
    assert model.quality_issues == []


def test_null_crdate_falls_back_to_trdate_and_creates_quality_issue():
    data = [{
        "Product": "P",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1,
            "Title": "RPP release",
            "AppTitle": "A",
            "TrDate": "29.06.2026 21:00:00",
            "CrDate": None,
            "Requirements": [{"Id": 10, "MarketingTitle": "ok"}],
        }]}]}],
    }]

    assert validate_roadmap(data) == []
    model = normalize_roadmap(data, language="ru")
    release = model.products[0].streams[0].tiers[0].releases[0]
    assert release.quarter == "Q2 2026"
    assert release.cr_date is None
    assert model.quality_issues == [{
        "code": "missing_crdate",
        "severity": "warning",
        "message": "CrDate не заполнена — квартал рассчитан по TrDate",
        "release_id": 1,
        "rpp_title": "RPP release",
        "trdate": "29.06.2026 21:00:00",
        "quarter": "Q2 2026",
        "product": "P",
        "stream": "S",
        "tier": "T",
    }]


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

def test_normalize_en_keeps_title_when_marketing_title_en_is_null(load_fixture):
    ru = normalize_roadmap(load_fixture("en_with_content.json"), language="ru")
    en = normalize_roadmap(load_fixture("en_with_content.json"), language="en")
    ru_req_count = sum(len(r.requirements) for r in ru.products[0].streams[0].tiers[0].releases)
    en_req_count = sum(len(r.requirements) for r in en.products[0].streams[0].tiers[0].releases)
    # У требования без EN-заголовка используется Title.
    assert ru_req_count == 3
    assert en_req_count == 3
    fallback = next(req for req in en.products[0].streams[0].tiers[0].releases[0].requirements if req.id == 8002)
    assert fallback.marketing_title_en == "[BRQ] Null EN text"


def test_normalize_ru_keeps_null_marketing_title_en(load_fixture):
    ru = normalize_roadmap(load_fixture("en_with_content.json"), language="ru")
    reqs = ru.products[0].streams[0].tiers[0].releases[0].requirements
    # в RU-версии null-требование не отбрасывается
    assert len(reqs) == 3
    assert any(r.marketing_title_en is None for r in reqs)


def _visibility_data() -> list:
    requirements = [
        {"Id": 1, "Kbr": "Yes", "MarketingTitle": "RU only", "MarketingTitleEn": "RU only EN", "Visibility": "Only RU"},
        {"Id": 2, "Kbr": "Yes", "MarketingTitle": "RU alias", "MarketingTitleEn": "RU alias EN", "Visibility": "RU"},
        {"Id": 3, "Kbr": "Yes", "MarketingTitle": "EN only RU", "MarketingTitleEn": "EN only", "Visibility": "Only ENG"},
        {"Id": 4, "Kbr": "Yes", "MarketingTitle": "ENG alias RU", "MarketingTitleEn": "ENG alias", "Visibility": "ENG"},
        {"Id": 5, "Kbr": "Yes", "MarketingTitle": "Both RU", "MarketingTitleEn": "Both EN", "Visibility": "RU and ENG"},
        {"Id": 6, "Kbr": "Yes", "MarketingTitle": "Null RU", "MarketingTitleEn": "Null EN", "Visibility": None},
        {"Id": 7, "Kbr": "Yes", "MarketingTitle": "Missing visibility RU", "MarketingTitleEn": "Missing visibility EN"},
        {"Id": 8, "Title": "Technical visible title", "Kbr": "Yes", "MarketingTitle": "No EN title", "MarketingTitleEn": None, "Visibility": "RU and ENG"},
    ]
    return [{
        "Product": "P",
        "Streams": [{"Stream": "S", "Tiers": [{"Tier": "T", "Releases": [{
            "Id": 1,
            "AppTitle": "A",
            "TrDate": "15.01.2025 21:00:00",
            "Requirements": requirements,
        }]}]}],
    }]


def test_visibility_filters_requirements_for_ru_and_en():
    ru = normalize_roadmap(_visibility_data(), language="ru")
    en = normalize_roadmap(_visibility_data(), language="en")

    ru_ids = {req.id for req in ru.products[0].streams[0].tiers[0].releases[0].requirements}
    en_ids = {req.id for req in en.products[0].streams[0].tiers[0].releases[0].requirements}

    assert ru_ids == {1, 2, 5, 6, 7, 8}
    assert en_ids == {3, 4, 5, 6, 7, 8}


def test_unknown_visibility_is_hidden_with_warning():
    data = _visibility_data()
    data[0]["Streams"][0]["Tiers"][0]["Releases"][0]["Requirements"].append({
        "Id": 9,
        "Kbr": "Yes",
        "MarketingTitle": "Unknown RU",
        "MarketingTitleEn": "Unknown EN",
        "Visibility": "Internal only",
    })

    model = normalize_roadmap(data, language="ru")
    reqs = model.products[0].streams[0].tiers[0].releases[0].requirements

    assert 9 not in {req.id for req in reqs}
    assert any("'Internal only': 1" in warning for warning in model.warnings)


# ---------------------------------------------------------------------------
# Нормализация: мягкие fallback'и опциональных полей
# ---------------------------------------------------------------------------

def test_normalize_kbr_s2c_fallbacks(load_fixture):
    model = normalize_roadmap(load_fixture("missing_optional_fields.json"), language="ru")
    reqs = model.products[0].streams[0].tiers[0].releases[0].requirements
    by_id = {r.id: r for r in reqs}

    assert by_id[10001].kbr == "No"
    assert by_id[10001].is_subject_to_change is False

    assert by_id[10002].kbr == "Subject To Change"
    assert by_id[10002].is_subject_to_change is True

    # нет Kbr -> None -> не S2C
    assert by_id[10003].kbr is None
    assert by_id[10003].is_subject_to_change is False

    assert by_id[10004].kbr is None
    assert by_id[10004].is_subject_to_change is False

    # warning: 2 без Kbr
    assert any("Kbr" in w for w in model.warnings)


def test_normalize_real_data_kbr_yes_is_not_s2c(real_data):
    model = normalize_roadmap(real_data, language="ru")
    next_tier = model.products[0].streams[0].tiers[0]
    for release in next_tier.releases:
        for req in release.requirements:
            assert req.is_subject_to_change is False


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
