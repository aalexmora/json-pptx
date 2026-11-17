"""Пользовательский журнал текущей версии приложения."""
from __future__ import annotations

from roadmap_generator.version import APP_VERSION


IMPLEMENTED = (
    "Подготовлен запуск на Linux-сервере через Docker Compose: настройка адреса и порта, постоянные данные и проверка контейнера.",
    "Удалены загрузка CSV, сопоставление публичных фич и CSV-зависимый список заполненных продуктов; отчёты работают по текущему JSON.",
    "Если маркетинговое название RU или EN отсутствует, используется Title; ошибка показана в контроле качества и не блокирует генерацию.",
    "Исправлено предупреждение PowerPoint о повреждённом содержимом скачанной презентации.",
    "Все сгенерированные слайды используют зарегистрированный layout и master загруженного roadmap-шаблона.",
    "Статичные слайды сохраняют собственные layout, master, theme и исходное содержимое PPTX.",
    "Плейсхолдеры roadmap_year и roadmap_version заполняются текущей системной датой.",
    "Reports now flag configured brand terms in English feature titles.",
    "AppTitle aliases with the same custom label are grouped together.",
    "Next roadmap features are grouped under Expert View and Pro View subheadings when ConsoleType is set.",
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
