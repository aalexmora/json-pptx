"""Схема и валидация входных данных roadmap.

Модуль не зависит от python-pptx и FastAPI — только stdlib. Содержит
`validate_roadmap` (сбор всех ошибок за один проход) и `normalize_roadmap`
(разворачивание сырого JSON в типизированную `RoadmapModel` с вычислением
календарных кварталов и применением EN-фильтра). Плагины здесь НЕ применяются —
они работают поверх `RoadmapModel` в `plugins_engine.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Literal, Optional

# Поддерживаемые форматы `TrDate`: исходный из ТЗ и фактическая выгрузка из продакшена.
# В продакшене даты приходят в US-формате 12-часового цикла («6/29/2026 9:00:00 PM»).
DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",     # «15.01.2025 21:00:00»
    "%m/%d/%Y %I:%M:%S %p",  # «6/29/2026 9:00:00 PM»
)
Language = Literal["ru", "en"]

_VISIBILITY_LANGUAGES = {
    "only ru": frozenset({"ru"}),
    "ru": frozenset({"ru"}),
    "only eng": frozenset({"en"}),
    "eng": frozenset({"en"}),
    "ru and eng": frozenset({"ru", "en"}),
}


def _parse_date(value) -> datetime:
    """Парсит `TrDate`, перебирая известные форматы; ValueError — если ни один не подошёл."""
    if not isinstance(value, str):
        raise ValueError(f"ожидалась строка, получен {type(value).__name__}")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"'{value}' не парсится ни одним из форматов {DATE_FORMATS}")


@dataclass
class Requirement:
    id: int
    title: str                      # техническое имя (Title), НЕ выводится на слайд
    kbr: Optional[str]              # "Yes" | "No" | None (None = поле отсутствовало)
    marketing_title: str            # RU, обязательное
    marketing_title_en: Optional[str]
    is_subject_to_change: bool


@dataclass
class Release:
    id: int
    title: str                      # внутреннее имя релиза, НЕ выводится на слайд
    app_id: Optional[int]
    app_title: str
    tr_date: datetime
    cr_date: Optional[datetime]
    quarter: str                    # "Qx YYYY" (календарный квартал)
    requirements: List[Requirement]


@dataclass
class Tier:
    name: str
    releases: List[Release]


@dataclass
class Stream:
    name: str
    tiers: List[Tier]


@dataclass
class Product:
    name: str
    streams: List[Stream]


@dataclass
class RoadmapModel:
    language: Language
    products: List[Product]
    warnings: List[str] = field(default_factory=list)
    quality_issues: List[dict] = field(default_factory=list)


def _quarter(dt: datetime) -> str:
    """Календарный квартал: Q1 = янв-мар, Q2 = апр-июн и т.д."""
    return f"Q{((dt.month - 1) // 3) + 1} {dt.year}"


_HYPHEN_SPACES = re.compile(r"\s*-\s*")


def _normalize_name(value) -> str:
    """Нормализует брендовое имя (Product/Stream/Tier/AppTitle) к каноническому виду.

    Канонический источник — `Products list.xlsx`. Правило (согласовано): схлопнуть
    пробелы/control-символы и убрать пробелы вокруг дефиса, чтобы
    «Kaspersky SD - WAN» → «Kaspersky SD-WAN», «Kaspersky Anti - Virus SDK» →
    «Kaspersky Anti-Virus SDK». Имена НЕ переводятся — только написание.
    """
    s = str(value or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = _HYPHEN_SPACES.sub("-", s)
    return s


def _visibility_languages(value) -> Optional[frozenset[str]]:
    """Возвращает языки Visibility; None означает неизвестное значение.

    Отсутствующее/null поле по согласованному fallback разрешает обе версии.
    """
    if value is None:
        return frozenset({"ru", "en"})
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return _VISIBILITY_LANGUAGES.get(normalized)


def validate_roadmap(data) -> List[str]:
    """Собирает все ошибки валидации за один проход.

    Возвращает список строк-описаний ошибок; пустой список = данные валидны.
    Отсутствие опциональных полей (`Kbr`, `MarketingTitleEn`, `Visibility`) ошибкой НЕ является —
    это мягкий fallback + warning в `normalize_roadmap`.
    """
    errors: List[str] = []

    if not isinstance(data, list) or len(data) == 0:
        return ["входные данные должны быть непустым списком (array)"]

    for pi, product in enumerate(data):
        prefix = f"Product[{pi}]"
        if not isinstance(product, dict):
            errors.append(f"{prefix}: ожидался объект, получен {type(product).__name__}")
            continue

        name = product.get("Product")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}: отсутствует непустое поле 'Product'")

        streams = product.get("Streams")
        if not isinstance(streams, list):
            errors.append(f"{prefix}: отсутствует поле 'Streams' (список)")
            continue

        for si, stream in enumerate(streams):
            sprefix = f"{prefix}.Streams[{si}]"
            if not isinstance(stream, dict):
                errors.append(f"{sprefix}: ожидался объект, получен {type(stream).__name__}")
                continue

            if not isinstance(stream.get("Stream"), str):
                errors.append(f"{sprefix}: отсутствует поле 'Stream' (строка)")

            tiers = stream.get("Tiers")
            if not isinstance(tiers, list):
                errors.append(f"{sprefix}: отсутствует поле 'Tiers' (список)")
                continue

            for ti, tier in enumerate(tiers):
                tprefix = f"{sprefix}.Tiers[{ti}]"
                if not isinstance(tier, dict):
                    errors.append(f"{tprefix}: ожидался объект, получен {type(tier).__name__}")
                    continue

                if not isinstance(tier.get("Tier"), str):
                    errors.append(f"{tprefix}: отсутствует поле 'Tier' (строка)")

                releases = tier.get("Releases")
                if not isinstance(releases, list):
                    errors.append(f"{tprefix}: отсутствует поле 'Releases' (список)")
                    continue

                for ri, release in enumerate(releases):
                    rprefix = f"{tprefix}.Releases[{ri}]"
                    if not isinstance(release, dict):
                        errors.append(f"{rprefix}: ожидался объект, получен {type(release).__name__}")
                        continue

                    rid = release.get("Id")
                    if not isinstance(rid, int):
                        errors.append(f"{rprefix}: поле 'Id' должно быть int")

                    if not isinstance(release.get("AppTitle"), str):
                        errors.append(f"{rprefix}: отсутствует поле 'AppTitle' (строка)")

                    trdate = release.get("TrDate")
                    if not isinstance(trdate, str):
                        errors.append(f"{rprefix}: отсутствует поле 'TrDate' (строка)")
                    else:
                        try:
                            _parse_date(trdate)
                        except ValueError:
                            errors.append(
                                f"{rprefix}: 'TrDate'='{trdate}' не парсится (форматы: {DATE_FORMATS})"
                            )

                    crdate = release.get("CrDate")
                    if crdate is not None:
                        if not isinstance(crdate, str):
                            errors.append(f"{rprefix}: поле 'CrDate' должно быть строкой или null")
                        else:
                            try:
                                _parse_date(crdate)
                            except ValueError:
                                errors.append(
                                    f"{rprefix}: 'CrDate'='{crdate}' не парсится (форматы: {DATE_FORMATS})"
                                )

                    reqs = release.get("Requirements")
                    if not isinstance(reqs, list):
                        errors.append(f"{rprefix}: отсутствует поле 'Requirements' (список)")
                        continue

                    for qi, req in enumerate(reqs):
                        qprefix = f"{rprefix}.Requirements[{qi}]"
                        if not isinstance(req, dict):
                            errors.append(f"{qprefix}: ожидался объект, получен {type(req).__name__}")
                            continue

                        qid = req.get("Id")
                        if not isinstance(qid, int):
                            errors.append(f"{qprefix}: поле 'Id' должно быть int")

                        mtitle = req.get("MarketingTitle")
                        if not isinstance(mtitle, str) or not mtitle.strip():
                            errors.append(f"{qprefix}: отсутствует непустое поле 'MarketingTitle'")

    return errors


def normalize_roadmap(data: list, language: Language) -> RoadmapModel:
    """Разворачивает сырой JSON в типизированную `RoadmapModel`.

    - вычисляет календарный квартал для каждого Release из `CrDate`;
      если `CrDate` отсутствует/null, использует `TrDate` и создаёт замечание качества;
    - фильтрует Requirements по `Visibility` для выбранного языка;
    - при `language == "en"` дополнительно отбрасывает Requirements без `MarketingTitleEn`;
    - `Kbr == "Yes"` — признак «Subject to Change» (S2C): помечает фичу как под вопросом.

    Плагины здесь НЕ применяются.
    """
    products: List[Product] = []
    missing_kbr = 0
    seen_release_ids: set[int] = set()
    seen_req_ids: set[int] = set()
    dup_releases = 0
    dup_reqs = 0
    unknown_visibility: dict[str, int] = {}
    quality_issues: List[dict] = []

    for raw_product in data:
        streams: List[Stream] = []
        for raw_stream in raw_product.get("Streams", []):
            tiers: List[Tier] = []
            for raw_tier in raw_stream.get("Tiers", []):
                releases: List[Release] = []
                for raw_release in raw_tier.get("Releases", []):
                    tr_date = _parse_date(raw_release["TrDate"])
                    raw_cr_date = raw_release.get("CrDate")
                    cr_date = _parse_date(raw_cr_date) if raw_cr_date is not None else None
                    display_date = cr_date or tr_date
                    quarter = _quarter(display_date)
                    if cr_date is None:
                        quality_issues.append({
                            "code": "missing_crdate",
                            "severity": "warning",
                            "message": "CrDate не заполнена — квартал рассчитан по TrDate",
                            "release_id": raw_release["Id"],
                            "rpp_title": (
                                raw_release.get("RppTitle")
                                or raw_release.get("RPPTitle")
                                or raw_release.get("Title")
                                or ""
                            ),
                            "trdate": raw_release["TrDate"],
                            "quarter": quarter,
                            "product": _normalize_name(raw_product.get("Product")),
                            "stream": _normalize_name(raw_stream.get("Stream")),
                            "tier": _normalize_name(raw_tier.get("Tier")),
                        })
                    rid = raw_release["Id"]
                    if rid in seen_release_ids:
                        dup_releases += 1
                    seen_release_ids.add(rid)
                    requirements: List[Requirement] = []
                    for raw_req in raw_release.get("Requirements", []):
                        qid = raw_req["Id"]
                        if qid in seen_req_ids:
                            dup_reqs += 1
                        seen_req_ids.add(qid)
                        kbr = raw_req.get("Kbr")
                        if "Kbr" not in raw_req:
                            missing_kbr += 1

                        # KBR == "Yes" → фича под вопросом (Subject to Change, S2C)
                        is_subject_to_change = (kbr == "Yes")

                        visibility = raw_req.get("Visibility")
                        visible_in = _visibility_languages(visibility)
                        if visible_in is None:
                            label = repr(visibility)
                            unknown_visibility[label] = unknown_visibility.get(label, 0) + 1
                            continue
                        if language not in visible_in:
                            continue

                        marketing_title_en = raw_req.get("MarketingTitleEn")
                        if language == "en" and (
                            not isinstance(marketing_title_en, str) or not marketing_title_en.strip()
                        ):
                            continue

                        requirements.append(Requirement(
                            id=raw_req["Id"],
                            title=raw_req.get("Title") or "",
                            kbr=kbr,
                            marketing_title=raw_req.get("MarketingTitle") or "",
                            marketing_title_en=marketing_title_en,
                            is_subject_to_change=is_subject_to_change,
                        ))

                    releases.append(Release(
                        id=raw_release["Id"],
                        title=raw_release.get("Title") or "",
                        app_id=raw_release.get("AppId"),
                        app_title=_normalize_name(raw_release.get("AppTitle")),
                        tr_date=tr_date,
                        cr_date=cr_date,
                        quarter=quarter,
                        requirements=requirements,
                    ))

                tiers.append(Tier(name=_normalize_name(raw_tier.get("Tier")), releases=releases))
            streams.append(Stream(name=_normalize_name(raw_stream.get("Stream")), tiers=tiers))
        products.append(Product(name=_normalize_name(raw_product.get("Product")), streams=streams))

    warnings: List[str] = []
    if missing_kbr:
        warnings.append(f"{missing_kbr} требований без поля Kbr — принято как не subject to change")
    if dup_releases or dup_reqs:
        warnings.append(
            f"{dup_releases} релизов и {dup_reqs} требований с неуникальными Id — "
            f"общие сущности повторяются в разных Streams/Tiers, принято как есть"
        )
    if unknown_visibility:
        values = ", ".join(
            f"{value}: {count}" for value, count in sorted(unknown_visibility.items())
        )
        warnings.append(
            f"Неизвестные значения Visibility ({values}) — требования скрыты"
        )

    return RoadmapModel(
        language=language,
        products=products,
        warnings=warnings,
        quality_issues=quality_issues,
    )
