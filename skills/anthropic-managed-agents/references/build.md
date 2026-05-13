# Build sub-mode — creating and configuring Managed Agents

Use this reference when the user is **defining** a managed agent: creating it, editing it, attaching skills, MCP servers, custom tools, files, memory stores; configuring environments; designing a multiagent coordinator. For *running* the agent against a task, use [`test.md`](test.md).

## What you build, in order

```
Agent definition       Environment template       Vaults & Memory stores
       ↓                       ↓                            ↓
   agent_01...             env_01...               vlt_01... / memstore_01...
              \______________ ↓ ______________________/
                              ↓
                        Session creation
                        (provisions container)
```

Agents, environments, vaults, and memory stores are **independent, long-lived resources**. Sessions assemble them at create time.

## 1. Agent — `POST /v1/agents`

### Minimum viable agent

```json
{
  "name": "Coding Assistant",
  "model": "claude-opus-4-7",
  "system": "You are a helpful coding assistant. Write clean, well-documented code.",
  "tools": [{"type": "agent_toolset_20260401"}]
}
```

### Full field reference

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Human label. Cannot be cleared. |
| `model` | yes | String (`"claude-opus-4-7"`) or object `{"id": "claude-opus-4-7", "speed": "fast"}`. `"fast"` requires the `fast-mode-2026-02-01` beta header (Opus 4.7 only). All Claude 4.5+ models supported. |
| `system` | no | The system prompt. Distinct from user messages. Pass `null` to clear. |
| `tools` | no | Array. Replaced as a whole on update. Mix `agent_toolset_20260401`, `mcp_toolset`, `custom`. See §Tools. |
| `mcp_servers` | no | Up to 20 per agent. Two-step model: declared here, credentials supplied per-session via vaults. See §MCP. |
| `skills` | no | Up to 20 per session (across all agents in a multiagent session). See §Skills. |
| `multiagent` | no | Coordinator declaration. See §Multiagent. |
| `description` | no | Free text. Pass `null` to clear. |
| `metadata` | no | Arbitrary key-value. **Merge** semantics on update (empty string deletes a key). |

### Response shape

```json
{
  "id": "agent_01HqR2k7vXbZ9mNpL3wYcT8f",
  "type": "agent",
  "name": "Coding Assistant",
  "model": {"id": "claude-opus-4-7", "speed": "standard"},
  "system": "You are a helpful coding agent.",
  "description": null,
  "tools": [{"type": "agent_toolset_20260401", "default_config": {"permission_policy": {"type": "always_allow"}}}],
  "skills": [],
  "mcp_servers": [],
  "metadata": {},
  "version": 1,
  "created_at": "2026-04-03T18:24:10.412Z",
  "updated_at": "2026-04-03T18:24:10.412Z",
  "archived_at": null
}
```

## 2. Versioning — `POST /v1/agents/{id}` (update)

Every update that changes any field creates a new immutable version. The version number on the response tells you what was minted.

```json
POST /v1/agents/agent_01HqR.../
{"version": 1, "system": "You are a helpful coding agent. Always write tests."}
```

The `"version": 1` in the body is the **expected current version** — an optimistic-concurrency guard. If the agent has already moved past version 1, you get a 409.

### What's replaced vs merged

| Update behavior | Fields |
|---|---|
| **Replace scalar** (or clear with `null`) | `model`, `name`, `system`, `description` (only `system`/`description` clearable) |
| **Replace array** (pass `[]` to clear) | `tools`, `mcp_servers`, `skills` |
| **Replace as a whole** | `multiagent` |
| **Merge per-key** (empty string deletes) | `metadata` |
| **Omitted** | Preserved |
| **No-op detection** | If the update produces no change, no new version is created |

### List versions — `GET /v1/agents/{id}/versions`

Returns history. Sessions can pin a specific version via `{"agent": {"type": "agent", "id": "agent_01...", "version": N}}`.

### Rollback

Two options:
1. **Pin sessions** to the older version going forward. Existing sessions on the new version keep their version.
2. **Forward-roll back** — `POST /v1/agents/{id}` with the old field values to mint a new version that behaves like the old one.

There is no "set active version" — sessions choose the version at creation time.

### Versioning workflow that survives real iteration

After ~5 versions of a real agent, ad-hoc updates become hazardous — the prompt has drifted, your local copy is stale, and a "small" change blows away unrelated content. The pattern that holds up:

1. **Snapshot first.** Dump the current prompt + tools + metadata to a markdown file before any change. See [`../resources/dump-agent-prompt.py`](../resources/dump-agent-prompt.py).
2. **Write a proposal as a sibling markdown file** (`agent-vN-proposed.md`) showing the full new system prompt. Review before any API call.
3. **Patch with sentinel-matched `str.replace()`, not full rewrites.** Pull the current prompt, apply exact-string find/replace with surrounding context, and **fail loud if a needle is missing**:

```python
# resources/update-agent-template.py
for needle, replacement in EDITS:
    if needle not in prompt:
        raise SystemExit(f"XX needle not found: {needle!r}")
    if prompt.count(needle) > 1:
        raise SystemExit(f"XX needle not unique ({prompt.count(needle)}x): {needle!r}")
    prompt = prompt.replace(needle, replacement)
```

4. **Default to dry-run.** Gate the actual `agents.update` call behind an explicit `--apply` flag. Print the diff without `--apply`; only mutate state when explicitly invoked.

5. **Bake operational discoveries back into the prompt.** A session that burns 15 turns rediscovering an integration quirk usually collapses to 2–3 turns once that quirk is in the system prompt. Prompt-token cost is more than offset by skipped discovery loops and better cache reuse.

A ready-to-copy template lives at [`../resources/update-agent-template.py`](../resources/update-agent-template.py).

### Archive — `POST /v1/agents/{id}/archive`

Sets `archived_at`. New sessions cannot reference the agent; existing sessions continue. There is no unarchive — recreate if needed.

## 3. Environment — `POST /v1/environments`

```json
{
  "name": "data-analysis",
  "config": {
    "type": "cloud",
    "packages": {
      "apt": ["ffmpeg"],
      "pip": ["pandas==2.2.0", "numpy", "scikit-learn"],
      "npm": ["express@4.18.0"]
    },
    "networking": {"type": "unrestricted"}
  }
}
```

### Package managers

| Field | Manager | Example |
|---|---|---|
| `apt` | apt-get | `"ffmpeg"` |
| `cargo` | cargo | `"ripgrep@14.0.0"` |
| `gem` | bundler/gem | `"rails:7.1.0"` |
| `go` | go modules | `"golang.org/x/tools/cmd/goimports@latest"` |
| `npm` | npm | `"express@4.18.0"` |
| `pip` | pip | `"pandas==2.2.0"` |

When multiple managers are present, they install in alphabetical order (apt, cargo, gem, go, npm, pip). Default version is latest.

### Networking modes

| Mode | Behavior |
|---|---|
| `unrestricted` | **Default.** Full outbound except Anthropic's safety blocklist. |
| `limited` | HTTPS-only egress to `allowed_hosts`. Configure `allow_mcp_servers` (default false) and `allow_package_managers` (default false). |

```json
{
  "type": "cloud",
  "networking": {
    "type": "limited",
    "allowed_hosts": ["api.example.com"],
    "allow_mcp_servers": true,
    "allow_package_managers": true
  }
}
```

**Production rule:** use `limited` with an explicit `allowed_hosts` list. The `networking` field does NOT govern `web_search`/`web_fetch` tool destinations — those are tool-level configs.

### Container specs (fixed, not configurable)

| Property | Value |
|---|---|
| OS | Ubuntu 22.04 LTS |
| Arch | x86_64 (amd64) |
| RAM | up to 8 GB |
| Disk | up to 10 GB |
| Default network | disabled (configure via `networking`) |

Pre-installed: Python 3.12+ (`pip`, `uv`), Node 20+ (`npm`, `yarn`, `pnpm`), Go 1.22+, Rust 1.77+, Java 21+ (`maven`, `gradle`), Ruby 3.3+ (`bundler`, `gem`), PHP 8.3+ (`composer`), C/C++ GCC 13+ (`make`, `cmake`). Tools: `git`, `curl`, `wget`, `jq`, `tar`, `zip`, `unzip`, `ssh`, `scp`, `tmux`, `screen`, `ripgrep`, `tree`, `htop`, `sed`, `awk`, `grep`, `vim`, `nano`, `diff`, `patch`. Clients: `sqlite` (pre-installed), `psql`, `redis-cli`. **No DB servers run by default.**

### Environment lifecycle

- Environments are **not versioned**. To change them, archive and recreate.
- `POST /v1/environments/{id}/archive` — read-only; existing sessions continue.
- `DELETE /v1/environments/{id}` — only if no sessions reference it.
- Multiple sessions can share an environment. Each session gets its own container instance — **filesystems do not share state across sessions**.

## 4. Tools

### Built-in toolset — `agent_toolset_20260401`

Eight tools: `bash`, `read`, `write`, `edit`, `glob`, `grep`, `web_fetch`, `web_search`. All enabled by default.

```json
{"type": "agent_toolset_20260401"}
```

Disable specific tools:

```json
{
  "type": "agent_toolset_20260401",
  "configs": [{"name": "web_fetch", "enabled": false}]
}
```

Inverted default (start disabled, allow-list):

```json
{
  "type": "agent_toolset_20260401",
  "default_config": {"enabled": false},
  "configs": [
    {"name": "bash", "enabled": true},
    {"name": "read", "enabled": true},
    {"name": "write", "enabled": true}
  ]
}
```

### MCP toolset — one per MCP server

```json
{"type": "mcp_toolset", "mcp_server_name": "github"}
```

`mcp_server_name` must match a `name` in `mcp_servers[]` on the same agent.

### Custom tool — your client executes

```json
{
  "type": "custom",
  "name": "get_weather",
  "description": "Get current weather for a location. Returns temperature in Celsius and conditions.",
  "input_schema": {
    "type": "object",
    "properties": {"location": {"type": "string", "description": "City name"}},
    "required": ["location"]
  }
}
```

When the agent calls a custom tool: session emits `agent.custom_tool_use`, pauses with `session.status_idle` + `stop_reason: requires_action`, and lists the blocked event IDs. You execute the tool, then send `user.custom_tool_result` per ID. See [`test.md`](test.md) for the round-trip protocol.

**Custom tool best practices:**
- Write 3–4 sentence descriptions. Vague descriptions hurt tool selection.
- Consolidate related operations behind an `action` parameter rather than 12 tiny tools.
- Namespace names (`db_query`, `storage_read`) so the agent doesn't confuse them.
- Return high-signal semantic identifiers, not bloated raw responses.

### Permission policies

| Policy | Behavior |
|---|---|
| `always_allow` | Auto-execute. **Default for `agent_toolset_20260401`.** |
| `always_ask` | Pauses with `requires_action`. You respond with `user.tool_confirmation`. **Default for `mcp_toolset`.** |

Apply at the toolset level (`default_config.permission_policy`) or per-tool (`configs[].permission_policy`):

```json
{
  "type": "agent_toolset_20260401",
  "default_config": {"permission_policy": {"type": "always_allow"}},
  "configs": [{"name": "bash", "permission_policy": {"type": "always_ask"}}]
}
```

**Permission policies do not apply to custom tools.** Your client always sees the call (that's the whole point of custom tools — you're the executor).

## 5. MCP servers

Two-step model: declare servers at the agent (no secrets), supply credentials at the session via vault references.

```json
{
  "name": "GitHub Assistant",
  "model": "claude-opus-4-7",
  "mcp_servers": [
    {"type": "url", "name": "github", "url": "https://api.githubcopilot.com/mcp/"}
  ],
  "tools": [
    {"type": "agent_toolset_20260401"},
    {"type": "mcp_toolset", "mcp_server_name": "github"}
  ]
}
```

The MCP server must support the streamable HTTP transport. If a vault is supplied at session-create but contains invalid credentials, the session still succeeds — a `session.error` event surfaces the auth failure and retries on the next `idle → running` transition.

## 6. Skills attachment

```json
{
  "name": "Financial Analyst",
  "model": "claude-opus-4-7",
  "system": "You are a financial analysis agent.",
  "skills": [
    {"type": "anthropic", "skill_id": "xlsx"},
    {"type": "custom", "skill_id": "skill_abc123", "version": "latest"}
  ]
}
```

### Two skill types

| Type | `skill_id` | `version` |
|---|---|---|
| `anthropic` | Short name: `pdf`, `docx`, `xlsx`, `pptx` | Not used |
| `custom` | Workspace `skill_*` ID | Specific number or `"latest"` |

### Counting limit

Max **20 skills per session**. In multiagent sessions, that 20 is the **sum across all agents** in the session.

### How skills load (progressive disclosure)

| Level | What loads | Cost |
|---|---|---|
| 1 — Always | `name` + `description` from SKILL.md frontmatter | ~100 tokens per skill |
| 2 — When triggered | SKILL.md body | <5k tokens |
| 3 — On demand | Bundled files (additional `.md`, scripts, `assets/`) | Effectively unlimited — agent reads from disk via bash |

### Authoring a custom skill (frontmatter rules)

```yaml
---
name: pdf-processing
description:
  Extract text and tables from PDF files, fill forms, merge documents. Use
  when working with PDF files or when the user mentions PDFs, forms, or
  document extraction.
---
```

- `name`: ≤64 chars, lowercase letters/numbers/hyphens, no XML tags, **no reserved words "anthropic" or "claude"**.
- `description`: non-empty, ≤1024 chars, no XML tags. **Include trigger phrases verbatim** ("Use when…"), because this is the only field besides `name` that's loaded at level 1.

Authoring is described in detail at `/docs/en/agents-and-tools/agent-skills/overview`.

### Skill runtime caveat

Inside the Agent Skills code-execution sandbox (standalone Skills feature), there is **no network access and no runtime package installation**. But when a skill triggers inside a Managed Agents session, the code runs in the **Environment** container, which has whatever network and packages you configured. Don't confuse the two sandboxes.

## 7. Files / resources

### Upload — `POST /v1/files` (multipart)

Use the `files-api-2025-04-14` beta header when uploading via the global Files API. Managed Agents read access works under `managed-agents-2026-04-01` alone.

### Mount in a session at creation

```json
{
  "agent": "agent_01...",
  "environment_id": "env_01...",
  "resources": [
    {"type": "file", "file_id": "file_abc", "mount_path": "/workspace/data.csv"},
    {"type": "file", "file_id": "file_def", "mount_path": "/workspace/config.json"}
  ]
}
```

- Max **100 files per session**.
- Mounted files are **read-only copies**. Modifications must be written to new paths.
- Paths must be absolute (start with `/`). Parent dirs auto-created.

### Add/remove files mid-session

- `POST /v1/sessions/{id}/resources` — add (returns `sesrsc_01...`).
- `GET /v1/sessions/{id}/resources` — list mounts.
- `DELETE /v1/sessions/{id}/resources/{rid}` — unmount.

### Output files

The agent writes deliverables to `/mnt/session/outputs/`. Retrieve them:

```
GET /v1/files?scope_id=sesn_abc123
GET /v1/files/{id}/content
```

Session output files do **not** count against storage limits.

## 8. Memory stores (attach at session create)

Memory stores are independent workspace resources. You create them once, then attach to sessions. Full memory-side reference: [`memory.md`](memory.md). At build time you need:

```json
{
  "agent": "agent_01...",
  "environment_id": "env_01...",
  "resources": [
    {
      "type": "memory_store",
      "memory_store_id": "memstore_01...",
      "access": "read_write",
      "instructions": "User preferences and project context. Check before starting any task."
    }
  ]
}
```

- Up to **8 memory stores per session**.
- `access`: `read_write` (default) or `read_only`. Enforced at the filesystem layer.
- `instructions`: max 4,096 chars. Concatenated into the system prompt along with the store's `name` + `description`.
- Mounts under `/mnt/memory/<store-name>/`.
- **Cannot attach/detach memory mid-session.** Plan up front.

## 9. Vaults (attach at session create)

Full vault reference: [`vault.md`](vault.md). At build time:

```json
{
  "agent": "agent_01...",
  "environment_id": "env_01...",
  "vault_ids": ["vlt_01..."]
}
```

When multiple vaults match a server URL, **the first wins**. When no credential matches, the connection is attempted unauthenticated (so private servers fail with auth errors that surface as `session.error`).

## 10. Multiagent coordinator

```json
{
  "name": "Engineering Lead",
  "model": "claude-opus-4-7",
  "system": "You coordinate engineering work. Delegate code review to the reviewer agent and test writing to the test agent.",
  "tools": [{"type": "agent_toolset_20260401"}],
  "multiagent": {
    "type": "coordinator",
    "agents": [
      {"type": "agent", "id": "agent_01reviewer..."},
      {"type": "agent", "id": "agent_01tests..."},
      {"type": "agent", "id": "agent_01frontend...", "version": 3}
    ]
  }
}
```

Roster entries:
- `{"type": "agent", "id": "..."}` — latest version.
- `{"type": "agent", "id": "...", "version": N}` — pinned.
- `{"type": "self"}` — coordinator spawns copies of itself.

Hard caps:
- Max **20 unique** agents in the roster (multiplicity in *invocations* is fine).
- Max **25 concurrent threads** per session.
- Coordinator delegates **one level deep only.** Nested coordinators don't propagate.

### Thread architecture

All agents share the same container and filesystem. Each agent runs in its own *session thread* with isolated event stream and conversation history. The coordinator's activity is on the **primary thread**. Threads spawn on delegation and persist — the coordinator can send follow-ups to an agent it called earlier, and that agent retains everything from previous turns.

Tool confirmations and custom tool results for ANY thread are posted on the **primary session events endpoint**. The server routes by `tool_use_id` automatically.

## 11. Sanity checklist before you ship

- [ ] Beta header `managed-agents-2026-04-01` on every request (SDK does this).
- [ ] System prompt explicit about the agent's task and tool philosophy.
- [ ] If MCP servers used: vault created, credentials added, vault ID supplied at session create.
- [ ] If user input is untrusted and memory is attached: `access: "read_only"` unless you understand the prompt-injection risk.
- [ ] Tools that destroy data (bash, write, mcp_toolsets that mutate) on `always_ask` if the agent processes untrusted input.
- [ ] Environment networking is `limited` with explicit `allowed_hosts` in production.
- [ ] `metadata` carries enough to trace sessions back to your users/orgs.
- [ ] Pinned agent version in your session-create code if rollback matters.

When you've built it, move to [`test.md`](test.md) to actually drive a session.
