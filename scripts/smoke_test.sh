#!/usr/bin/env bash
#
# smoke_test.sh — post-deploy verification per 08_TestPlan §17.
#
# Checks:
#   - /health returns 200
#   - /briefs returns an array (possibly empty)
#   - /metrics returns exposition-format output
#   - dashboard renders (HTTP 200 on /)

set -euo pipefail

API_URL=${API_URL:-http://localhost:8000}
DASHBOARD_URL=${DASHBOARD_URL:-http://localhost:3000}

echo "[smoke] ${API_URL}/health"
curl -fsS "${API_URL}/health" | grep -q "agents"

echo "[smoke] ${API_URL}/briefs"
curl -fsS "${API_URL}/briefs?limit=1" | grep -q "items"

echo "[smoke] ${API_URL}/metrics"
curl -fsS "${API_URL}/metrics" | grep -q "# HELP"

echo "[smoke] ${DASHBOARD_URL}/"
curl -fsS "${DASHBOARD_URL}/" | grep -q "SwarmScout"

echo "smoke tests passed"
