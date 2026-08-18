# =============================================================================
# Stage 1: сборка фронтенда (React + Vite + TypeScript)
# =============================================================================
FROM node:20-alpine AS frontend

WORKDIR /build

# Сначала только манифесты — кэшируем npm ci при неизменных зависимостях
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# =============================================================================
# Stage 2: рантайм (FastAPI, раздаёт API + собранный фронтенд)
# =============================================================================
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Рантайм-зависимости (без dev: pytest/httpx/sqlmodel не попадают в образ)
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Код приложения
COPY app.py ./
COPY roadmap_generator/ ./roadmap_generator/
COPY plugins/ ./plugins/
COPY config/ ./config/

# Собранный фронтенд из Stage 1
COPY --from=frontend /build/dist ./frontend/dist

# Непривилегированный пользователь; директории состояния пишутся на рантайме
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data /app/templates_library \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

# Один процесс: состояние профиля/шаблонов хранится in-memory + в файлах,
# поэтому несколько воркеров не нужны (и приведут к рассинхрону).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
