# anthropic-managed-agents

A Claude Code / Agent Skills–compatible skill that gives Claude full operational knowledge of **Anthropic's Claude Managed Agents** API.

When this skill loads, the model has the entire Managed Agents surface — agent/environment/session lifecycle, vault and memory semantics, skill attachment, multiagent threads, outcomes/rubrics, webhooks, the `ant` CLI, and both Python and TypeScript SDK shapes.

## What you get

- `SKILL.md` — orientation, decision routing, working agreement.
- `references/build.md` — creating agents, environments, attaching skills/MCP/files, versioning.
- `references/status.md` — listing, polling, event history, debugging, webhooks, retention.
- `references/test.md` — running sessions, SSE, custom-tool round trips, outcomes, harness patterns.
- `references/memory.md` — memory stores, version history, redaction, security.
- `references/vault.md` — credential management, OAuth refresh, validation.
- `references/prompting.md` — system prompt design, tool design, multiagent patterns, caching.
- `references/sdk-python.md` — `client.beta.*` method tree, end-to-end example, webhook verification.
- `references/sdk-typescript.md` — same in TS.
- `references/ant-cli.md` — official CLI commands and output formatting.
- `references/limits-and-pricing.md` — limits, rate limits, pricing model, failure modes.
- `references/local-dev-playbook.md` — **hands-on learnings from running a real agent in production**: vault Bearer-only injection limit, Composio + Asana OAuth quirks, Windows UTF-8, error triage, versioning workflow. Read this when something breaks.
- `resources/*.sh` — curl wrappers (`env.sh`, `create-agent.sh`, `create-session.sh`, `stream-events.sh`, `send-message.sh`, `session-status.sh`).
- `resources/*.py` — proven Python helpers: `mcp-oauth-helper.py` (dynamic registration + PKCE), `validate-vault-credentials.py`, `inspect-agent-vaults.py`, `cleanup-vault.py`, `dump-agent-prompt.py`, `update-agent-template.py`, `test-managed-agent.py`, `setup-memory-store.py`, `list-memory-stores.py`, `fetch-recent-errors.py`.

## When this skill triggers

Trigger phrases (already in the description, but for human reference):

- "create a managed agent", "deploy an agent", "run a Claude agent in the cloud"
- "managed agents", "Claude Managed Agents"
- "stream agent events", "check session status", "rotate an agent credential"
- "attach a skill to an agent", "give my agent memory", "test an agent against a rubric"
- imports of `client.beta.agents`, `client.beta.sessions`, `client.beta.memory_stores`, `client.beta.vaults`
- `/v1/agents`, `/v1/sessions`, `/v1/environments` endpoints
- `anthropic-beta: managed-agents-2026-04-01` header
- the `ant` CLI

## Install (Claude Code)

```bash
mkdir -p ~/.claude/skills
cp -r skills/anthropic-managed-agents ~/.claude/skills/
```

Or use the [Agent Skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add gfsaaser24/anthropic-managed-agents
```

## Snapshot date

This skill reflects the Managed Agents API as of **2026-05-12**. The beta header is `managed-agents-2026-04-01`. Sub-features that are research preview (Outcomes, Multiagent) require access via `https://claude.com/form/claude-managed-agents`.

## License

MIT
