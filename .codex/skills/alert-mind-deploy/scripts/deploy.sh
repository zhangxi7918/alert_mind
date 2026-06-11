#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${SKILL_DIR}/../../.." && pwd)"
LOCAL_ENV_FILE="${ALERT_MIND_DEPLOY_ENV:-${SKILL_DIR}/deploy.local.env}"

if [[ -f "${LOCAL_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${LOCAL_ENV_FILE}"
fi

require_local_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing local command: $1" >&2
    exit 10
  fi
}

require_local_command ssh
require_local_command rsync

if [[ -z "${ALERT_MIND_DEPLOY_HOST:-}" ]]; then
  cat >&2 <<'EOF'
Missing ALERT_MIND_DEPLOY_HOST.

Create .codex/skills/alert-mind-deploy/deploy.local.env, for example:
ALERT_MIND_DEPLOY_HOST=your.server.ip
ALERT_MIND_DEPLOY_USER=root
ALERT_MIND_DEPLOY_PORT=22
ALERT_MIND_DEPLOY_DIR=/opt/alert_mind
EOF
  exit 11
fi

DEPLOY_USER="${ALERT_MIND_DEPLOY_USER:-root}"
DEPLOY_PORT="${ALERT_MIND_DEPLOY_PORT:-22}"
DEPLOY_DIR="${ALERT_MIND_DEPLOY_DIR:-/opt/alert_mind}"
HEALTH_URL="${ALERT_MIND_HEALTH_URL:-http://127.0.0.1:9000/health}"
COMPOSE_FILES="${ALERT_MIND_COMPOSE_FILES:-vector-database.yml docker-compose.yml docker-compose.prod.yml}"

SSH_TARGET="${DEPLOY_USER}@${ALERT_MIND_DEPLOY_HOST}"
SSH_ARGS=(-p "${DEPLOY_PORT}")
if [[ -n "${ALERT_MIND_SSH_KEY:-}" ]]; then
  SSH_ARGS+=(-i "${ALERT_MIND_SSH_KEY}")
fi

read -r -a COMPOSE_FILE_ARRAY <<< "${COMPOSE_FILES}"
for compose_file in "${COMPOSE_FILE_ARRAY[@]}"; do
  if [[ ! -f "${PROJECT_ROOT}/${compose_file}" ]]; then
    echo "Missing local Compose file: ${compose_file}" >&2
    exit 12
  fi
done

REMOTE_DIR_Q="$(printf '%q' "${DEPLOY_DIR}")"
HEALTH_URL_Q="$(printf '%q' "${HEALTH_URL}")"
COMPOSE_FILES_Q="$(printf '%q' "${COMPOSE_FILES}")"

echo "Deploying AlertMind to ${SSH_TARGET}:${DEPLOY_DIR}"

ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "mkdir -p ${REMOTE_DIR_Q}"

RSYNC_SSH="ssh -p ${DEPLOY_PORT}"
if [[ -n "${ALERT_MIND_SSH_KEY:-}" ]]; then
  RSYNC_SSH+=" -i ${ALERT_MIND_SSH_KEY}"
fi

rsync -az \
  -e "${RSYNC_SSH}" \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.DS_Store' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.pytest_cache' \
  --exclude '.mypy_cache' \
  --exclude '.ruff_cache' \
  --exclude 'logs/*' \
  --exclude 'volumes/*' \
  --exclude '.codex/skills/alert-mind-deploy/deploy.local.env' \
  "${PROJECT_ROOT}/" \
  "${SSH_TARGET}:${DEPLOY_DIR}/"

ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "DEPLOY_DIR=${REMOTE_DIR_Q} HEALTH_URL=${HEALTH_URL_Q} COMPOSE_FILES=${COMPOSE_FILES_Q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
cd "${DEPLOY_DIR}"
mkdir -p uploads logs volumes

if [[ ! -f .env ]]; then
  echo "Remote .env is missing at ${DEPLOY_DIR}/.env" >&2
  echo "Create it from .env.example, fill production secrets, then rerun deployment." >&2
  exit 20
fi

read -r -a compose_files <<< "${COMPOSE_FILES}"
compose_args=()
for compose_file in "${compose_files[@]}"; do
  compose_args+=(-f "${compose_file}")
done

if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "Docker Compose is not installed on the remote server." >&2
  exit 21
fi

"${compose_cmd[@]}" "${compose_args[@]}" up -d --build
"${compose_cmd[@]}" "${compose_args[@]}" ps

if command -v curl >/dev/null 2>&1; then
  curl -fsS "${HEALTH_URL}"
else
  python - "${HEALTH_URL}" <<'PY'
import sys
import urllib.request
print(urllib.request.urlopen(sys.argv[1], timeout=10).read().decode())
PY
fi
REMOTE_SCRIPT

echo
echo "Deployment finished. Health URL: ${HEALTH_URL}"
