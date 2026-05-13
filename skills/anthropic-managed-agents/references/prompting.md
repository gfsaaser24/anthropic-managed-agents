# Prompting and tool design

This reference covers the **system prompt**, **tool design**, **permission policies**, **MCP design**, and **multiagent coordinator** patterns. For raw endpoint shapes, see [`build.md`](build.md).

## System prompt

The `system` field on the agent defines the agent's behavior and persona. It is **distinct from user messages** — user messages describe the work to be done; the system prompt describes how the agent should behave across all interactions.

### What goes in the system prompt

- Role and capabilities ("You are a financial analyst agent.")
- Output style ("Be terse. Use markdown tables for comparisons.")
- Tool philosophy ("Use `bash` aggressively to explore the filesystem before answering.")
- Safety rails ("Never delete files outside `/workspace`.")
- Memory store contract — the system prompt is auto-augmented with each attached store's `name`, `description`, and `instructions`, but you should also explicitly tell the agent to consult memory at the start of each task.
- Hard rules ("Always include unit tests for any code you write.")

### What does NOT belong in the system prompt

- Per-task input — that goes in `user.message`.
- Secrets — use vaults.
- Reference material >1k tokens — put it in a memory store or a file.

### System prompt can be cleared, but not removed

Pass `null` on update to clear. The field defaults to an empty string if you create an agent without one — but a no-op system prompt produces a generic Claude, which is rarely what you want.

## Tool design

Three flavors:

| Type | Who executes | When to use |
|---|---|---|
| `agent_toolset_20260401` | Anthropic-managed container | File I/O, shell, web fetch/search — the universal default. |
| `mcp_toolset` | The MCP server (third-party or yours) | Standardized integrations (GitHub, Slack, Linear, your own MCP servers). |
| `custom` | Your client | When the tool needs to run in your process, not Anthropic's. |

### Built-in toolset (`agent_toolset_20260401`)

| Tool | Use |
|---|---|
| `bash` | Run shell commands. Long-running by default. |
| `read` | Read files. |
| `write` | Write files (overwrite). |
| `edit` | String replacement in a file. |
| `glob` | File pattern matching. |
| `grep` | Regex search. |
| `web_fetch` | Fetch a URL. |
| `web_search` | Search the web. |

All enabled by default. To selectively disable:

```json
{
  "type": "agent_toolset_20260401",
  "configs": [{"name": "web_fetch", "enabled": false}]
}
```

Allow-list style (start all disabled, enable explicit):

```json
{
  "type": "agent_toolset_20260401",
  "default_config": {"enabled": false},
  "configs": [
    {"name": "bash", "enabled": true},
    {"name": "read", "enabled": true}
  ]
}
```

### Custom tools

```json
{
  "type": "custom",
  "name": "get_weather",
  "description": "Get current weather for a location. Returns temperature in Celsius and conditions. Use this whenever the user asks about weather, temperature, or outdoor conditions.",
  "input_schema": {
    "type": "object",
    "properties": {"location": {"type": "string", "description": "City name"}},
    "required": ["location"]
  }
}
```

### Best practices (verbatim from Anthropic)

> "Write detailed descriptions (3-4 sentences minimum). Vague descriptions hurt tool selection — the model has to guess from the name alone."

> "Consolidate related operations with an `action` parameter rather than 12 tiny tools. The agent picks tools by name; fewer names with richer parameters is easier to disambiguate."

> "Namespace tool names (`db_query`, `storage_read`). Plain names like `get` or `list` collide when you scale up."

> "Return high-signal, semantic identifiers; avoid bloated responses. The tool result goes back into the agent's context — long results cost tokens and crowd out reasoning room."

## Permission policies

| Policy | Behavior |
|---|---|
| `always_allow` | Auto-execute. Default for `agent_toolset_20260401`. |
| `always_ask` | Pauses the session with `stop_reason: requires_action`. You respond via `user.tool_confirmation`. Default for `mcp_toolset`. |

Apply at toolset level or per-tool:

```json
{
  "type": "agent_toolset_20260401",
  "default_config": {"permission_policy": {"type": "always_allow"}},
  "configs": [
    {"name": "bash", "permission_policy": {"type": "always_ask"}}
  ]
}
```

**Permission policies do not apply to custom tools.** Your client is the executor and always sees the call.

### When to require confirmation

- Destructive shell commands (`rm`, `git push --force`, DB writes).
- MCP tools that mutate external state (creating issues, sending Slack messages, charging payments).
- Anything that touches money, prod data, or external humans.

When the agent processes **untrusted user input**, default-deny is safer: set `default_config.permission_policy` to `always_ask` and selectively `always_allow` only the read-only tools.

## MCP server design

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

The MCP server must:
- Be a remote HTTP endpoint reachable from Anthropic's network.
- Support the MCP **streamable HTTP transport**.
- Authenticate via OAuth (provide a credential of type `mcp_oauth`) or bearer (provide `static_bearer`) in a vault attached at session create.

Max **20 MCP servers per agent**.

## Multiagent coordinator patterns

Two design philosophies:

### A. Roles-based fan-out

The coordinator delegates by role. Each sub-agent is a specialist.

```json
{
  "name": "Engineering Lead",
  "system": "You coordinate engineering work. For code review: delegate to `code-reviewer`. For tests: delegate to `test-writer`. For frontend: delegate to `frontend-dev`. Synthesize their outputs into a single PR plan.",
  "multiagent": {
    "type": "coordinator",
    "agents": [
      {"type": "agent", "id": "agent_reviewer_01..."},
      {"type": "agent", "id": "agent_tests_01..."},
      {"type": "agent", "id": "agent_frontend_01..."}
    ]
  }
}
```

Good when: tasks fall cleanly into specialties; each sub-agent has a distinct system prompt.

### B. Self-fan-out (parallel workers)

The coordinator spawns copies of itself to parallelize work.

```json
{
  "name": "Researcher",
  "system": "You research topics. If the user asks about N distinct things, spawn N copies of yourself, each researching one, and synthesize.",
  "multiagent": {"type": "coordinator", "agents": [{"type": "self"}]}
}
```

Good when: the work is embarrassingly parallel; one prompt suffices for all workers.

### Shared filesystem, isolated threads

All agents in a multiagent session **share the same container filesystem**. Each agent runs in its own **session thread** with isolated event stream and conversation history. This means:

- Coordinator writes a plan to `/workspace/plan.md`; sub-agents read it.
- Sub-agent writes a result to `/workspace/results/reviewer.md`; coordinator reads it.
- Sub-agents do NOT see each other's events. Only the coordinator does.

### Threads persist

The coordinator can send a follow-up to a sub-agent it called earlier, and that sub-agent retains everything from its previous turns. Useful for iterative refinement loops where the coordinator critiques and the sub-agent revises.

### Limits

- **20 unique agents** in the coordinator roster (multiplicity in *invocations* is fine — the coordinator can call the same sub-agent 50 times).
- **25 concurrent threads** per session.
- Coordinator delegates **one level only.** Nested coordinators are flattened — depth >1 is ignored.

### Tool confirmation routing

When any thread's tool requires confirmation, the agent emits `agent.tool_use` and `session.thread_status_idle` with `stop_reason: requires_action`. **You post `user.tool_confirmation` on the primary session events endpoint**, not on the thread's events endpoint — the server routes by `tool_use_id`.

## Prompt caching

The Managed Agents harness uses prompt caching aggressively. Cache reads/writes are reflected on `session.usage`:

```json
"usage": {
  "input_tokens": 5000,
  "output_tokens": 3200,
  "cache_creation_input_tokens": 2000,
  "cache_read_input_tokens": 20000
}
```

Default TTL is 5 minutes; 1-hour cache TTL is GA on the standard API. You don't manually control caching for Managed Agents — the harness decides.

## Compaction

When conversation history exceeds the context window, the harness compacts it and emits `agent.thread_context_compacted`. This is automatic and lossless to the agent's *immediate* working memory (it can still reason about recent turns) but older history is summarized. For workloads where full history matters, persist key facts to a memory store rather than relying on the rolling conversation.

## Extended thinking

When the model supports extended thinking, the agent emits `agent.thinking` events separately from `agent.message`. You typically don't act on thinking — it's there for observability. The Console renders it in the tracing view (Developers/Admins only).
