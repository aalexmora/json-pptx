"""Пользовательский журнал текущей версии приложения."""
from __future__ import annotations

from roadmap_generator.version import APP_VERSION


IMPLEMENTED = (
    "В админке можно скачать ранее загруженный PPTX статичного слайда.",
    "Сгенерированные слайды сохраняют layout загруженного roadmap-шаблона.",
    "Статичные слайды сохраняют layout своего исходного PPTX.",
    "Плейсхолдеры roadmap_year и roadmap_version заполняются текущей системной датой.",
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
