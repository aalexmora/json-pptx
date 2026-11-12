#!/usr/bin/env bash
# Run in Terminal on the main Mac, outside the VM.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ACTION="${1:-start}"
fail() { printf '%s\n' "$*" >&2; exit 1; }
case "$ACTION" in verify|check|start|status|stop|logs) ;; *) fail 'Команды: start, check, verify, status, stop, logs' ;; esac

[[ -f "$ROOT/SHA256SUMS" ]] || fail 'Нужен полный Mac-пакет с SHA256SUMS.'
for file in scripts/run-mac.sh docker-compose.mac.yml SOURCE_REVISION VERSION; do
  [[ -f "$ROOT/$file" && ! -L "$ROOT/$file" ]] || fail "Отсутствует файл пакета: $file"
  digest="$(awk -v name="$file" '$2 == name {print $1}' "$ROOT/SHA256SUMS")"
  [[ "$digest" =~ ^[a-f0-9]{64}$ ]] || fail "Нет единственной SHA-256 для $file"
done
(cd -- "$ROOT" && shasum -a 256 -c SHA256SUMS) || fail 'Контрольные суммы не совпали. Повторно скачайте пакет.'
[[ "$ACTION" != verify ]] || exit 0
[[ "$(uname -s)" == Darwin ]] || fail 'Запустите эту команду в Terminal основного Mac.'

DOCKER_BIN="${JSON_PPTX_DOCKER:-}"
if [[ -z "$DOCKER_BIN" ]]; then DOCKER_BIN="$(command -v docker || true)"; fi
if [[ -z "$DOCKER_BIN" ]]; then
  for candidate in /Applications/Docker.app/Contents/Resources/bin/docker "$HOME/Applications/Docker.app/Contents/Resources/bin/docker"; do
    if [[ -x "$candidate" ]]; then DOCKER_BIN="$candidate"; break; fi
  done
fi
[[ -n "$DOCKER_BIN" && -x "$DOCKER_BIN" ]] || fail 'Откройте Docker Desktop на основном Mac и завершите его настройку.'
for directory in "$(dirname -- "$DOCKER_BIN")" /Applications/Docker.app/Contents/Resources/bin "$HOME/Applications/Docker.app/Contents/Resources/bin"; do
  if [[ -d "$directory" ]]; then export PATH="$directory:$PATH"; fi
done
endpoint="$("$DOCKER_BIN" context inspect desktop-linux --format '{{.Endpoints.docker.Host}}')" || fail 'Локальный context desktop-linux недоступен. Завершите настройку Docker Desktop.'
case "$endpoint" in unix:///*) ;; *) fail "Нужен локальный Unix socket Docker Desktop: $endpoint" ;; esac
docker_local() { "$DOCKER_BIN" --context desktop-linux "$@"; }
engine="$(docker_local info --format '{{.OSType}}/{{.Architecture}}')" || fail 'Движок Docker Desktop недоступен. Откройте Docker Desktop и повторите команду.'
case "$engine" in linux/arm64|linux/aarch64|linux/amd64|linux/x86_64) ;; *) fail "Нужен Linux-движок Docker Desktop: $engine" ;; esac
docker_local compose version --short || fail 'Плагин Docker Compose недоступен.'
if [[ "$ACTION" == check ]]; then printf 'Docker Desktop готов: %s\n' "$engine"; exit 0; fi

revision="$(cat "$ROOT/SOURCE_REVISION")"
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || fail 'Некорректная Git revision пакета.'
export JSON_PPTX_REVISION="${revision:0:12}"
export JSON_PPTX_PORT="${JSON_PPTX_PORT:-8000}"
[[ "$JSON_PPTX_PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$JSON_PPTX_PORT >= 1 && 10#$JSON_PPTX_PORT <= 65535)) || fail 'Порт должен быть от 1 до 65535.'
project="${JSON_PPTX_PROJECT:-json-pptx-mac}"
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail 'Некорректное имя Compose-проекта.'
compose() { docker_local compose --project-name "$project" --project-directory "$ROOT" -f "$ROOT/docker-compose.mac.yml" "$@"; }
case "$ACTION" in
  status) compose ps; exit 0 ;;
  stop) compose stop; exit 0 ;;
  logs) compose logs --tail=100 -f roadmap; exit 0 ;;
esac
if ! compose up -d --build --wait --wait-timeout 120; then
  compose logs --tail=80 roadmap >&2 || true
  fail 'Запуск не завершён. Исправьте ошибку выше и повторите команду из того же пакета.'
fi
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:$JSON_PPTX_PORT/api/health" || fail 'HTTP-проверка приложения не прошла.'
printf '\nПриложение готово: http://127.0.0.1:%s/\nВерсия: %s\nGit revision: %s\n' "$JSON_PPTX_PORT" "$(cat "$ROOT/VERSION")" "$revision"
