#!/usr/bin/env bash
# Stream SSE events from a session. Always run this BEFORE sending the first user event.
# Usage: ./stream-events.sh <session-id>
# Requires: source ./env.sh first.
set -euo pipefail

SESSION_ID="${1:?usage: stream-events.sh <session-id>}"

curl -N -sS "${ANTHROPIC_BASE}/sessions/${SESSION_ID}/events/stream" \
  -H "x-api-key: ${ANTHROPIC_API_KEY}" \
  -H "anthropic-version: ${ANTHROPIC_VERSION}" \
  -H "anthropic-beta: ${ANTHROPIC_BETA}"
