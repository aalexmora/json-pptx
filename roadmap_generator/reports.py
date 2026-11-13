"""Расчёты годовых отчётов и проверок по текущему roadmap JSON."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


_DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
)
REPORT_YEARS = (2026, 2027)
ENGLISH_NAME_TERMS = (
    "ФСТЕК", "ФСТЭК", "FSTEC", "FSB", "ФСБ", "СБЕР", "SBER",
    "Yandex", "Яндекс", "Astra", "Астра",
)
_ENGLISH_NAME_PATTERN = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(term) for term in ENGLISH_NAME_TERMS) + r")(?!\w)",
    re.IGNORECASE,
)


def _iter_releases(data: list[dict]):
    for product in data:
        if not isinstance(product, dict):
            continue
        product_name = str(product.get("Product") or "").strip()
        for stream in product.get("Streams", []):
            if not isinstance(stream, dict):
                continue
            stream_name = str(stream.get("Stream") or "").strip()
            for tier in stream.get("Tiers", []):
                if not isinstance(tier, dict):
                    continue
                tier_name = str(tier.get("Tier") or "").strip()
                for release in tier.get("Releases", []):
                    if isinstance(release, dict):
                        yield product_name, stream_name, tier_name, release


def _parseable_date(value: Any) -> bool:
    return _parse_date(value) is not None


def _parse_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _http_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _normalize_req_id(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


def build_json_report(data: list[dict]) -> dict[str, Any]:
    """Возвращает независимые сводки за 2026 и 2027 годы по `TrDate`."""
    releases_by_year: dict[int, list[tuple[str, str, str, dict[str, Any]]]] = {
        year: [] for year in REPORT_YEARS
    }
    for product, stream, tier, release in _iter_releases(data):
        trdate = _parse_date(release.get("TrDate"))
        if trdate is not None and trdate.year in releases_by_year:
            releases_by_year[trdate.year].append((product, stream, tier, release))

    return {
        "english_name_issues": _find_english_name_issues(data),
        "years": {
            str(year): _build_year_report(releases_by_year[year])
            for year in REPORT_YEARS
        },
    }


def _find_english_name_issues(data: list[dict]) -> list[dict[str, Any]]:
    """Find branded terms in every MarketingTitleEn occurrence in the source JSON."""
    issues: list[dict[str, Any]] = []
    for product, stream, tier, release in _iter_releases(data):
        requirements = release.get("Requirements")
        if not isinstance(requirements, list):
            continue
        release_title = str(
            release.get("RppTitle") or release.get("RPPTitle") or release.get("Title") or ""
        )
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            title = requirement.get("MarketingTitleEn")
            if not isinstance(title, str) or not title:
                continue
            matches = list(dict.fromkeys(match.group(0) for match in _ENGLISH_NAME_PATTERN.finditer(title)))
            if matches:
                issues.append({
                    "product": product,
                    "stream": stream,
                    "tier": tier,
                    "release_id": release.get("Id"),
                    "release_title": release_title,
                    "requirement_id": _normalize_req_id(requirement.get("Id")),
                    "marketing_title_en": title,
                    "matched_terms": matches,
                })
    return issues


def _build_year_report(
    releases: list[tuple[str, str, str, dict[str, Any]]],
) -> dict[str, Any]:
    requirement_occurrences: Counter[str] = Counter()
    release_problems: list[dict[str, Any]] = []

    for product, stream, tier, release in releases:
        requirements = release.get("Requirements")
        if isinstance(requirements, list):
            for requirement in requirements:
                if not isinstance(requirement, dict):
                    continue
                req_id = _normalize_req_id(requirement.get("Id"))
                if req_id is not None:
                    requirement_occurrences[req_id] += 1

        codes: list[str] = []
        raw_crdate = release.get("CrDate")
        if raw_crdate is None or (isinstance(raw_crdate, str) and not raw_crdate.strip()):
            codes.append("missing_crdate")
        elif not _parseable_date(raw_crdate):
            codes.append("invalid_crdate")
        if not _parseable_date(release.get("TrDate")):
            codes.append("invalid_trdate")
        if not str(release.get("AppTitle") or "").strip():
            codes.append("missing_app_title")
        if not isinstance(requirements, list) or not requirements:
            codes.append("empty_requirements")

        if codes:
            release_problems.append({
                "release_id": release.get("Id"),
                "title": (
                    release.get("RppTitle")
                    or release.get("RPPTitle")
                    or release.get("Title")
                    or ""
                ),
                "product": product,
                "stream": stream,
                "tier": tier,
                "trdate": release.get("TrDate"),
                "crdate": release.get("CrDate"),
                "tfs_url": _http_url(release.get("TfsUrl")),
                "codes": codes,
            })

    def count_problem(code: str) -> int:
        return sum(code in item["codes"] for item in release_problems)

    occurrence_total = sum(requirement_occurrences.values())
    return {
        "requirements": {
            "unique": len(requirement_occurrences),
            "occurrences": occurrence_total,
            "reused": sum(count > 1 for count in requirement_occurrences.values()),
            "duplicate_occurrences": occurrence_total - len(requirement_occurrences),
        },
        "releases": {
            "total": len(releases),
            "with_problems": len(release_problems),
            "missing_crdate": count_problem("missing_crdate"),
            "invalid_crdate": count_problem("invalid_crdate"),
            "invalid_trdate": count_problem("invalid_trdate"),
            "missing_app_title": count_problem("missing_app_title"),
            "empty_requirements": count_problem("empty_requirements"),
        },
        "release_problems": release_problems,
    }
