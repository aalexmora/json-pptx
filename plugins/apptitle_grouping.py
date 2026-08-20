"""Плагин-группировка: разбивает bullet'ы каждой колонки на подгруппы по AppTitle.

Порядок групп и переименование заголовков применяет движок (`build_slide_plan`)
через `ordering.resolve_apptitle_order` и `labels.get_apptitle_label` — плагин
делает только механическую группировку по значению AppTitle.

Группа = набор **идущих подряд** Feature с одинаковым AppTitle (TOR v2 §2);
неконсекутивные вхождения одного AppTitle считаются отдельными группами.
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
            groups = []
            for bullet in column.bullets:
                if groups and groups[-1].app_title == bullet.app_title:
                    groups[-1].bullets.append(bullet)
                else:
                    groups.append(Group(app_title=bullet.app_title, bullets=[bullet]))
            column.groups = groups
            column.grouped = True
        return context
