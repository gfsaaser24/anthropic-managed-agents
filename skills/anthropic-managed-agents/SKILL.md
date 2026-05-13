---
name: anthropic-managed-agents
description: >-
  Build, deploy, operate, and test Claude Managed Agents through Anthropic's
  hosted agent harness API. Use whenever the user mentions "managed agents",
  "Claude Managed Agents", /v1/agents, /v1/sessions, /v1/environments, agent
  vaults, agent memory stores, agent skills attachment, multiagent
  coordinators, outcomes/rubrics, the ant CLI, the managed-agents-2026-04-01
  beta header, or asks to "create an agent", "run a Claude agent in the
  cloud", "deploy an agent", "stream agent events", "check session status",
  "rotate an agent credential", "attach a skill to an agent", "give my agent
  memory", or "test an agent against a rubric". Also trigger when code
  imports client.beta.agents, client.beta.sessions, client.beta.memory_stores,
  or client.beta.vaults from the Anthropic SDK in Python or TypeScript.
  Covers the full API surface, vault model, memory versioning, skills
  attachment, multiagent threads, webhooks, pricing, limits, and SDK shapes.
  Loads sub-modes for build, status, and test.
license: MIT
metadata:
  author: x.com/gabefletcher
  version: "0.2.0"
  references:
    - https://platform.claude.com/docs/en/managed-agents/overview
    - https://platform.claude.com/docs/en/managed-agents/quickstart
---

# Claude Managed Agents — Skill

This skill is the single source of truth for working with **Claude Managed Agents**, Anthropic's hosted agent harness. When this skill triggers, you have the entire API surface, the auth model, the runtime semantics, and the SDK/CLI shapes in scope.

## What this skill covers

Managed Agents is a Claude API beta (`anthropic-beta: managed-agents-2026-04-01`) that runs Claude as an autonomous agent inside Anthropic-managed cloud containers. You define an **Agent** (model + system prompt + tools + skills + MCP servers) and an **Environment** (container template), then start a **Session** that takes events and streams back agent/tool/span events over SSE.

It is **not** the same as the Claude Agent SDK. The Claude Agent SDK is an in-process library where you own the harness. Managed Agents *is* the harness — Anthropic provisions the container, executes tools, checkpoints state, and routes credentials.

## When to use Managed Agents vs alternatives

| Use case | Tool |
|---|---|
| Long-running tasks (minutes-to-hours), autonomous loop, hosted sandbox | **Managed Agents** |
| Fine-grained control, custom loop, your own infra | **Claude Agent SDK** |
| Single-turn or short multi-turn completions | **Messages API** |

Managed Agents is best for: long-running execution, cloud filesystem and package access, stateful sessions across interactions, and async work driven by webhooks.

## The four core objects

| Concept | What it is |
|---|---|
| **Agent** | Definition: model, system prompt, tools, MCP servers, skills, optional multiagent roster. Versioned. |
| **Environment** | Container template: packages (apt/cargo/gem/go/npm/pip), networking mode, name. Not versioned. |
| **Session** | Running instance of `agent × environment`. Provisions a container. Status: `idle`, `running`, `rescheduling`, `terminated`. |
| **Event** | Typed message exchanged via the session: user input, agent output, session lifecycle, span (observability). |

## Required headers on every request

```
x-api-key: $ANTHROPIC_API_KEY
anthropic-version: 2023-06-01
anthropic-beta: managed-agents-2026-04-01
content-type: application/json
```

Stack additional beta headers as needed:
- `fast-mode-2026-02-01` — when using `model: {speed: "fast"}` (Opus 4.7 supports fast mode).
- `files-api-2025-04-14` — Files API operations.
- `advisor-tool-2026-03-01` — advisor strategy.

Base URL: `https://api.anthropic.com/v1/`.

## Decision routing — read the right reference

This SKILL.md gives you the orientation. Drill into the reference that matches the task at hand. Each reference file is self-contained — read only what you need.

| Sub-mode | When to use it | Reference |
|---|---|---|
| **Build** | Creating or updating agents, environments, attaching skills/MCP servers/files, defining tools, versioning, deploy/rollback. | [`references/build.md`](references/build.md) |
| **Status check** | Listing agents/sessions, polling status, inspecting event history, debugging via Console, reading usage, observability via webhooks. | [`references/status.md`](references/status.md) |
| **Test** | Creating a session, sending user events, streaming SSE, custom-tool round-trips, outcomes/rubric loop, evaluation patterns. | [`references/test.md`](references/test.md) |
| **Local dev playbook** | When the user is running real agents from their machine: OAuth helpers, MCP auth quirks, vault Bearer-only limitation, Windows UTF-8, versioning workflow, error triage. **Hands-on knowledge not in the docs — read this when something breaks.** | [`references/local-dev-playbook.md`](references/local-dev-playbook.md) |
| Memory store internals | When the user asks about memory, persistence, `/mnt/memory/`, redaction, versioning of memories. | [`references/memory.md`](references/memory.md) |
| Vault and credentials | OAuth refresh, static bearer, validating credentials, rotating secrets, scoping. | [`references/vault.md`](references/vault.md) |
| Prompting and tools | System prompt shape, tool configs, permission policies, MCP, multiagent coordinator design, prompting patterns. | [`references/prompting.md`](references/prompting.md) |
| Python SDK | When the user is writing Python and imports `anthropic`. Covers `client.beta.*` methods. | [`references/sdk-python.md`](references/sdk-python.md) |
| TypeScript SDK | When the user is writing TS/JS and imports `@anthropic-ai/sdk`. | [`references/sdk-typescript.md`](references/sdk-typescript.md) |
| `ant` CLI | When the user is in a shell, wants curl-equivalents, or asks about the CLI. | [`references/ant-cli.md`](references/ant-cli.md) |
| Pricing, limits, gotchas | Quotas, billing model, rate limits, common failure modes. | [`references/limits-and-pricing.md`](references/limits-and-pricing.md) |

The `resources/` folder contains executable helpers — both curl wrappers and Python scripts proven on a production agent. They are not required, but they save real time:

- **`mcp-oauth-helper.py`** — one-shot dynamic-registration + PKCE OAuth flow that stores tokens in your vault with refresh wired. Pre-configured for Composio and Asana; trivially extended to any MCP server that follows the standard auth spec.
- **`validate-vault-credentials.py`** — probe every credential in a vault. Shows the actual MCP handshake response and refresh status.
- **`inspect-agent-vaults.py`** — print an agent's declared MCP servers and every vault + credential, so you can spot URL mismatches.
- **`cleanup-vault.py`** — vault hygiene (display name, metadata, hard-delete archived credentials).
- **`dump-agent-prompt.py`** — snapshot an agent's full config to markdown before any change.
- **`update-agent-template.py`** — copy-this template for versioning prompt updates. Sentinel-matched `str.replace()` + dry-run by default. Fails loud if the prompt has drifted.
- **`test-managed-agent.py`** — end-to-end smoke test (retrieve → env → session → stream).
- **`setup-memory-store.py`** + **`list-memory-stores.py`** — memory-store onboarding and inspection.
- **`fetch-recent-errors.py`** — surface `is_error=true` events from recent sessions without clicking through the Console.
- **`env.sh`**, **`create-agent.sh`**, **`create-session.sh`**, **`stream-events.sh`**, **`send-message.sh`**, **`session-status.sh`** — curl wrappers for pure-shell workflows.

## The minimum end-to-end flow

If the user just wants the **shortest path from zero to a running agent**, do this. Don't reach for references unless they want depth.

```bash
# 1. Create an agent definition
curl https://api.anthropic.com/v1/agents \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -d '{
    "name": "Coding Assistant",
    "model": "claude-opus-4-7",
    "system": "You are a helpful coding assistant. Write clean, well-documented code.",
    "tools": [{"type": "agent_toolset_20260401"}]
  }'
# -> { "id": "agent_01...", "version": 1, ... }

# 2. Create an environment (container template)
curl https://api.anthropic.com/v1/environments \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -d '{
    "name": "quickstart-env",
    "config": {"type": "cloud", "networking": {"type": "unrestricted"}}
  }'
# -> { "id": "env_01...", ... }

# 3. Create a session (provisions container, status=idle, no work yet)
curl https://api.anthropic.com/v1/sessions \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -d '{"agent": "agent_01...", "environment_id": "env_01..."}'
# -> { "id": "sesn_01...", "status": "idle", ... }

# 4. Open SSE stream BEFORE sending the first event (race-condition prevention)
curl -N https://api.anthropic.com/v1/sessions/sesn_01.../events/stream \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" &

# 5. Send a user message
curl https://api.anthropic.com/v1/sessions/sesn_01.../events \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -d '{
    "events": [{
      "type": "user.message",
      "content": [{"type": "text", "text": "Create a Python script that prints Fibonacci numbers."}]
    }]
  }'
```

The `ant` CLI collapses this into four short commands — see [`references/ant-cli.md`](references/ant-cli.md).

## Race condition you must avoid

The SSE stream only delivers events emitted **after** the stream is opened. Always open the stream **before** sending the first user event, or you'll miss the start. To resume cleanly after disconnect: open new stream → call `GET /v1/sessions/{id}/events` to seed a `seen_event_ids` set → tail the live stream skipping seen IDs.

## What Managed Agents is good at

- **Long-running autonomous work.** Sessions can run for minutes or hours. Container is checkpointed when the session goes idle and resumed when the next event arrives.
- **Cloud filesystem persistence.** A container per session, files persist across events, full Ubuntu 22.04 toolchain pre-installed.
- **State plumbing handed to you.** Conversation history, memory stores, vaults, files, multiagent threads — all managed.
- **Built-in observability.** Span events emit per model request and outcome evaluation; usage tokens reported on session; Console has tracing view.
- **Multiagent fan-out.** One coordinator can delegate to up to 20 sub-agents across 25 concurrent threads — all sharing the same container.
- **Outcomes/rubric loop.** Self-evaluating grader iterates the agent until the rubric is satisfied or `max_iterations` reached.

## What Managed Agents is NOT good at

- **Sub-second latency workflows.** You're driving a streaming session, not a chat completion. Use the Messages API for synchronous request-response.
- **Self-hosted deployments.** There is no on-prem Managed Agents. The closest alternative is Claude Platform on AWS, which is still Anthropic-operated infrastructure — only the billing/auth layer is AWS.
- **Custom container images.** You configure packages via `apt/cargo/gem/go/npm/pip`, not by supplying a Dockerfile. The base image is fixed: Ubuntu 22.04 LTS on x86_64, 8 GB RAM, 10 GB disk.
- **Workloads needing >10 GB disk or >8 GB RAM.** Stream large data instead of mounting it.
- **Read-after-write on files mounted via `resources`.** Mounted files are read-only copies. The agent must write modifications to new paths.
- **Tight cost predictability at small scale.** Billing combines per-token charges with a $0.08/session-hour runtime charge. Idle time is free, but if you can't bound session runtime you can't bound spend.
- **Cross-workspace credential isolation.** Vaults are workspace-scoped: anyone with API-key access can use any vault. There is no per-user ACL. Build user separation into vault `metadata.external_user_id` and your own routing layer.
- **Skills that need network access at skill-runtime.** Inside the Agent Skills code-execution sandbox, skills cannot make network calls and cannot `pip install`. However, when a skill triggers inside a Managed Agents session, the agent uses the *Environment* container — so it has whatever network and packages the environment was configured with.

## Versioning model

- Agents are versioned. Every `POST /v1/agents/{id}` that changes any field creates a **new immutable version**. No-op updates return the existing version (no bump).
- Update semantics:
  - Scalar fields (`name`, `model`, `system`, `description`) are *replaced*; `system`/`description` can be cleared with `null`; `model`/`name` cannot.
  - Array fields (`tools`, `mcp_servers`, `skills`) are *fully replaced*. Pass `[]` to clear.
  - `multiagent` is replaced as a whole.
  - `metadata` is *merged* per-key — pass an empty string to delete a key.
  - Include `"version": N` in your update body as an optimistic-concurrency guard.
- Sessions pin a version implicitly (latest) unless you pass the object form: `"agent": {"type": "agent", "id": "agent_01...", "version": 2}`.
- Rollback = create a session pinned to the older version, or `POST /v1/agents/{id}` with the old field values to make a new version that matches the old behavior.
- Environments are **not** versioned. Archive + recreate to "version" them.

## Memory in one paragraph

A memory store is a workspace-scoped, version-controlled collection of text documents. Attach up to 8 stores to a session at creation time (you cannot attach/detach mid-session). Each store mounts as a directory under `/mnt/memory/`. The agent reads/writes with normal file tools. Every mutation creates an immutable memory version (`memver_...`) retained 30 days. `access: "read_only"` is the safe default when the agent processes untrusted input — `read_write` is vulnerable to prompt-injection writes that later sessions will trust. Individual memories cap at 100 kB (~25k tokens). Deep dive: [`references/memory.md`](references/memory.md).

## Vault in one paragraph

A vault stores credentials (`mcp_oauth` or `static_bearer`) that the session's MCP connectors consume at runtime. Agents declare MCP servers; vaults supply the secrets. Vaults are workspace-scoped, one credential per `mcp_server_url`, max 20 credentials per vault. Secret fields are write-only — Anthropic never returns them. Validate credential health with `POST /v1/vaults/{vid}/credentials/{cid}/mcp_oauth_validate?beta=true`. Background refresh is supported when you supply a `refresh` object with `token_endpoint`/`refresh_token`. Deep dive: [`references/vault.md`](references/vault.md).

## Skills attachment in one paragraph

Skills are attached to an agent at create-time, not to a session. Two types: **`anthropic`** (Anthropic-built — `pdf`, `docx`, `xlsx`, `pptx`) and **`custom`** (workspace-authored, identified by `skill_*` ID, pinnable by version or `"version": "latest"`). Up to 20 skills per session — counted across all agents in a multiagent session. The skill's `SKILL.md` metadata (name + description, ~100 tokens) is always in the agent's context; the body loads on trigger; bundled files load via filesystem reads. Deep dive: [`references/build.md`](references/build.md) §Skills.

## Tools in one paragraph

Three flavors: **`agent_toolset_20260401`** (built-in: bash, read, write, edit, glob, grep, web_fetch, web_search), **`mcp_toolset`** (one per MCP server declared on the agent), and **`custom`** (your client executes; the session emits `agent.custom_tool_use` and pauses with `requires_action`). Permission policies (`always_allow` / `always_ask`) apply to agent and MCP toolsets but **not** to custom tools. Default: agent toolset = `always_allow`, MCP toolset = `always_ask`. Deep dive: [`references/prompting.md`](references/prompting.md) §Tools.

## Pricing in one paragraph

Two axes: standard Claude API token rates **plus** `$0.08 per session-hour` measured to the millisecond, accruing only while session status is `running` (idle time is free). Web search adds `$10 / 1k searches`. Code execution container is included in the session-hour rate. Worked example from Anthropic: a one-hour Opus 4.6 session with 50k input / 15k output tokens = ~$0.705 total, of which only $0.08 (11%) is the session runtime. Deep dive: [`references/limits-and-pricing.md`](references/limits-and-pricing.md).

## Hard limits at a glance

| Thing | Limit |
|---|---|
| Skills per session (across all agents) | 20 |
| Files per session | 100 |
| Memory stores per session | 8 |
| Bytes per memory | 100 kB |
| Credentials per vault | 20 |
| MCP servers per agent | 20 |
| Memory store `instructions` | 4,096 chars |
| Memory version retention | 30 days (recent always kept) |
| Container checkpoint retention | 30 days after last activity |
| Multiagent agents in coordinator roster | 20 unique |
| Concurrent threads per session | 25 |
| Outcome `max_iterations` | default 3, max 20 |
| Container RAM / disk | 8 GB / 10 GB |
| Create endpoints rate limit | 300 rpm/org |
| Read endpoints rate limit | 600 rpm/org |
| Webhook payload max age before reject | 5 minutes |

## SDK shape (Python)

All Managed Agents calls live under `client.beta.*`:

```python
client.beta.agents.create / retrieve / list / update / archive
client.beta.agents.versions.list
client.beta.environments.create / retrieve / list / archive / delete
client.beta.sessions.create / retrieve / list / archive / delete
client.beta.sessions.events.send / list / stream
client.beta.sessions.resources.add / list / delete
client.beta.sessions.threads.list / archive
client.beta.sessions.threads.events.list / stream_events
client.beta.memory_stores.create / retrieve / update / list / archive / delete
client.beta.memory_stores.memories.create / retrieve / update / list / delete
client.beta.memory_stores.memory_versions.list / retrieve / redact
client.beta.vaults.create / retrieve / list / archive / delete
client.beta.vaults.credentials.create / update / archive / delete
client.beta.files.upload / list / download
client.beta.webhooks.unwrap
```

The official SDKs add the `anthropic-beta: managed-agents-2026-04-01` header automatically. Stream methods return async iterators.

## Working agreement when this skill is active

1. **Always send the beta header.** Either let the SDK do it (preferred) or include `anthropic-beta: managed-agents-2026-04-01` on every request. Without it, the API returns 400.
2. **Open the SSE stream before sending the first user event.** This is the most common race-condition bug in beginner code.
3. **Pin agent versions in production.** Use `{"type": "agent", "id": "...", "version": N}` so an unrelated agent update doesn't change behavior mid-deploy.
4. **Default vault credentials to `read_only` memory when handling untrusted input.** Prompt injection that writes memory will be trusted by future sessions.
5. **Never assume sessions auto-start.** A freshly created session is `idle` until you POST a user event.
6. **Bound session runtime with `user.interrupt` or session deletion.** Otherwise a stuck agent racks up $0.08/hr indefinitely.
7. **Use webhooks (not polling) for async workflows.** Register at `platform.claude.com/settings/workspaces/{ws}/webhooks`. Verify via `client.beta.webhooks.unwrap(rawBody, { headers })`. Payloads >5 min old are rejected by the SDK.
8. **For multiagent, post tool confirmations on the *primary* session events endpoint** — the server routes them to the correct thread by `tool_use_id`.
9. **Vaults inject `Authorization: Bearer` only.** If an MCP server uses a custom header (e.g. Composio's `x-consumer-api-key`), use full OAuth — even when you have a working static API key. There is no shortcut.
10. **On Windows, every helper script needs `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`** at the top, or the cp1252 default codec crashes on agent output containing emoji or non-Latin text.

If a user asks something that lands squarely in a sub-mode (build/status/test), open the corresponding reference and follow its checklist. Don't recapitulate this whole document.
