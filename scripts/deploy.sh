#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [-m "commit message"] [--visual-qa-ok]

Deploys exactly the files already staged in Git:
  validate staged payload -> conditional tests/build -> commit -> push -> deploy -> health

Before running:
  git add -- <only intended source files>

Options:
  -m, --message       Commit message (default: release: v<APP_VERSION>)
  --visual-qa-ok      Required when builder.py or layout.py is staged
  -h, --help          Show this help
EOF
}

commit_message=""
visual_qa_ok=0

while (($#)); do
  case "$1" in
    -m|--message)
      [[ $# -ge 2 ]] || { echo "ERROR: missing commit message" >&2; exit 2; }
      commit_message="$2"
      shift 2
      ;;
    --visual-qa-ok)
      visual_qa_ok=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

branch="${DEPLOY_BRANCH:-main}"
remote="${DEPLOY_REMOTE:-origin}"
expected_remote_url="${DEPLOY_REMOTE_URL:-https://github.com/aalexmora/json-pptx.git}"
deploy_host="${DEPLOY_HOST:-root@192.168.1.149}"
deploy_path="${DEPLOY_PATH:-/opt/homelab/stacks/json-pptx}"
deploy_service="${DEPLOY_SERVICE:-roadmap}"
deploy_container="${DEPLOY_CONTAINER:-roadmap-pptx}"
deploy_ssh_key="${DEPLOY_SSH_KEY:-${HOME}/.ssh/mcp-gpt-saver}"
health_url="${DEPLOY_HEALTH_URL:-http://127.0.0.1:8000/api/health}"

current_branch="$(git branch --show-current)"
[[ "$current_branch" == "$branch" ]] || {
  echo "ERROR: expected branch '$branch', got '$current_branch'" >&2
  exit 1
}

remote_url="$(git remote get-url "$remote")"
[[ "$remote_url" == "$expected_remote_url" ]] || {
  echo "ERROR: unexpected remote: $remote_url" >&2
  exit 1
}

staged_files="$(git diff --cached --name-only --diff-filter=ACMRD)"
[[ -n "$staged_files" ]] || {
  echo "ERROR: nothing staged; stage only the intended release files first" >&2
  exit 1
}

blocked_files=""
while IFS= read -r file; do
  case "$file" in
    Requirements/*|data/*|frontend/dist/*|tests/fixtures/synthetic_template.pptx|*.xlsx|*.xls|*.csv|*.pem|*.key|.env|.env.*|*/.env|*/.env.*)
      blocked_files+="${file}"$'\n'
      ;;
  esac
done <<< "$staged_files"

[[ -z "$blocked_files" ]] || {
  echo "ERROR: protected/generated files are staged:" >&2
  printf '%s' "$blocked_files" >&2
  exit 1
}

unstaged_runtime_files="$({
  git diff --name-only --diff-filter=ACMRD
  git ls-files --others --exclude-standard
} | grep -E '^(app\.py|roadmap_generator/|plugins/|config/|frontend/src/|frontend/package(-lock)?\.json|Dockerfile$|docker-compose\.ya?ml$|requirements\.txt$|tests/)' \
  | grep -v '^tests/fixtures/synthetic_template\.pptx$' || true)"

[[ -z "$unstaged_runtime_files" ]] || {
  echo "ERROR: executable/test files have unstaged changes:" >&2
  printf '%s\n' "$unstaged_runtime_files" >&2
  exit 1
}

git diff --cached --check

version="$(sed -n 's/^APP_VERSION = "\([^"]*\)"/\1/p' roadmap_generator/version.py)"
[[ -n "$version" ]] || { echo "ERROR: APP_VERSION not found" >&2; exit 1; }
[[ -n "$commit_message" ]] || commit_message="release: v${version}"

backend_needed=0
frontend_needed=0
render_changed=0
version_required=0

while IFS= read -r file; do
  case "$file" in
    app.py|roadmap_generator/*.py|plugins/*.py|config/*|requirements.txt|tests/*.py|tests/**/*.py)
      [[ "$file" == "roadmap_generator/version.py" ]] || backend_needed=1
      ;;
  esac
  case "$file" in
    frontend/src/*|frontend/package.json|frontend/package-lock.json|frontend/vite.config.*)
      frontend_needed=1
      ;;
  esac
  case "$file" in
    roadmap_generator/builder.py|roadmap_generator/layout.py)
      render_changed=1
      ;;
  esac
  case "$file" in
    app.py|roadmap_generator/*.py|plugins/*.py|config/*|requirements.txt|frontend/src/*|frontend/package.json|frontend/package-lock.json|frontend/vite.config.*|Dockerfile|docker-compose.yml)
      [[ "$file" == "roadmap_generator/version.py" ]] || version_required=1
      ;;
  esac
done <<< "$staged_files"

if ((version_required)) && ! grep -Fxq 'roadmap_generator/version.py' <<< "$staged_files"; then
  echo "ERROR: stage an APP_VERSION bump in roadmap_generator/version.py" >&2
  exit 1
fi

if ((render_changed)) && ((visual_qa_ok == 0)); then
  echo "ERROR: render-sensitive change; inspect the rendered deck, then rerun with --visual-qa-ok" >&2
  exit 1
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/roadmap-deploy.XXXXXX")"
fixture="tests/fixtures/synthetic_template.pptx"
fixture_existed=0

cleanup() {
  if ((fixture_existed)); then
    cp "$work_dir/synthetic_template.pptx" "$fixture"
  else
    rm -f "$fixture"
  fi
  rm -rf "$work_dir"
}
trap cleanup EXIT

if [[ -f "$fixture" ]]; then
  cp "$fixture" "$work_dir/synthetic_template.pptx"
  fixture_existed=1
fi

if ((backend_needed)); then
  echo "[1/4] backend tests"
  .venv/bin/python -m pytest -q
fi

if ((frontend_needed)); then
  echo "[1/4] frontend checks"
  (
    cd frontend
    npm run typecheck
    npm run build -- --outDir "$work_dir/frontend-dist" --emptyOutDir
  )
fi

echo "[2/4] commit + push"
git commit -m "$commit_message"
git push "$remote" "$branch"

echo "[3/4] production deploy"
ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$deploy_ssh_key" "$deploy_host" \
  bash -s -- "$deploy_path" "$remote" "$branch" "$deploy_service" "$deploy_container" "$health_url" "$version" <<'REMOTE'
set -euo pipefail
deploy_path="$1"
remote="$2"
branch="$3"
service="$4"
container="$5"
health_url="$6"
expected_version="$7"

cd "$deploy_path"
git pull --ff-only "$remote" "$branch"
docker compose up -d --build "$service"

for _ in $(seq 1 30); do
  container_health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
  response="$(curl -fsS "$health_url" 2>/dev/null || true)"
  if [[ "$container_health" == "healthy" && "$response" == *\"version\":\"${expected_version}\"* ]]; then
    printf '%s\n' "$response"
    exit 0
  fi
  sleep 2
done

docker compose ps "$service"
echo "ERROR: deployment health/version check timed out" >&2
exit 1
REMOTE

echo "[4/4] DEPLOY_OK v${version} $(git rev-parse --short HEAD)"
