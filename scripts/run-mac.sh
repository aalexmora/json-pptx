#!/usr/bin/env bash
# Run in Terminal on the main Mac, outside the VM.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ACTION="${1:-start}"
fail() { printf '%s\n' "$*" >&2; exit 1; }
case "$ACTION" in verify|check|start|status|stop|logs|backup) ;; *) fail 'Команды: start, check, verify, status, stop, logs, backup' ;; esac

[[ -f "$ROOT/SHA256SUMS" ]] || fail 'Нужен полный Mac-пакет с SHA256SUMS.'
for file in image.tar.gz image.txt scripts/run-mac.sh docker-compose.mac.yml SOURCE_REVISION VERSION; do
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
case "$engine" in linux/arm64|linux/aarch64) ;; *) fail "Для пакета нужен Linux ARM64 движок Docker Desktop: $engine" ;; esac
docker_local compose version --short || fail 'Плагин Docker Compose недоступен.'
if [[ "$ACTION" == check ]]; then printf 'Docker Desktop готов: %s\n' "$engine"; exit 0; fi

revision="$(cat "$ROOT/SOURCE_REVISION")"
[[ "$revision" =~ ^[a-f0-9]{40}$ ]] || fail 'Некорректная Git revision пакета.'
export JSON_PPTX_REVISION="$revision"
export JSON_PPTX_IMAGE="$(cat "$ROOT/image.txt")"
[[ "$JSON_PPTX_IMAGE" =~ ^json-pptx:[a-zA-Z0-9._-]+$ ]] || fail 'Некорректное имя образа в пакете.'
export JSON_PPTX_PORT="${JSON_PPTX_PORT:-8000}"
[[ "$JSON_PPTX_PORT" =~ ^[0-9]{1,5}$ ]] && ((10#$JSON_PPTX_PORT >= 1 && 10#$JSON_PPTX_PORT <= 65535)) || fail 'Порт должен быть от 1 до 65535.'
project="${JSON_PPTX_PROJECT:-json-pptx-mac}"
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail 'Некорректное имя Compose-проекта.'
compose() { docker_local compose --project-name "$project" --project-directory "$ROOT" -f "$ROOT/docker-compose.mac.yml" "$@"; }

backup_state() (
  set -euo pipefail
  container="$1"
  mode="$2"
  old_image="$(docker_local container inspect --format '{{.Image}}' "$container")"
  was_running="$(docker_local container inspect --format '{{.State.Running}}' "$container")"
  for destination in /app/data /app/templates_library; do
    mount="$(docker_local container inspect --format "{{range .Mounts}}{{if eq .Destination \"$destination\"}}{{.Type}}|{{.Name}}|{{.RW}}{{end}}{{end}}" "$container")"
    if [[ "$destination" == /app/data ]]; then expected="volume|${project}_roadmap-data|true";
    else expected="volume|${project}_roadmap-templates|true"; fi
    [[ "$mount" == "$expected" ]] || fail "Существующий контейнер имеет другое хранилище: $destination"
  done
  resume="$was_running"
  trap 'backup_rc=$?; if [[ "$resume" == true ]]; then compose start >&2 || true; fi; exit "$backup_rc"' EXIT
  backup_root="${JSON_PPTX_BACKUP_DIR:-$HOME/Library/Application Support/json-pptx/backups}"
  mkdir -p "$backup_root"
  backup_root="$(cd -- "$backup_root" && pwd -P)"
  snapshot="$(mktemp -d "$backup_root/$project-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
  compose stop >&2
  docker_local run --rm --network none --read-only --user 0 --entrypoint tar \
    --mount "type=volume,source=${project}_roadmap-data,target=/state/data,readonly" \
    --mount "type=volume,source=${project}_roadmap-templates,target=/state/templates,readonly" \
    --mount "type=bind,source=$snapshot,target=/backup" \
    "$old_image" -czf /backup/state.tar.gz -C /state data templates >&2
  docker_local image save "$old_image" | gzip > "$snapshot/image.tar.gz"
  printf '%s\n' "$old_image" > "$snapshot/image-id.txt"
  printf '%s\n' "$project" > "$snapshot/project.txt"
  gzip -t "$snapshot/state.tar.gz" "$snapshot/image.tar.gz"
  (cd -- "$snapshot" && shasum -a 256 state.tar.gz image.tar.gz image-id.txt project.txt > SHA256SUMS && shasum -a 256 -c SHA256SUMS) >&2
  [[ "$mode" != upgrade ]] || resume=false
  printf '%s\n' "$snapshot"
)

case "$ACTION" in
  status) compose ps; exit 0 ;;
  stop) compose stop; exit 0 ;;
  logs) compose logs --tail=100 -f roadmap; exit 0 ;;
  backup)
    container="$(compose ps -aq roadmap)"
    [[ -n "$container" ]] || fail 'Контейнер этого проекта ещё не создан.'
    backup_state "$container" backup; exit 0 ;;
esac
docker_local load --input "$ROOT/image.tar.gz"
actual="$(docker_local image inspect --format '{{.Os}}/{{.Architecture}}|{{index .Config.Labels "org.opencontainers.image.revision"}}|{{index .Config.Labels "org.opencontainers.image.version"}}' "$JSON_PPTX_IMAGE")"
[[ "$actual" == "linux/arm64|$revision|$(cat "$ROOT/VERSION")" ]] || fail 'Архитектура, версия или Git revision образа не совпали с пакетом.'
container="$(compose ps -aq roadmap)"
if [[ -n "$container" ]]; then
  old_image="$(docker_local container inspect --format '{{.Image}}' "$container")"
  new_image="$(docker_local image inspect --format '{{.Id}}' "$JSON_PPTX_IMAGE")"
  if [[ "$old_image" != "$new_image" ]]; then
    snapshot="$(backup_state "$container" upgrade)"
    printf 'Резервная копия перед обновлением: %s\n' "$snapshot"
  fi
fi
if ! compose up -d --pull never --no-build --wait --wait-timeout 120; then
  compose logs --tail=80 roadmap >&2 || true
  fail "Запуск не завершён. Повторите команду из того же пакета. Резервная копия: ${snapshot:-при первом запуске не требуется}"
fi
curl --fail --silent --show-error --max-time 10 "http://127.0.0.1:$JSON_PPTX_PORT/api/health" || fail 'HTTP-проверка приложения не прошла.'
printf '\nПриложение готово: http://127.0.0.1:%s/\nВерсия: %s\nGit revision: %s\n' "$JSON_PPTX_PORT" "$(cat "$ROOT/VERSION")" "$revision"
