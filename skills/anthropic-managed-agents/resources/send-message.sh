#!/usr/bin/env bash
# Send a user.message event to a session.
# Usage: ./send-message.sh <session-id> "<message text>"
# Requires: source ./env.sh first.
set -euo pipefail

SESSION_ID="${1:?usage: send-message.sh <session-id> <text>}"
TEXT="${2:?text required}"

BODY=$(jq -n --arg text "$TEXT" \
  '{events: [{type: "user.message", content: [{type: "text", text: $text}]}]}')

ant_curl POST "/sessions/${SESSION_ID}/events" -d "$BODY"
