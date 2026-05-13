# Limits, pricing, and gotchas

## Pricing model

Managed Agents bills on two axes, on top of standard Claude API token rates:

| Axis | Rate |
|---|---|
| **Tokens** | Standard Claude API rates. No Managed Agents markup. Example: Opus 4.6/4.7 = $5/MTok input, $25/MTok output. |
| **Session runtime** | **$0.08 per session-hour.** Measured to the millisecond. Accrues only while session status is `running`. Idle and queued time is free. |
| **Web search tool** | $10 per 1,000 searches (same as standard API tool pricing). |
| **Code execution container** | **Included** in the $0.08/session-hour. |
| **Infrastructure provisioning, checkpointing, retry** | **Included.** |

### Worked example (Anthropic-published)

> "A one-hour coding session using Claude Opus 4.6 consuming 50,000 input tokens and 15,000 output tokens costs ~$0.705 total. The session runtime is $0.08 out of $0.705 — just 11% of the cost."

So at typical agent-workload token mixes, the session-hour charge is a small fraction of total cost. The implication: **don't optimize for session runtime first. Optimize for token spend first.** Prompt caching helps materially here.

### Prompt caching

Cache reads cost ~10% of input. 5-minute TTL by default; 1-hour cache TTL is GA on the standard API. Cache writes/reads appear on `session.usage`:

```json
"usage": {
  "input_tokens": 5000,
  "output_tokens": 3200,
  "cache_creation_input_tokens": 2000,
  "cache_read_input_tokens": 20000
}
```

The harness manages caching automatically — you can't force or disable it.

### Cost control patterns

- **Bound session runtime.** Wall-clock timer in your orchestrator; `user.interrupt` + delete on timeout.
- **Pin model version** to the cheapest Claude that meets quality.
- **`max_iterations` on outcomes** caps the rubric-loop spend.
- **Webhook on `session.status_run_started`** + poll `usage` to abort sessions exceeding token budget.
- **Idle aggressively.** A session that finishes its turn and goes idle costs $0 until the next event.

### Beta caveat

All rates above are beta-era. Subject to change before GA. Cite `/docs/en/about-claude/pricing` if a user needs the live number.

## Rate limits

| Endpoint class | Limit |
|---|---|
| Create endpoints (agents, sessions, environments, memory_stores, vaults, etc.) | **300 requests/minute/org** |
| Read endpoints (retrieve, list, stream) | **600 requests/minute/org** |

Plus org-level token budgets and tier-based standard API rate limits per `/docs/en/api/rate-limits`.

## Hard limits

### Per session

| Thing | Limit |
|---|---|
| Skills (across all agents in a multiagent session) | **20** |
| Files (mounted via `resources`) | **100** |
| Memory stores | **8** |
| Concurrent threads (multiagent) | **25** |

### Per memory store

| Thing | Limit |
|---|---|
| Bytes per memory | **100 kB** (~25k tokens) |
| `instructions` length | **4,096 characters** |
| Version retention | **30 days** (recent versions always kept regardless of age) |

### Per agent

| Thing | Limit |
|---|---|
| MCP servers | **20** |
| Multiagent coordinator roster (unique agents) | **20** |
| Multiagent delegation depth | **1** (deeper is silently flattened) |

### Per vault

| Thing | Limit |
|---|---|
| Credentials | **20** |
| Active credential per `mcp_server_url` | **1** |

### Container

| Thing | Limit |
|---|---|
| RAM | **8 GB** |
| Disk | **10 GB** |
| OS | Ubuntu 22.04 LTS x86_64 (fixed) |
| Checkpoint retention after last activity | **30 days** |

### Outcomes

| Thing | Default | Max |
|---|---|---|
| `max_iterations` | 3 | **20** |
| Concurrent outcomes on a session | 1 (chain via `user.define_outcome` after terminal event) | |

### Webhooks

| Thing | Value |
|---|---|
| Payload max age before rejection | **5 minutes** |
| Endpoint transport | HTTPS port 443 |
| Auto-disable threshold | ~20 consecutive failures (immediate for private IPs / redirects) |
| Redirects (3xx) | Treated as failure |
| Delivery | At-least-once, ordering not guaranteed |

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| 400 on every request | Missing `anthropic-beta: managed-agents-2026-04-01` header | Add it, or use `client.beta.*` methods |
| 409 on agent update | Stale `version` in request body | GET agent, retry with current version |
| 409 on credential create | Existing credential for same `mcp_server_url` | Archive the old one or update via the credential update endpoint |
| Session stays `idle`, never advances | Forgot to send first user event after create | POST `user.message` |
| Stream delivers nothing | Stream opened *after* first event sent | Always open stream first |
| MCP tool calls fail with auth errors | Vault not attached or credential invalid | Validate via `mcp_oauth_validate?beta=true`; re-attach correct vault_ids |
| Network requests in container fail | Environment is `limited` networking; host not in `allowed_hosts` | Add the host, or switch to `unrestricted` (dev only) |
| Container OOM (>8 GB) | Loading large data into memory | Stream from disk; downsample; split work |
| Disk full (>10 GB) | Logs/output piling up | Write to `/mnt/session/outputs/` (counts separately) or clean `/tmp` |
| Memory write silently rejected | Memory mounted `read_only` | Switch to `read_write` if you trust input; otherwise add an unguarded writable store |
| Session deleted unexpectedly | 30-day inactivity expired checkpoint | Send a no-op `user.message` periodically to reset the timer |
| Webhook calls 401 | Bad signature or stale (>5 min) payload | Check `ANTHROPIC_WEBHOOK_SIGNING_KEY`, verify clock sync |

## Anthropic-managed vs Claude Agent SDK

| Aspect | Messages API | Claude Agent SDK | Managed Agents |
|---|---|---|---|
| Who runs the loop | You | You (with SDK helpers) | Anthropic |
| Sandbox for tool execution | None (BYO) | None (BYO) | Anthropic container |
| State persistence | None | None | Built-in (sessions, memory, files) |
| Multiagent fan-out | DIY | DIY | Built-in coordinator |
| Best for | Single-turn / short multi-turn | Custom loops, you own infra | Long autonomous tasks |
| Billing | Tokens only | Tokens only | Tokens + $0.08/session-hour |

There is **no self-hosted Managed Agents**. The closest alternative is **Claude Platform on AWS** (launched May 11, 2026), where the *billing* and *auth* layer is AWS (SigV4 / IAM) but Anthropic still operates the inference and harness infrastructure. Unlike Bedrock, AWS does not run the inference stack. Data may not reside in AWS — inference may route to Anthropic's primary cloud. ZDR (zero data retention) is available on request.

## Memory & prompt-injection risk

`read_write` memory + untrusted user input is a known prompt-injection vector. A malicious user prompt can instruct the agent to write attacker-controlled content into memory; future sessions then read that content as trusted memory store content.

**Mitigations:**
- Default `read_only` for reference material.
- Use separate memory stores per trust boundary (user A's memory ≠ user B's).
- Audit version diffs periodically.
- Redact problematic versions (write a clean head first; redacting the current head is blocked).

## Vault scoping

Vaults are workspace-scoped — there is no per-user ACL. Anyone with an API key for the workspace can reference any vault. Build per-user routing in your own layer:

- Set `vault.metadata.external_user_id` to your user ID at create time.
- Look up the right vault for the requesting user before calling `sessions.create`.
- Treat the workspace API key as fully privileged; rotate immediately if compromised.

## Feature gates (research preview)

These features require requesting access via `https://claude.com/form/claude-managed-agents`:

- **Outcomes** (`user.define_outcome`, `span.outcome_evaluation_*`).
- **Multiagent sessions**.

Even after May 6, 2026 GA wording, the overview lists these as research preview. Plan for an access request if you need either.

## Data residency

- Default API region: Anthropic's primary cloud.
- **Claude Platform on AWS** provides AWS IAM/billing but still runs on Anthropic infrastructure. Data may not reside in AWS.
- ZDR (Zero Data Retention) is available on request on Claude Platform on AWS, same retention defaults as first-party API otherwise.

## What's NOT in the Managed Agents docs (as of May 2026)

A few capabilities show up in third-party blog posts but are not officially documented yet:

- **Dreaming** — references suggest an agent self-improvement loop that reviews past sessions to find patterns. Treat as forward-looking; no endpoint yet.
- **Per-user vault ACLs** — repeatedly requested in forums; not yet shipped.

When a user asks about these, point them at the form for early-access programs and check release notes for the latest status.

## Release-notes timeline

| Date | What shipped |
|---|---|
| 2026-04-08 | Managed Agents public beta. `ant` CLI. Beta header `managed-agents-2026-04-01`. |
| 2026-04-23 | Memory for Managed Agents public beta (same header). |
| 2026-05-06 | Multiagent sessions, Outcomes, vault background credential refresh, webhooks for session/vault lifecycle. Session/event filtering (status, type, created_at). |
| 2026-05-11 | Claude Platform on AWS launched. Managed Agents available with AWS billing + IAM auth. |
| 2026-05-12 | Fast mode for Opus 4.7 (`speed: "fast"`, `fast-mode-2026-02-01` beta). |

Check `/docs/en/release-notes/overview` for the latest.
