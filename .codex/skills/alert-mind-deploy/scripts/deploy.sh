#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOCAL_ENV_FILE="${ALERT_MIND_DEPLOY_ENV:-${SKILL_DIR}/deploy.local.env}"
DEPLOY_HOST_FROM_ENV="${ALERT_MIND_DEPLOY_HOST:-}"

if [[ -f "${LOCAL_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${LOCAL_ENV_FILE}"
fi
[[ -n "${DEPLOY_HOST_FROM_ENV}" ]] && ALERT_MIND_DEPLOY_HOST="${DEPLOY_HOST_FROM_ENV}"

: "${ALERT_MIND_DEPLOY_HOST:?Set ALERT_MIND_DEPLOY_HOST in the shell or a private local env file.}"

DEPLOY_USER="${ALERT_MIND_DEPLOY_USER:-root}"
DEPLOY_PORT="${ALERT_MIND_DEPLOY_PORT:-22}"
DEPLOY_DIR="${ALERT_MIND_DEPLOY_DIR:-/opt/alert_mind}"
HEALTH_URL="${ALERT_MIND_HEALTH_URL:-http://127.0.0.1:9000/health}"
SSH_TARGET="${DEPLOY_USER}@${ALERT_MIND_DEPLOY_HOST}"
SSH_ARGS=(-p "${DEPLOY_PORT}")
if [[ -n "${ALERT_MIND_SSH_KEY:-}" ]]; then
  SSH_ARGS+=(-i "${ALERT_MIND_SSH_KEY}")
fi

REMOTE_DIR_Q="$(printf '%q' "${DEPLOY_DIR}")"
HEALTH_URL_Q="$(printf '%q' "${HEALTH_URL}")"

echo "Deploying AlertMind origin/main on ${SSH_TARGET}:${DEPLOY_DIR}"

ssh "${SSH_ARGS[@]}" "${SSH_TARGET}" "DEPLOY_DIR=${REMOTE_DIR_Q} HEALTH_URL=${HEALTH_URL_Q} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${DEPLOY_DIR}"

test -f .env

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Remote repository has uncommitted tracked changes. Refusing to deploy over them." >&2
  exit 20
fi

git fetch origin main:refs/remotes/origin/main
git switch main
git merge --ff-only origin/main

deployed_commit="$(git rev-parse --short HEAD)"
echo "Deploying commit: ${deployed_commit}"

if docker ps >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker ps >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo "Current user cannot access Docker. Add it to the docker group or configure passwordless sudo." >&2
  exit 30
fi

"${DOCKER[@]}" compose \
  -f vector-database.yml \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --build

"${DOCKER[@]}" compose \
  -f vector-database.yml \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  ps

curl -fsS "${HEALTH_URL}"
REMOTE_SCRIPT

echo
echo "Deployment finished. Health URL: ${HEALTH_URL}"
