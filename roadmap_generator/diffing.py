"""Diff и matching между старой и новой загрузкой roadmap (ТЗ v4 §8).

- `match_previous_project` сопоставляет `(Product, Stream, Tier)` по имени.
- `compute_diff` сравнивает по `Id` на уровне Release и Requirement.
Модуль не зависит от pptx/FastAPI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List

from roadmap_generator.ordering import SEPARATOR
from roadmap_generator.schema import RoadmapModel, _normalize_name, is_service_product


@dataclass
class MatchResult:
    matched_tier_paths: List[str] = field(default_factory=list)
    new_tier_paths: List[str] = field(default_factory=list)
    removed_tier_paths: List[str] = field(default_factory=list)


@dataclass
class DiffResult:
    new_release_ids: List[int] = field(default_factory=list)
    changed_release_ids: List[int] = field(default_factory=list)
    removed_release_ids: List[int] = field(default_factory=list)
    new_requirement_ids: List[int] = field(default_factory=list)
    changed_requirement_ids: List[int] = field(default_factory=list)
    removed_requirement_ids: List[int] = field(default_factory=list)


def _tier_paths_from_model(model: RoadmapModel) -> List[str]:
    return [
        f"{p.name}{SEPARATOR}{s.name}{SEPARATOR}{t.name}"
        for p in model.products
        for s in p.streams
        for t in s.tiers
    ]


def _tier_paths_from_raw(raw) -> List[str]:
    paths: List[str] = []
    for product in raw:
        if is_service_product(product):
            continue
        pname = _normalize_name(product.get("Product"))
        for stream in product.get("Streams", []):
            sname = _normalize_name(stream.get("Stream"))
            for tier in stream.get("Tiers", []):
                tname = _normalize_name(tier.get("Tier"))
                paths.append(f"{pname}{SEPARATOR}{sname}{SEPARATOR}{tname}")
    return paths


def match_previous_project(old_model: RoadmapModel, new_raw: list) -> MatchResult:
    """Сопоставляет (Product, Stream, Tier) между старой моделью и новой выгрузкой по имени."""
    old = set(_tier_paths_from_model(old_model))
    new = set(_tier_paths_from_raw(new_raw))
    return MatchResult(
        matched_tier_paths=sorted(old & new),
        new_tier_paths=sorted(new - old),
        removed_tier_paths=sorted(old - new),
    )


def _release_signature(release) -> tuple:
    return (release.app_title, release.quarter)


def _requirement_signature(req) -> tuple:
    return (req.title, req.kbr, req.marketing_title, req.marketing_title_en, req.is_subject_to_change)


def _all_releases(model: RoadmapModel) -> dict:
    return {
        r.id: r
        for p in model.products
        for s in p.streams
        for t in s.tiers
        for r in t.releases
    }


def _all_requirements(model: RoadmapModel) -> dict:
    return {q.id: q for r in _all_releases(model).values() for q in r.requirements}


def compute_diff(old_model: RoadmapModel, new_model: RoadmapModel) -> DiffResult:
    """Возвращает new/changed/removed на уровне Release.Id и Requirement.Id."""
    old_releases = _all_releases(old_model)
    new_releases = _all_releases(new_model)
    old_reqs = _all_requirements(old_model)
    new_reqs = _all_requirements(new_model)

    return DiffResult(
        new_release_ids=sorted(set(new_releases) - set(old_releases)),
        removed_release_ids=sorted(set(old_releases) - set(new_releases)),
        changed_release_ids=sorted(
            rid
            for rid in set(old_releases) & set(new_releases)
            if _release_signature(old_releases[rid]) != _release_signature(new_releases[rid])
        ),
        new_requirement_ids=sorted(set(new_reqs) - set(old_reqs)),
        removed_requirement_ids=sorted(set(old_reqs) - set(new_reqs)),
        changed_requirement_ids=sorted(
            qid
            for qid in set(old_reqs) & set(new_reqs)
            if _requirement_signature(old_reqs[qid]) != _requirement_signature(new_reqs[qid])
        ),
    )


def build_diff_details(
    old_model: RoadmapModel,
    new_model: RoadmapModel,
    diff: DiffResult,
) -> dict[str, list[dict[str, Any]]]:
    """Человекочитаемые записи diff с путём и значениями до/после."""
    old_releases = _release_details(old_model)
    new_releases = _release_details(new_model)
    old_requirements = _requirement_details(old_model)
    new_requirements = _requirement_details(new_model)
    return {
        "new_releases": [new_releases[item_id] for item_id in diff.new_release_ids],
        "changed_releases": [
            _changed_detail(old_releases[item_id], new_releases[item_id])
            for item_id in diff.changed_release_ids
        ],
        "removed_releases": [old_releases[item_id] for item_id in diff.removed_release_ids],
        "new_requirements": [new_requirements[item_id] for item_id in diff.new_requirement_ids],
        "changed_requirements": [
            _changed_detail(old_requirements[item_id], new_requirements[item_id])
            for item_id in diff.changed_requirement_ids
        ],
        "removed_requirements": [old_requirements[item_id] for item_id in diff.removed_requirement_ids],
    }


def _release_details(model: RoadmapModel) -> dict[int, dict[str, Any]]:
    return {
        release.id: {
            "id": release.id,
            "path": f"{product.name}{SEPARATOR}{stream.name}{SEPARATOR}{tier.name}",
            "title": release.title or release.app_title,
            "quarter": release.quarter,
        }
        for product in model.products
        for stream in product.streams
        for tier in stream.tiers
        for release in tier.releases
    }


def _requirement_details(model: RoadmapModel) -> dict[int, dict[str, Any]]:
    return {
        requirement.id: {
            "id": requirement.id,
            "path": f"{product.name}{SEPARATOR}{stream.name}{SEPARATOR}{tier.name}",
            "text": (
                requirement.marketing_title_en
                if model.language == "en" and requirement.marketing_title_en
                else requirement.marketing_title
            ),
            "kbr": requirement.kbr,
        }
        for product in model.products
        for stream in product.streams
        for tier in stream.tiers
        for release in tier.releases
        for requirement in release.requirements
    }


def _changed_detail(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed_fields = {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in sorted((set(before) | set(after)) - {"id", "path"})
        if before.get(key) != after.get(key)
    }
    return {**after, "before_path": before["path"], "changes": changed_fields}
