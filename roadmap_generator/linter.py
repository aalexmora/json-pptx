"""Dev-линтер: подсвечивает ошибки в данных перед генерацией.

Встроенное правило: кириллица в EN-тексте (русские названия, оставшиеся в
EN-презентации). Пользовательские regex'ы — из глобального профиля (этап 8 —
из админки). Результат — список issue-словарей для показа в превью/UI.
"""
from __future__ import annotations

import re
from typing import Dict, List

from roadmap_generator.schema import RoadmapModel

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

_custom_rules: List[Dict[str, str]] = []  # [{"pattern": str, "description": str}]


def save_custom_rules(rules: List[Dict[str, str]]) -> None:
    _custom_rules[:] = list(rules)


def get_custom_rules() -> List[Dict[str, str]]:
    return list(_custom_rules)


def lint_model(model: RoadmapModel) -> List[dict]:
    """Возвращает список issue: {product, stream, tier, requirement_id, text, message}."""
    issues: List[dict] = []
    for product in model.products:
        for stream in product.streams:
            for tier in stream.tiers:
                for release in tier.releases:
                    for req in release.requirements:
                        text = req.marketing_title_en if model.language == "en" else req.marketing_title

                        if model.language == "en" and CYRILLIC_RE.search(text):
                            issues.append(_issue(
                                product.name, stream.name, tier.name, req.id, text,
                                "кириллица в EN-тексте",
                            ))

                        for rule in _custom_rules:
                            try:
                                if re.search(rule["pattern"], text):
                                    issues.append(_issue(
                                        product.name, stream.name, tier.name, req.id, text,
                                        rule.get("description") or rule["pattern"],
                                    ))
                            except re.error:
                                continue
    return issues


def _issue(product: str, stream: str, tier: str, requirement_id: int, text: str, message: str) -> dict:
    return {
        "product": product,
        "stream": stream,
        "tier": tier,
        "requirement_id": requirement_id,
        "text": text,
        "message": message,
    }


def _reset_state() -> None:
    """Сброс in-memory хранилища regex-правил (для тестов)."""
    _custom_rules.clear()
