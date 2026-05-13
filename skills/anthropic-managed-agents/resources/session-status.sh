#!/usr/bin/env bash
# Retrieve a session's current status and usage.
# Usage: ./session-status.sh <session-id>
# Requires: source ./env.sh first.
set -euo pipefail

SESSION_ID="${1:?usage: session-status.sh <session-id>}"

ant_curl GET "/sessions/${SESSION_ID}" | jq '{id, status, stop_reason, usage, agent, environment_id, updated_at}'
