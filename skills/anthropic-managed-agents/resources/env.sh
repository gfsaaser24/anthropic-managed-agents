#!/usr/bin/env bash
# Source this file to set the headers and base URL for curl-based Managed Agents work.
# Usage: source ./env.sh

: "${ANTHROPIC_API_KEY:?ANTHROPIC_API_KEY must be set}"

export ANTHROPIC_BASE="https://api.anthropic.com/v1"
export ANTHROPIC_BETA="managed-agents-2026-04-01"
export ANTHROPIC_VERSION="2023-06-01"

ant_curl() {
  # Convenience wrapper that prepends required headers.
  # Usage: ant_curl <method> <path> [extra curl args...]
  local method="$1"; shift
  local path="$1"; shift
  curl -sS -X "$method" "${ANTHROPIC_BASE}${path}" \
    -H "x-api-key: ${ANTHROPIC_API_KEY}" \
    -H "anthropic-version: ${ANTHROPIC_VERSION}" \
    -H "anthropic-beta: ${ANTHROPIC_BETA}" \
    -H "content-type: application/json" \
    "$@"
}

export -f ant_curl
