"""Плагин-фильтр: оставляет только требования с `Kbr == "Yes"`.

По умолчанию включён. `Kbr` отсутствует (None) → не проходит фильтр.
"""
from __future__ import annotations

from plugins._base import SlideBuildContext


class KbrFilter:
    id = "kbr_filter"
    label = "Фильтр KBR (только Yes)"
    kind = "filter"
    scope = "tier"

    def default_settings(self) -> dict:
        return {"enabled": True, "keep": "Yes"}

    def apply(self, context: SlideBuildContext, settings: dict) -> SlideBuildContext:
        if not settings.get("enabled", True):
            return context
        keep = settings.get("keep", "Yes")
        context.bullets = [b for b in context.bullets if b.kbr == keep]
        return context
