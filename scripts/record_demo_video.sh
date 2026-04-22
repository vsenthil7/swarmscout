#!/usr/bin/env bash
#
# record_demo_video.sh — Playwright-driven capture of the dashboard,
# verify round-trip, Telegram alert, bot /verify, and model usage panel.
#
# Outputs:
#   demo.webm           raw capture
#   demo.mp4            h264 for DoraHacks upload (ffmpeg)
#
# Target run time: 2 min 45 s. Hard ceiling: 3 min (hackathon rule).

set -euo pipefail

cd "$(dirname "$0")/.."
cd web

export PLAYWRIGHT_BASE_URL=${PLAYWRIGHT_BASE_URL:-http://localhost:3000}

pnpm exec playwright test tests/e2e/demo.spec.ts --project=chromium-desktop

if [ -f test-results/demo/video.webm ]; then
  cp test-results/demo/video.webm ../demo.webm
  if command -v ffmpeg >/dev/null 2>&1; then
    ffmpeg -y -i ../demo.webm -c:v libx264 -c:a aac -movflags +faststart ../demo.mp4
  fi
  echo "demo written to $(realpath ../demo.webm)"
else
  echo "no video captured; check playwright output"
  exit 1
fi
