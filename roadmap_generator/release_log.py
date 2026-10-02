"""Пользовательский журнал текущей версии приложения."""
from __future__ import annotations

from roadmap_generator.version import APP_VERSION


IMPLEMENTED = (
    "Отчёты разделены на вкладки 2026 и 2027 с расчётом по TrDate.",
    "Проблемные релизы открываются по TfsUrl, а после загрузки CSV показываются полностью заполненные продукты.",
    "Заголовок и маркер квартала не повторяются в подколонках одного квартала.",
    "Наследование Tier удалено: каждый Tier показывает собственный полный набор фич.",
    "Журнал релиза открывается по клику на версию приложения.",
)

REMAINING = (
    "Collector-плагины для prefix-based секций остаются в Phase 2 и требуют отдельного явного запуска.",
    "Вместимость колонки пока определяется фиксированным MAX_BULLETS_PER_COLUMN, без расчёта по высоте текста.",
)


def current_release_log() -> dict[str, object]:
    return {
        "version": APP_VERSION,
        "implemented": list(IMPLEMENTED),
        "remaining": list(REMAINING),
    }
