#!/usr/bin/env bash
# Create a session and (optionally) attach vaults and resources.
# Usage: ./create-session.sh <agent-id> <env-id> [vault-id...]
# Requires: source ./env.sh first.
set -euo pipefail

AGENT_ID="${1:?usage: create-session.sh <agent-id> <env-id> [vault-id...]}"
ENV_ID="${2:?env id required}"
shift 2
VAULT_IDS=("$@")

BODY=$(jq -n \
  --arg agent "$AGENT_ID" \
  --arg env "$ENV_ID" \
  --argjson vaults "$(printf '%s\n' "${VAULT_IDS[@]:-}" | jq -R . | jq -s 'map(select(length>0))')" \
  '{agent: $agent, environment_id: $env} + (if $vaults | length > 0 then {vault_ids: $vaults} else {} end)')

ant_curl POST /sessions -d "$BODY"
