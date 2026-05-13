# `ant` CLI

The `ant` CLI is Anthropic's official command-line client for the Claude API, including Managed Agents. It was released alongside Managed Agents public beta on April 8, 2026.

## Install

```bash
brew install anthropics/tap/ant
```

Or download from `github.com/anthropics/anthropic-cli/releases`:

```bash
curl -fsSL "https://github.com/anthropics/anthropic-cli/releases/download/v${VERSION}/ant_${VERSION}_${OS}_${ARCH}.tar.gz" \
  | sudo tar -xz -C /usr/local/bin ant
```

Or via Go:

```bash
go install github.com/anthropics/anthropic-cli/cmd/ant@latest
```

## Auth

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

The CLI adds the `managed-agents-2026-04-01` beta header automatically on the `beta:*` subcommands.

## End-to-end quickstart

```bash
# 1. Create an agent
ant beta:agents create \
  --name "Coding Assistant" \
  --model '{id: claude-opus-4-7}' \
  --system "You are a helpful coding assistant. Write clean, well-documented code." \
  --tool '{type: agent_toolset_20260401}'
# → returns agent_id; capture it
AGENT_ID=...

# 2. Create an environment
ant beta:environments create \
  --name "quickstart-env" \
  --config '{type: cloud, networking: {type: unrestricted}}'
ENV_ID=...

# 3. Create a session
ant beta:sessions create --agent "$AGENT_ID" --environment-id "$ENV_ID"
SESSION_ID=...

# 4. Stream events (in another shell)
ant beta:sessions:events stream --session-id "$SESSION_ID"

# 5. Send a user message
ant beta:sessions:events send --session-id "$SESSION_ID" <<'YAML'
events:
  - type: user.message
    content:
      - type: text
        text: Create a Python script that generates the first 20 Fibonacci numbers...
YAML
```

The CLI accepts YAML (heredoc) or JSON via `--data` or `--file`.

## Subcommand inventory

```bash
# Agents
ant beta:agents create | retrieve | list | update | archive
ant beta:agents:versions list --agent-id ...

# Environments
ant beta:environments create | retrieve | list | archive | delete

# Sessions
ant beta:sessions create | retrieve | list | archive | delete

# Session events
ant beta:sessions:events send | list | stream

# Session resources
ant beta:sessions:resources add | list | delete

# Session threads (multiagent)
ant beta:sessions:threads list | archive
ant beta:sessions:threads:events list | stream

# Memory stores
ant beta:memory-stores create | retrieve | update | list | archive | delete
ant beta:memory-stores:memories create | retrieve | update | list | delete
ant beta:memory-stores:memory-versions list | retrieve | redact

# Vaults
ant beta:vaults create | retrieve | list | archive | delete
ant beta:vaults:credentials create | update | archive | delete

# Files
ant beta:files upload --file ./data.csv
ant beta:files list --scope-id sesn_...
ant beta:files download --file-id file_... --output ./out.txt
```

## Output formatting

```bash
ant ... --format json
ant ... --format yaml
ant ... --format jsonl       # one event per line, great for piping
ant ... --format table       # tabular for lists
ant ... --raw-output         # disables headers/colors for piping
```

Use `jsonl` for `events stream` so you can pipe into `jq`, `grep`, or your own scripts:

```bash
ant beta:sessions:events stream --session-id "$SESSION_ID" --format jsonl \
  | jq 'select(.type == "agent.message") | .content[].text'
```

## Filters

```bash
ant beta:sessions:events list --session-id ... --type agent.tool_use --type agent.tool_result
ant beta:sessions list --status running
```

## Interactive onboarding

Inside Claude Code:

```
/claude-api managed-agents-onboard
```

Walks you through the install, key setup, and a first end-to-end run.

## Transforms

`--transform` accepts a JMESPath-style expression for inline projection:

```bash
ant beta:sessions list --format json --transform 'data[?status==`running`].{id: id, agent: agent.id}'
```

## Why the CLI vs curl

- **No header juggling** — the CLI applies version + beta headers automatically.
- **YAML input** — much easier to handcraft event payloads than escaped JSON.
- **`--format jsonl` streaming** — clean pipe-friendly output for shell scripts and CI.
- **Auth context switching** — `--profile` and config file support multiple workspaces.

## Why curl over the CLI

- CI environments without Go/Homebrew.
- When you want exact wire-level control over headers.
- When you're translating a snippet for the [resources/](../resources) shell helpers in this skill.
