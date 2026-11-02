"""Расчёты отчётности по сырому roadmap JSON и загруженному CSV.

Модуль не зависит от FastAPI и python-pptx. CSV используется только как
временный источник данных: файл читается из bytes и нигде не сохраняется.
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from datetime import datetime
from io import StringIO
from typing import Any
from urllib.parse import urlparse


_DATE_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
)
_TRUE_VALUES = {"1", "true", "yes", "y", "да"}
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


def _is_published(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    return isinstance(value, str) and value.strip().casefold() in _TRUE_VALUES


def _normalized_header(value: Any) -> str:
    return re.sub(r"[^a-zа-я0-9]+", "", str(value or "").strip().casefold())


def _header_indexes(row: tuple[Any, ...]) -> dict[str, int] | None:
    aliases = {
        "req_id": ("reqid", "requirementid"),
        "is_published": ("ispublished", "published"),
        "applicable_for_products": ("applicableforproducts", "applicableproducts"),
        "product": ("application", "product", "productname"),
        "title": ("requirement", "requirementtitle", "feature", "title"),
    }
    normalized = [_normalized_header(value) for value in row]
    indexes: dict[str, int] = {}
    for field, names in aliases.items():
        index = next(
            (
                normalized.index(alias)
                for alias in names
                if alias in normalized
            ),
            None,
        )
        if index is not None:
            indexes[field] = index
    if {"req_id", "is_published", "applicable_for_products"} <= indexes.keys():
        return indexes
    return None


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


def collect_json_requirement_ids(data: list[dict]) -> set[str]:
    ids: set[str] = set()
    for _, _, _, release in _iter_releases(data):
        requirements = release.get("Requirements")
        if not isinstance(requirements, list):
            continue
        for requirement in requirements:
            if not isinstance(requirement, dict):
                continue
            req_id = _normalize_req_id(requirement.get("Id"))
            if req_id is not None:
                ids.add(req_id)
    return ids


def _decode_csv(csv_bytes: bytes) -> str:
    encodings = ("utf-16",) if csv_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else (
        "utf-8-sig",
        "cp1251",
    )
    for encoding in encodings:
        try:
            return csv_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось определить кодировку CSV (поддерживаются UTF-8, UTF-16 и Windows-1251)")


def _csv_reader_with_headers(text: str) -> tuple[Iterator[list[str]], dict[str, int]]:
    sample = text[:65536]
    delimiters: list[str] = []
    try:
        delimiters.append(csv.Sniffer().sniff(sample, delimiters="\t;,").delimiter)
    except csv.Error:
        pass
    for delimiter in ("\t", ";", ","):
        if delimiter not in delimiters:
            delimiters.append(delimiter)

    for delimiter in delimiters:
        rows = csv.reader(StringIO(text), delimiter=delimiter)
        for _ in range(50):
            row = next(rows, None)
            if row is None:
                break
            indexes = _header_indexes(tuple(row))
            if indexes is not None:
                return rows, indexes
    raise ValueError(
        "В CSV не найдены обязательные колонки ReqId, IsPublished и ApplicableForProducts"
    )


def _complete_products_by_year(
    json_data: list[dict],
    applicable_req_ids: set[str],
) -> dict[str, list[str]]:
    releases_by_product_year: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for product, _, _, release in _iter_releases(json_data):
        trdate = _parse_date(release.get("TrDate"))
        if trdate is not None and trdate.year in REPORT_YEARS:
            releases_by_product_year[(product, trdate.year)].append(release)

    result: dict[str, list[str]] = {}
    for year in REPORT_YEARS:
        complete: list[str] = []
        products = sorted({product for product, item_year in releases_by_product_year if item_year == year}, key=str.casefold)
        for product in products:
            releases = releases_by_product_year[(product, year)]
            is_complete = True
            for release in releases:
                requirements = release.get("Requirements")
                if not _parseable_date(release.get("CrDate")) or not isinstance(requirements, list) or not requirements:
                    is_complete = False
                    break
                for requirement in requirements:
                    req_id = _normalize_req_id(requirement.get("Id")) if isinstance(requirement, dict) else None
                    if req_id is None or req_id not in applicable_req_ids:
                        is_complete = False
                        break
                if not is_complete:
                    break
            if is_complete:
                complete.append(product)
        result[str(year)] = complete
    return result


def analyze_public_features_csv(
    csv_bytes: bytes,
    json_data: list[dict],
    filename: str = "report.csv",
) -> dict[str, Any]:
    """Сопоставляет публичные фичи CSV с Requirements JSON по ReqId."""
    rows, indexes = _csv_reader_with_headers(_decode_csv(csv_bytes))

    public_by_id: dict[str, dict[str, Any]] = {}
    product_ids: dict[str, set[str]] = defaultdict(set)
    applicable_req_ids: set[str] = set()
    data_rows = 0
    invalid_req_id_rows = 0

    for row in rows:
        data_rows += 1
        req_id = _normalize_req_id(
            row[indexes["req_id"]] if indexes["req_id"] < len(row) else None
        )
        if req_id is None:
            if any(value.strip() for value in row):
                invalid_req_id_rows += 1
            continue
        applicable = (
            row[indexes["applicable_for_products"]]
            if indexes["applicable_for_products"] < len(row)
            else ""
        )
        if str(applicable or "").strip():
            applicable_req_ids.add(req_id)
        published = _is_published(
            row[indexes["is_published"]]
            if indexes["is_published"] < len(row)
            else None
        )
        if not published:
            continue

        product = "Без продукта"
        if "product" in indexes and indexes["product"] < len(row):
            product = str(row[indexes["product"]] or "").strip() or product
        title = ""
        if "title" in indexes and indexes["title"] < len(row):
            title = str(row[indexes["title"]] or "").strip()

        item = public_by_id.setdefault(req_id, {
            "req_id": req_id,
            "title": title,
            "products": set(),
        })
        if not item["title"] and title:
            item["title"] = title
        item["products"].add(product)
        product_ids[product].add(req_id)

    if not public_by_id:
        raise ValueError("В CSV нет строк с IsPublished=true и корректным ReqId")

    json_ids = collect_json_requirement_ids(json_data)
    public_ids = set(public_by_id)
    mapped_ids = public_ids & json_ids
    unmapped_ids = public_ids - json_ids

    products = []
    for product, ids in product_ids.items():
        public_ids_for_product = ids & public_ids
        unmapped_for_product = public_ids_for_product - json_ids
        if not unmapped_for_product:
            continue
        requirements = [
            {
                "req_id": req_id,
                "title": public_by_id[req_id]["title"],
            }
            for req_id in sorted(unmapped_for_product, key=lambda value: (len(value), value))
        ]
        products.append({
            "product": product,
            "public": len(public_ids_for_product),
            "mapped": len(public_ids_for_product & json_ids),
            "unmapped": len(unmapped_for_product),
            "requirements": requirements,
        })
    products.sort(key=lambda item: (-item["unmapped"], item["product"].casefold()))

    return {
        "filename": filename,
        "data_rows": data_rows,
        "invalid_req_id_rows": invalid_req_id_rows,
        "public_features": len(public_ids),
        "mapped_public_features": len(mapped_ids),
        "unmapped_public_features": len(unmapped_ids),
        "mapped_percent": round(len(mapped_ids) * 100 / len(public_ids), 1),
        "products": products,
        "complete_products_by_year": _complete_products_by_year(
            json_data, applicable_req_ids,
        ),
    }
