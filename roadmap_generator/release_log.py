"""Пользовательский журнал текущей версии приложения."""
from __future__ import annotations

from roadmap_generator.version import APP_VERSION


IMPLEMENTED = (
    "Исправлено предупреждение PowerPoint о повреждённом содержимом скачанной презентации.",
    "Все сгенерированные слайды используют зарегистрированный layout и master загруженного roadmap-шаблона.",
    "Статичные слайды сохраняют собственные layout, master, theme и исходное содержимое PPTX.",
    "Плейсхолдеры roadmap_year и roadmap_version заполняются текущей системной датой.",
    "Reports now flag configured brand terms in English feature titles.",
    "AppTitle aliases with the same custom label are grouped together.",
    "??????? ???????? ??????????? ?? ?????????? ???? ??????.",
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
