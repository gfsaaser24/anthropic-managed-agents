# Status / observability sub-mode

Use this reference when the user wants to **inspect** what an agent or session is doing: listing resources, polling status, reading event history, debugging failures, reading token usage, setting up webhooks, or using the Console.

## The two questions this sub-mode answers

1. **"What's the state of this session right now?"** → `GET /v1/sessions/{id}` (status, usage, stop_reason).
2. **"What happened?"** → `GET /v1/sessions/{id}/events` (full event history) or webhook-driven async.

## Session statuses (and what each means)

| Status | What's happening | What you do |
|---|---|---|
| `idle` | Agent is waiting for input — either a user message, a tool confirmation, or a custom-tool result. Sessions start here. | Inspect `stop_reason`. Send next event or leave it. |
| `running` | Agent is actively executing. | Stream events. Don't poll status — let SSE deliver. |
| `rescheduling` | Transient error; auto-retry in progress. | Wait. Optionally inspect `session.error` events. |
| `terminated` | Unrecoverable error or explicit archive. | Read final events. Session is read-only. |

**Idle is the resting state.** Creating a session leaves it `idle` until you send the first user event. After every burst of agent work, it returns to `idle` with a `stop_reason`.

### Stop reasons on `session.status_idle`

| `stop_reason.type` | Meaning |
|---|---|
| `end_turn` | Normal completion. Agent has nothing more to say. |
| `requires_action` | Blocked on user input. The payload includes `stop_reason.event_ids[]` listing the custom-tool calls or tool-confirmation requests you must respond to. |

## Inspecting an individual session

```
GET /v1/sessions/{id}
```

Returns:

```json
{
  "id": "sesn_01...",
  "type": "session",
  "status": "idle",
  "agent": {"id": "agent_01...", "version": 1},
  "environment_id": "env_01...",
  "title": "...",
  "usage": {
    "input_tokens": 5000,
    "output_tokens": 3200,
    "cache_creation_input_tokens": 2000,
    "cache_read_input_tokens": 20000
  },
  "outcome_evaluations": [],
  "created_at": "...",
  "updated_at": "...",
  "archived_at": null
}
```

`usage` aggregates across all model calls in the session. `cache_creation_input_tokens` / `cache_read_input_tokens` reflect prompt caching activity (5-minute TTL by default; 1-hour TTL is GA on the standard API).

## Listing sessions

```
GET /v1/sessions?status=running&limit=20
GET /v1/sessions?status=idle
GET /v1/sessions?status=terminated
```

Filter by status (available since May 6, 2026 release). Paginate via cursor returned in the response envelope.

## Reading event history

The full event log is queryable. This is the **authoritative source of truth** about what the agent did.

```
GET /v1/sessions/{id}/events
GET /v1/sessions/{id}/events?types[]=agent.tool_use&types[]=agent.tool_result
GET /v1/sessions/{id}/events?created_at[gte]=2026-04-01T00:00:00Z
```

Filters supported:
- `types[]=...` (repeatable) — restrict to one or more event types.
- `created_at[gte]=` / `created_at[lte]=` — time window.

Each event carries:
- `id` (`sevt_01...`)
- `type` (see taxonomy below)
- `created_at`, `processed_at` (latter is null while queued behind earlier events)
- Type-specific payload

### Full event taxonomy

#### User events (you send these)
| Type | Purpose |
|---|---|
| `user.message` | Text input to the agent. |
| `user.interrupt` | Stop the agent mid-execution. Optional `session_thread_id` for multiagent. |
| `user.custom_tool_result` | Respond to a `agent.custom_tool_use` call. |
| `user.tool_confirmation` | Approve/deny a pending agent or MCP tool call. |
| `user.define_outcome` | Define an outcome rubric (research preview). |

#### Agent events
| Type | Purpose |
|---|---|
| `agent.message` | Text content from the agent. |
| `agent.thinking` | Reasoning content (emitted separately when extended thinking is on). |
| `agent.tool_use` | Built-in agent tool invoked. |
| `agent.tool_result` | Built-in agent tool returned. |
| `agent.mcp_tool_use` | MCP server tool invoked. |
| `agent.mcp_tool_result` | MCP server tool returned. |
| `agent.custom_tool_use` | Your custom tool was called. You must respond. |
| `agent.thread_context_compacted` | Conversation history was compacted to fit the context window. Normal — no action required. |
| `agent.thread_message_received` | Multiagent: a sub-agent delivered its result to the coordinator. |
| `agent.thread_message_sent` | Multiagent: coordinator sent a follow-up to a sub-agent. |

#### Session events
| Type | Purpose |
|---|---|
| `session.status_running` | Agent began processing. |
| `session.status_idle` | Agent finished a turn. Carries `stop_reason`. |
| `session.status_rescheduled` | Transient error; auto-retry queued. |
| `session.status_terminated` | Session ended (terminal error or archive). |
| `session.error` | Error during processing. Includes typed `error` with `retry_status`. |
| `session.thread_created` | Multiagent: a sub-agent thread opened. |
| `session.thread_status_running` | Multiagent: sub-agent thread started work. |
| `session.thread_status_idle` | Multiagent: sub-agent thread idle. Carries `stop_reason`. |
| `session.thread_status_terminated` | Multiagent: sub-agent thread archived / terminal. |

#### Span events (observability)
| Type | Purpose |
|---|---|
| `span.model_request_start` | A model inference call started. |
| `span.model_request_end` | A model inference call completed. Includes `model_usage` (token counts). |
| `span.outcome_evaluation_start` | Outcome grader started. |
| `span.outcome_evaluation_ongoing` | Heartbeat during outcome grading. |
| `span.outcome_evaluation_end` | Outcome grader finished. Includes `result` and `explanation`. |

## Listing other resources

| Resource | Endpoint |
|---|---|
| Agents | `GET /v1/agents` |
| Agent versions | `GET /v1/agents/{id}/versions` |
| Environments | `GET /v1/environments` |
| Sessions | `GET /v1/sessions?status=...` |
| Memory stores | `GET /v1/memory_stores?include_archived=true` |
| Memory in a store | `GET /v1/memory_stores/{sid}/memories?path_prefix=/prefs&depth=2` |
| Memory versions | `GET /v1/memory_stores/{sid}/memory_versions?memory_id=...` |
| Vaults | `GET /v1/vaults` |
| Files in a session | `GET /v1/files?scope_id=sesn_...` |

## Rate limits to keep in mind

| Endpoint class | Limit |
|---|---|
| Create endpoints | 300 rpm/org |
| Read endpoints (retrieve, list, stream) | 600 rpm/org |

Combined with org-level token budgets and tier-based rate limits per `/docs/en/api/rate-limits`.

## Console view

`platform.claude.com` → workspace → **Claude Managed Agents** section.

- **Session list** — every session with status, creation time, model.
- **Tracing view** — chronological event view including content, timestamps, token usage. *Only Developers and Admins can see content.*
- **Tool execution** — per-tool call detail with inputs and results.

This is the fastest UI for "why did this go wrong" debugging. The API event log is the canonical source — Console renders it.

## Webhooks (async observability)

Register at `platform.claude.com/settings/workspaces/{ws}/webhooks`. Secret has prefix `whsec_` (shown once). Set env var `ANTHROPIC_WEBHOOK_SIGNING_KEY`.

### Payload shape (what the webhook receives)

```json
{
  "type": "event",
  "id": "event_01ABC...",
  "created_at": "2026-03-18T14:05:22Z",
  "data": {
    "type": "session.status_idled",
    "id": "sesn_01XYZ...",
    "organization_id": "...",
    "workspace_id": "..."
  }
}
```

The webhook carries only `type` + `id`. **Fetch the full object via GET after receipt.**

### Session event types delivered via webhook

| Event | Trigger |
|---|---|
| `session.status_run_started` | Every transition to `running`. |
| `session.status_idled` | Agent awaiting input. |
| `session.status_rescheduled` | Transient retry. |
| `session.status_terminated` | Terminal error or archive. |
| `session.thread_created` | New multiagent thread. |
| `session.thread_idled` | Multiagent agent awaiting input. |
| `session.thread_terminated` | Multiagent thread archived. |
| `session.outcome_evaluation_ended` | Outcome iteration completed. |

### Vault event types delivered via webhook

| Event |
|---|
| `vault.created` |
| `vault.archived` |
| `vault.deleted` |
| `vault_credential.created` |
| `vault_credential.archived` |
| `vault_credential.deleted` |
| `vault_credential.refresh_failed` |

### Verification rules

- Header `X-Webhook-Signature` must validate. Use SDK `unwrap()` helpers.
- Payloads older than **5 minutes** are rejected (replay protection).
- Endpoint must be HTTPS on port 443, publicly resolvable.
- **Ordering is not guaranteed.** Sort by `created_at` if you care about order.
- **At-least-once delivery.** Anthropic retries failures with the same `event.id` — de-dupe on that.
- 3xx redirects are treated as failure and not followed.
- Endpoint auto-disables after ~20 consecutive failures, or immediately for private IPs / redirects.

### Python verify pattern

```python
from anthropic import Anthropic
client = Anthropic()
event = client.beta.webhooks.unwrap(raw_body, headers={"x-webhook-signature": sig})
```

Throws on invalid signature or stale payload. Same shape in TS: `client.beta.webhooks.unwrap(rawBody, { headers })`.

## Debugging recipes

### Q: Session is stuck at `idle`. Why?

Check `stop_reason` on the most recent `session.status_idle` event:
- `end_turn` → it's done; you need to send a new `user.message` to continue.
- `requires_action` → look at `stop_reason.event_ids[]` and respond to each blocked tool call.

### Q: I never see the first event after creating a session.

You opened the stream **after** sending the first user event. Open the stream first, then send. To resume mid-flight: open new stream → `GET /v1/sessions/{id}/events` → seed `seen_event_ids` → tail and skip seen IDs.

### Q: `session.error` keeps firing. How do I find the root cause?

The event payload contains a typed `error` with `retry_status`. Common causes:
- MCP server auth failure (invalid vault credential) — fix the credential and re-trigger.
- Network reach to a non-allowed host in `limited` networking mode — update `allowed_hosts`.
- Container OOM (>8 GB) — split the workload or stream data.
- Disk full (>10 GB) — clean up `/tmp` or write to `/mnt/session/outputs/`.

### Q: Why did my agent's tokens spike?

`session.usage` aggregates across the whole session. Inspect `span.model_request_end` events to see per-request token counts. Common offenders:
- Large file mounts pulled into context.
- Long-lived sessions where conversation history compounds (watch for `agent.thread_context_compacted` events — those mean it hit the ceiling).
- Many MCP calls returning verbose results.

### Q: Session shows `terminated` but I didn't archive it.

Read the final `session.error` event. If the agent encountered an unrecoverable error (e.g., persistent OOM, terminal vault failure), the session terminates automatically.

## Cost monitoring

`$0.08 per session-hour` accrues only while session status is `running`. Idle is free. To estimate cost:

```python
runtime_hours = sum(
    (e.processed_at - prev.processed_at).total_seconds() / 3600
    for prev, e in pairs(running_to_idle_transitions)
)
session_cost = 0.08 * runtime_hours + token_cost(usage)
```

If you want hard caps: register a webhook on `session.status_run_started`, start a wall-clock timer per session, and send `user.interrupt` + archive when you hit your budget.

## Archive vs delete

| Op | Endpoint | Effect |
|---|---|---|
| Archive session | `POST /v1/sessions/{id}/archive` | Preserves history. New events blocked. |
| Delete session | `DELETE /v1/sessions/{id}` | Hard delete. **`running` sessions cannot be deleted — interrupt first.** Independent resources (files, memory stores, vaults, skills, environments, agents) are NOT affected. |
| Archive agent | `POST /v1/agents/{id}/archive` | New sessions blocked. Existing sessions continue. |
| Archive environment | `POST /v1/environments/{id}/archive` | Existing sessions continue. |
| Delete environment | `DELETE /v1/environments/{id}` | Only if no sessions reference it. |

## Retention

| Thing | Retained |
|---|---|
| Session conversation history | Until you delete the session. |
| Container checkpoint (filesystem state, installed packages) | **30 days after last activity.** Send a no-op `user.message` to reset the inactivity timer. |
| Memory versions | 30 days, but recent versions are always kept regardless of age. |
| Webhook signing secret | One-time view at creation. |

When a workflow needs container state beyond 30 days, persist outputs to memory stores or files and resurrect a fresh session against them.
