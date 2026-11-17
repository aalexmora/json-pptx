#!/usr/bin/env bash
# Uses only disposable Compose resources; never touches the deployment project.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for tool in docker curl; do
  command -v "$tool" >/dev/null || { echo "Required tool missing: $tool" >&2; exit 1; }
done
WORK="$(mktemp -d "${TMPDIR:-/tmp}/json-pptx-smoke.XXXXXX")"
PROJECT="json-pptx-smoke-$(date +%s)-$$"
: > "$WORK/empty.env"
export JSON_PPTX_BIND=127.0.0.1 JSON_PPTX_PORT=0
export JSON_PPTX_CONTAINER_NAME="$PROJECT-roadmap"
export JSON_PPTX_REVISION="${JSON_PPTX_REVISION:-$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo local)}"
COMPOSE=(docker compose --project-name "$PROJECT" --project-directory "$ROOT"
  --env-file "$WORK/empty.env" -f "$ROOT/docker-compose.yml")

cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 )); then "${COMPOSE[@]}" logs --no-color --tail=100 roadmap || true; fi
  "${COMPOSE[@]}" down --volumes --remove-orphans || status=1
  rm -f -- "$WORK/empty.env" "$WORK/index.html" "$WORK/published-health.json"
  rmdir -- "$WORK"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

VERSION="$(sed -n 's/^APP_VERSION = "\([^"]*\)"/\1/p' "$ROOT/roadmap_generator/version.py")"
test -n "$VERSION"
"${COMPOSE[@]}" up --build --detach --wait --wait-timeout 120

check() {
  local mode=$1 address
  address="$("${COMPOSE[@]}" port roadmap 8000)"
  curl --fail --silent --show-error --max-time 30 "http://$address/" > "$WORK/index.html"
  grep -qi '<html' "$WORK/index.html"
  curl --fail --silent --show-error --max-time 30 "http://$address/api/health" > "$WORK/published-health.json"
  "${COMPOSE[@]}" exec -T roadmap mkdir -p /tmp/json-pptx-smoke
  "${COMPOSE[@]}" exec -T roadmap sh -c 'cat > /tmp/json-pptx-smoke/check.py' < "$ROOT/scripts/smoke-container.py"
  "${COMPOSE[@]}" exec -T roadmap sh -c 'cat > /tmp/json-pptx-smoke/published-health.json' < "$WORK/published-health.json"
  for fixture in pagination_5_quarters.json en_with_content.json; do
    "${COMPOSE[@]}" exec -T roadmap sh -c 'cat > "$1"' sh "/tmp/json-pptx-smoke/$fixture" < "$ROOT/tests/fixtures/$fixture"
  done
  "${COMPOSE[@]}" exec -T roadmap python /tmp/json-pptx-smoke/check.py "$mode" "$VERSION" "$PROJECT"
}

check fresh
"${COMPOSE[@]}" up --detach --force-recreate --no-build --wait --wait-timeout 120
check persist
echo "Container smoke passed: frontend, RU/EN PPTX, validation, persistent state ($VERSION)."
