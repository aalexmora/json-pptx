"""Отчёты раздела «Отчёты» по текущему roadmap JSON.

Год определяется по `Release.TrDate`. Для каждого года из `REPORT_YEARS`:

- общие показатели — уникальные требования и уникальные релизы года;
- «Не заполнено Applicable for products» — требования, у которых поле есть,
  но пустое; группы по `AppTitle` релиза;
- «Не указана CR date» — релизы без `CrDate`; группы по продукту;
- «Only RU» — требования с термином из словаря в `MarketingTitle` и
  Visibility «RU and ENG» или «Only RU»; группы по продукту.

Одни и те же требования и релизы повторяются под разными продуктами и Tier,
поэтому всё считается по уникальному `Id`. Требование относится к году, если
хотя бы один его релиз относится к этому году. Данные служебного узла
экспортёра входят в отчёты (в продуктовых отчётах — группой «Без продукта»),
но не в проверку ENG-названий: в презентацию они не попадают.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import urlparse

from roadmap_generator.report_terms import DEFAULT_TERMS, clean_terms
from roadmap_generator.schema import DATE_FORMATS, _normalize_name, is_service_product

REPORT_YEARS = (2026, 2027)
NO_PRODUCT_GROUP = "Без продукта"
NO_APP_TITLE_GROUP = "Без AppTitle"
_ONLY_RU_VISIBILITY = frozenset({"ru and eng", "only ru"})


@dataclass(frozen=True)
class _ReleaseEntry:
    product: str
    stream: str
    tier: str
    is_service: bool
    release: dict


def _dicts(value: Any) -> Iterator[dict]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def _iter_releases(data: Any) -> Iterator[_ReleaseEntry]:
    if not isinstance(data, list):
        return
    for product in _dicts(data):
        is_service = is_service_product(product)
        product_name = "" if is_service else _normalize_name(product.get("Product"))
        for stream in _dicts(product.get("Streams")):
            for tier in _dicts(stream.get("Tiers")):
                for release in _dicts(tier.get("Releases")):
                    yield _ReleaseEntry(
                        product=product_name or NO_PRODUCT_GROUP,
                        stream=_normalize_name(stream.get("Stream")),
                        tier=_normalize_name(tier.get("Tier")),
                        is_service=is_service,
                        release=release,
                    )


def _parse_date(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _http_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _normalize_id(value: Any) -> Optional[str]:
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


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple)):
        return all(_is_blank(item) for item in value)
    return False


def _applicable_is_empty(requirement: dict) -> bool:
    """Поле есть в JSON, но не заполнено. Отсутствующее поле не считается пустым."""
    return "ApplicableForProduct" in requirement and _is_blank(requirement["ApplicableForProduct"])


def _is_ru_visible(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return re.sub(r"\s+", " ", value).strip().casefold() in _ONLY_RU_VISIBILITY


def _terms_pattern(terms: list[str]) -> Optional[re.Pattern[str]]:
    if not terms:
        return None
    # Длинные термины раньше коротких: «Astra Linux» не должен съедаться «Astra».
    ordered = sorted(terms, key=len, reverse=True)
    return re.compile(
        r"(?<!\w)(?:" + "|".join(re.escape(term) for term in ordered) + r")(?!\w)",
        re.IGNORECASE,
    )


def _matched_terms(text: Any, pattern: Optional[re.Pattern[str]]) -> list[str]:
    if pattern is None or not isinstance(text, str) or not text:
        return []
    return list(dict.fromkeys(match.group(0) for match in pattern.finditer(text)))


def _release_title(release: dict, release_id: Optional[str]) -> str:
    for key in ("RppTitle", "RPPTitle", "Title", "AppTitle"):
        value = _text(release.get(key))
        if value:
            return value
    return f"Release {release_id}" if release_id else "Release"


def _requirement_title(requirement: dict, requirement_id: str) -> str:
    return (
        _text(requirement.get("Title"))
        or _text(requirement.get("MarketingTitle"))
        or f"Requirement {requirement_id}"
    )


class _Groups:
    """Уникальные элементы по группам: группы и элементы в порядке первого появления."""

    def __init__(self, last_group: str) -> None:
        self._last_group = last_group
        self._groups: dict[str, dict[str, dict[str, Any]]] = {}
        self._keys: set[str] = set()

    def add(self, group: str, key: str, item: dict[str, Any]) -> None:
        self._keys.add(key)
        self._groups.setdefault(group, {}).setdefault(key, item)

    def export(self) -> dict[str, Any]:
        names = [name for name in self._groups if name != self._last_group]
        if self._last_group in self._groups:
            names.append(self._last_group)
        return {
            "count": len(self._keys),
            "groups": [
                {
                    "name": name,
                    "count": len(self._groups[name]),
                    "items": list(self._groups[name].values()),
                }
                for name in names
            ],
        }


def build_json_report(data: Any, terms: Optional[Iterable[str]] = None) -> dict[str, Any]:
    """Возвращает отчёты за 2026 и 2027 годы и проверку ENG-названий по словарю."""
    term_list = clean_terms(DEFAULT_TERMS if terms is None else terms)
    pattern = _terms_pattern(term_list)
    entries = list(_iter_releases(data))

    entries_by_year: dict[int, list[_ReleaseEntry]] = {year: [] for year in REPORT_YEARS}
    for entry in entries:
        trdate = _parse_date(entry.release.get("TrDate"))
        if trdate is not None and trdate.year in entries_by_year:
            entries_by_year[trdate.year].append(entry)

    return {
        "terms": term_list,
        "english_name_issues": _find_english_name_issues(entries, pattern),
        "years": {
            str(year): _build_year_report(entries_by_year[year], pattern)
            for year in REPORT_YEARS
        },
    }


def _find_english_name_issues(
    entries: list[_ReleaseEntry],
    pattern: Optional[re.Pattern[str]],
) -> list[dict[str, Any]]:
    """Термины словаря в каждом вхождении MarketingTitleEn, кроме служебного узла."""
    issues: list[dict[str, Any]] = []
    for entry in entries:
        if entry.is_service:
            continue
        release = entry.release
        release_title = _text(release.get("RppTitle")) or _text(release.get("RPPTitle")) or _text(release.get("Title"))
        for requirement in _dicts(release.get("Requirements")):
            title = requirement.get("MarketingTitleEn")
            matches = _matched_terms(title, pattern)
            if matches:
                issues.append({
                    "product": entry.product,
                    "stream": entry.stream,
                    "tier": entry.tier,
                    "release_id": release.get("Id"),
                    "release_title": release_title,
                    "requirement_id": _normalize_id(requirement.get("Id")),
                    "marketing_title_en": title,
                    "matched_terms": matches,
                })
    return issues


def _build_year_report(
    entries: list[_ReleaseEntry],
    pattern: Optional[re.Pattern[str]],
) -> dict[str, Any]:
    requirement_ids: set[str] = set()
    release_ids: set[str] = set()
    missing_applicable = _Groups(last_group=NO_APP_TITLE_GROUP)
    missing_crdate = _Groups(last_group=NO_PRODUCT_GROUP)
    only_ru = _Groups(last_group=NO_PRODUCT_GROUP)

    for entry in entries:
        release = entry.release
        release_id = _normalize_id(release.get("Id"))
        # Релиз без Id нельзя сопоставить с другими вхождениями — считаем его отдельно.
        release_key = release_id if release_id is not None else f"#{id(release)}"
        release_ids.add(release_key)

        if _is_blank(release.get("CrDate")):
            trdate = _parse_date(release.get("TrDate"))
            missing_crdate.add(entry.product, release_key, {
                "id": release_id,
                "title": _release_title(release, release_id),
                "tfs_url": _http_url(release.get("TfsUrl")),
                "trdate": trdate.strftime("%d.%m.%Y") if trdate else "",
            })

        app_group = _normalize_name(release.get("AppTitle")) or NO_APP_TITLE_GROUP
        for requirement in _dicts(release.get("Requirements")):
            requirement_id = _normalize_id(requirement.get("Id"))
            if requirement_id is None:
                continue
            requirement_ids.add(requirement_id)
            item = {
                "id": requirement_id,
                "title": _requirement_title(requirement, requirement_id),
                "tfs_url": _http_url(requirement.get("TfsUrl")),
            }

            if _applicable_is_empty(requirement):
                missing_applicable.add(app_group, requirement_id, item)

            if _is_ru_visible(requirement.get("Visibility")):
                marketing_title = requirement.get("MarketingTitle")
                matches = _matched_terms(marketing_title, pattern)
                if matches:
                    only_ru.add(entry.product, requirement_id, {
                        **item,
                        "marketing_title": marketing_title,
                        "matched_terms": matches,
                    })

    return {
        "totals": {
            "requirements": len(requirement_ids),
            "releases": len(release_ids),
        },
        "missing_applicable": missing_applicable.export(),
        "missing_crdate": missing_crdate.export(),
        "only_ru": only_ru.export(),
    }
