#!/usr/bin/env bash
# Create a Managed Agent.
# Usage: ./create-agent.sh <name> <model> <system-prompt-file>
# Requires: source ./env.sh first.
set -euo pipefail

NAME="${1:?usage: create-agent.sh <name> <model> <system-prompt-file>}"
MODEL="${2:?model required}"
SYSTEM_FILE="${3:?system prompt file required}"
SYSTEM="$(cat "$SYSTEM_FILE")"

ant_curl POST /agents -d "$(jq -n \
  --arg name "$NAME" \
  --arg model "$MODEL" \
  --arg system "$SYSTEM" \
  '{name: $name, model: $model, system: $system, tools: [{type: "agent_toolset_20260401"}]}')"
