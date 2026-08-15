"""Плагин-группировка: разбивает bullet'ы каждой колонки на подгруппы по AppTitle.

Порядок групп и переименование заголовков применяет движок (`build_slide_plan`)
через `ordering.resolve_apptitle_order` и `labels.get_apptitle_label` — плагин
делает только механическую группировку по значению AppTitle.
"""
from __future__ import annotations

from plugins._base import Group, SlideBuildContext


class AppTitleGrouping:
    id = "apptitle_grouping"
    label = "Группировка по AppTitle"
    kind = "grouping"
    scope = "tier"

    def default_settings(self) -> dict:
        return {"enabled": False}

    def apply(self, context: SlideBuildContext, settings: dict) -> SlideBuildContext:
        if not settings.get("enabled", False):
            return context
        for column in context.columns:
            buckets: dict = {}
            order: list = []
            for bullet in column.bullets:
                if bullet.app_title not in buckets:
                    buckets[bullet.app_title] = []
                    order.append(bullet.app_title)
                buckets[bullet.app_title].append(bullet)
            column.groups = [Group(app_title=title, bullets=buckets[title]) for title in order]
            column.grouped = True
        return context
