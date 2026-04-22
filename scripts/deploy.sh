#!/usr/bin/env bash
#
# deploy.sh — production deploy to a single VPS.
#
# Assumptions:
#   - SSH access to $DEPLOY_HOST as $DEPLOY_USER with passwordless sudo
#   - Remote has Docker + docker compose v2 installed
#   - $DEPLOY_HOST runs nginx; certs managed by Let's Encrypt / certbot
#
# Usage:
#   DEPLOY_HOST=vps.example.com DEPLOY_USER=deploy ./scripts/deploy.sh
#
# The script:
#   1. Syncs the working copy (respecting .gitignore) to the remote
#   2. Rebuilds docker images in place
#   3. Applies the latest compose state
#   4. Runs the smoke test; if it fails, logs the failure and exits non-zero

set -euo pipefail

: "${DEPLOY_HOST:?DEPLOY_HOST is required}"
: "${DEPLOY_USER:?DEPLOY_USER is required}"

REMOTE_PATH=${REMOTE_PATH:-/opt/swarmscout}

echo "[1/4] syncing ${PWD} -> ${DEPLOY_USER}@${DEPLOY_HOST}:${REMOTE_PATH}"
rsync -az --delete \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='contracts/out/' \
  --exclude='contracts/cache/' \
  --exclude='web/.next/' \
  --exclude='web/coverage/' \
  --exclude='htmlcov/' \
  -e ssh \
  ./ "${DEPLOY_USER}@${DEPLOY_HOST}:${REMOTE_PATH}/"

echo "[2/4] building docker images on remote"
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "cd ${REMOTE_PATH} && docker compose build"

echo "[3/4] starting services"
ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "cd ${REMOTE_PATH} && docker compose up -d"

echo "[4/4] running smoke test"
if ! ssh "${DEPLOY_USER}@${DEPLOY_HOST}" "cd ${REMOTE_PATH} && bash scripts/smoke_test.sh"; then
  echo "smoke test failed"
  exit 1
fi

echo "deploy complete"
