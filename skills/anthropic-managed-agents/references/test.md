# Test sub-mode — running and evaluating a Managed Agent

Use this reference when the user wants to **drive** a Managed Agent: create a session, send events, stream SSE, handle custom-tool round trips, run outcome/rubric evaluations, or set up test harnesses.

If the agent doesn't exist yet, see [`build.md`](build.md). If you need to inspect what happened during a run, see [`status.md`](status.md).

## The three things this sub-mode answers

1. How do I start a session and feed it work?
2. How do I respond when the agent calls a custom tool or asks permission?
3. How do I evaluate whether the agent did the right thing?

## 1. Start the session

```
POST /v1/sessions
```

```json
{
  "agent": "agent_01...",
  "environment_id": "env_01...",
  "title": "Smoke test — Q1 finance"
}
```

Optional fields:
- `agent` as an object pins a version: `{"type": "agent", "id": "agent_01...", "version": 2}`. **Do this in tests** so a teammate updating the agent doesn't invalidate your fixtures.
- `vault_ids: ["vlt_01..."]` — credentials for MCP servers.
- `resources: [...]` — files and memory stores to mount.

A freshly created session is `idle` and the container is provisioned but **no work has started.** Don't expect the SSE stream to deliver anything until you send the first user event.

## 2. Open the SSE stream BEFORE sending the first event

This is the single most common bug. The stream only delivers events emitted **after** it's opened.

```bash
# Terminal 1: open the stream FIRST
curl -N https://api.anthropic.com/v1/sessions/sesn_01.../events/stream \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01"
```

```bash
# Terminal 2: NOW send the user event
curl https://api.anthropic.com/v1/sessions/sesn_01.../events \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: managed-agents-2026-04-01" \
  -H "content-type: application/json" \
  -d '{"events": [{"type": "user.message", "content": [{"type": "text", "text": "Analyze utils.py performance."}]}]}'
```

### Resume / reconnect protocol

If your stream drops mid-session, you cannot get redelivery. Recovery:

1. Open a new stream.
2. `GET /v1/sessions/{id}/events?created_at[gte]=<last_known_processed_at>` to seed a `seen_event_ids` set.
3. Tail the live stream, skipping any IDs already in `seen_event_ids`.

The "open stream first, then list to backfill" order matters: if you list first then open, events arriving in between are lost.

## 3. Drive the agent with user events

### Send a message

```json
POST /v1/sessions/{id}/events
{
  "events": [{
    "type": "user.message",
    "content": [{"type": "text", "text": "Analyze the performance of the sort function in utils.py"}]
  }]
}
```

You can batch multiple events in one request:

```json
{
  "events": [
    {"type": "user.message", "content": [{"type": "text", "text": "First step:..."}]},
    {"type": "user.message", "content": [{"type": "text", "text": "Then..."}]}
  ]
}
```

### Interrupt and redirect mid-execution

```json
{
  "events": [
    {"type": "user.interrupt"},
    {"type": "user.message", "content": [{"type": "text", "text": "Instead, focus on fixing the bug in line 42."}]}
  ]
}
```

Use `user.interrupt` to:
- Stop a runaway agent.
- Redirect when you change your mind.
- Bound runtime (when combined with a wall-clock timer, this is how you cap session-hour spend).

In multiagent sessions, you can interrupt a specific thread:

```json
{"events": [{"type": "user.interrupt", "session_thread_id": "sth_01..."}]}
```

## 4. Custom tool round-trip (you execute, agent waits)

When the agent calls a custom tool you declared on the agent, the session pauses with `requires_action`. This is a synchronous handshake:

```
agent.custom_tool_use            — agent emits, with input
session.status_idle              — stop_reason: requires_action, event_ids: [...]
                                   (session is paused, no $0.08/hr accruing)
user.custom_tool_result          — you POST per blocked tool_use_id
session.status_running           — agent resumes
agent.message                    — agent continues
```

### What the agent emits

```json
{
  "type": "agent.custom_tool_use",
  "id": "sevt_01...",
  "tool_use_id": "toolu_01ABC...",
  "name": "get_weather",
  "input": {"location": "Seattle"}
}
```

### What you respond with

```json
POST /v1/sessions/{id}/events
{
  "events": [{
    "type": "user.custom_tool_result",
    "custom_tool_use_id": "toolu_01ABC...",
    "content": [{"type": "text", "text": "{\"temp\": 12, \"conditions\": \"rain\"}"}]
  }]
}
```

Match by `tool_use_id`. If the agent issued multiple custom tool calls in parallel, the `stop_reason.event_ids[]` array enumerates them and you must respond to each.

## 5. Tool confirmation round-trip (MCP / agent tools with `always_ask`)

When a tool has `permission_policy: always_ask`, the agent pauses for explicit user approval:

```json
{"type": "user.tool_confirmation", "tool_use_id": "toolu_01ABC...", "result": "allow"}
{"type": "user.tool_confirmation", "tool_use_id": "toolu_01ABC...", "result": "deny", "deny_message": "Don't create issues in the production project. Use the staging project."}
```

`deny_message` is fed back to the agent so it can adapt. In multiagent, post on the **primary session events endpoint** — the server routes by `tool_use_id` to the correct thread.

## 6. Outcomes / rubrics (research preview testing harness)

This is Anthropic's recommended evaluation pattern. Define a rubric, the system spawns a grader in a separate context, and the loop iterates until satisfied or `max_iterations` reached.

### Define an outcome

```json
POST /v1/sessions/{id}/events
{
  "events": [{
    "type": "user.define_outcome",
    "description": "Build a DCF model for Costco in .xlsx",
    "rubric": {"type": "text", "content": "# DCF Model Rubric\n\n- The output is a single .xlsx file\n- Includes columns for Revenue, COGS, Operating Income, FCF\n- Discount rate is between 7% and 10%\n- Terminal value uses Gordon Growth\n- All numbers are formulas, not hardcoded\n"},
    "max_iterations": 5
  }]
}
```

Or use a file as the rubric:

```json
{"rubric": {"type": "file", "file_id": "file_01..."}}
```

`max_iterations` defaults to **3**, max is **20**.

### What the grader emits

```
span.outcome_evaluation_start         — iteration N begins
span.outcome_evaluation_ongoing       — heartbeat (grader reasoning is opaque)
span.outcome_evaluation_end           — verdict
```

Verdicts in `span.outcome_evaluation_end.result`:

| Result | What happens next |
|---|---|
| `satisfied` | Session → `idle`. Done. |
| `needs_revision` | Agent starts another iteration. |
| `max_iterations_reached` | Final agent revision may run, then idle. |
| `failed` | Rubric fundamentally doesn't fit the task. |
| `interrupted` | Only if `outcome_evaluation_start` already fired before an interrupt. |

The end event payload also carries `outcome_evaluation_start_id`, `outcome_id`, `explanation`, `iteration`, and `usage`.

### Chain outcomes

> "Only one outcome supported at a time, but you may chain together outcomes in sequence. To do this, send a new `user.define_outcome` event after the terminal event of the previous outcome."

### Rubric-writing tips (verbatim)

> "Structure the rubric as explicit, gradeable criteria, such as 'The CSV contains a price column with numeric values' rather than 'The data looks good.'"

> "If you don't have a rubric on hand, try giving Claude an example of a known-good artifact and asking it to analyze what makes that content good, then turn that analysis into a rubric."

## 7. Multiagent testing

The primary stream sees everything in the coordinator. Sub-agent activity also shows up via thread events:

```
session.thread_created             — { session_thread_id, agent_name }
session.thread_status_running      — sub-agent started
agent.thread_message_sent          — coordinator sent input to sub-agent
agent.thread_message_received      — sub-agent delivered output
session.thread_status_idle         — sub-agent idle (with stop_reason)
session.thread_status_terminated   — sub-agent thread archived
```

You can also subscribe to a single thread:

```
GET /v1/sessions/{id}/threads
GET /v1/sessions/{id}/threads/{tid}/events
GET /v1/sessions/{id}/threads/{tid}/stream
POST /v1/sessions/{id}/threads/{tid}/archive
```

Tool confirmations for sub-agents post on the **primary** events endpoint with the sub-agent's `tool_use_id`. The server routes.

## 8. Test-harness patterns

### Pattern A — fixture session per test

```python
import anthropic
client = anthropic.Anthropic()

# Pin version so unrelated agent updates don't invalidate fixtures
session = client.beta.sessions.create(
    agent={"type": "agent", "id": AGENT_ID, "version": 3},
    environment_id=ENV_ID,
    title=f"test:{test_name}",
    resources=[{"type": "file", "file_id": FIXTURE_FILE_ID, "mount_path": "/workspace/input.csv"}],
)

# Open stream BEFORE sending first event
with client.beta.sessions.events.stream(session.id) as stream:
    client.beta.sessions.events.send(session.id, events=[
        {"type": "user.message", "content": [{"type": "text", "text": prompt}]}
    ])
    for event in stream:
        if event.type == "session.status_idle" and event.stop_reason.type == "end_turn":
            break
        # ...handle custom tools, tool confirmations
```

After the test, `DELETE /v1/sessions/{id}` to keep the workspace tidy. Files/memory/vault are untouched.

### Pattern B — outcome-driven CI

Wrap the rubric loop in your CI. Pass criteria for each test in a markdown rubric. Exit 0 on `satisfied`, exit 1 on anything else, capture the grader's `explanation` for the failure message.

### Pattern C — replay traffic

Use the event-list endpoint to capture a real session's events, then use those user events as test fixtures by replaying them against a fresh session.

```python
events = client.beta.sessions.events.list(real_session_id, types=["user.message", "user.custom_tool_result"])
new_session = client.beta.sessions.create(...)
client.beta.sessions.events.send(new_session.id, events=[e.to_send_shape() for e in events])
```

### Pattern D — webhook-driven evaluation

For long-running tests, register a webhook on `session.status_idled` and have the webhook handler check the session's outputs. This avoids holding open SSE streams or polling.

## 9. What "done" looks like

Wait for `session.status_idle` with `stop_reason.type == "end_turn"`. That's the only signal that the agent has nothing more to say. Anything else (`requires_action`, an outcome `needs_revision`) means more work pending.

## 10. Cleanup

```
POST /v1/sessions/{id}/archive   # keeps history, blocks new events
DELETE /v1/sessions/{id}          # hard delete; cannot delete `running` sessions
```

**Always cap test session runtime.** A stuck test session bills $0.08/hr indefinitely. Patterns:

- Wall-clock timer in the test runner — `user.interrupt` + delete on timeout.
- `max_iterations` on outcomes — bounded by definition.
- Pre-test budget gate: query `usage` periodically and abort when token spend exceeds your budget.

## 11. Quick smoke test (60 seconds)

```bash
export ANTHROPIC_API_KEY=...
export BETA="anthropic-beta: managed-agents-2026-04-01"
export V="anthropic-version: 2023-06-01"
export H="x-api-key: $ANTHROPIC_API_KEY"

AGENT=$(curl -s https://api.anthropic.com/v1/agents -H "$H" -H "$V" -H "$BETA" -H "content-type: application/json" \
  -d '{"name":"smoke","model":"claude-opus-4-7","system":"Be terse.","tools":[{"type":"agent_toolset_20260401"}]}' | jq -r .id)

ENV=$(curl -s https://api.anthropic.com/v1/environments -H "$H" -H "$V" -H "$BETA" -H "content-type: application/json" \
  -d '{"name":"smoke-env","config":{"type":"cloud","networking":{"type":"unrestricted"}}}' | jq -r .id)

SESN=$(curl -s https://api.anthropic.com/v1/sessions -H "$H" -H "$V" -H "$BETA" -H "content-type: application/json" \
  -d "{\"agent\":\"$AGENT\",\"environment_id\":\"$ENV\"}" | jq -r .id)

# stream in background, then send
curl -N -s https://api.anthropic.com/v1/sessions/$SESN/events/stream -H "$H" -H "$V" -H "$BETA" &
SLEEP_PID=$!
sleep 1

curl -s https://api.anthropic.com/v1/sessions/$SESN/events -H "$H" -H "$V" -H "$BETA" -H "content-type: application/json" \
  -d '{"events":[{"type":"user.message","content":[{"type":"text","text":"echo hello via bash"}]}]}'
```

You should see `session.status_running` → `agent.tool_use` (bash) → `agent.tool_result` → `agent.message` → `session.status_idle (end_turn)` within 30 seconds.

If you don't: most likely the beta header is missing or the model is one that doesn't support Managed Agents (must be Claude 4.5+).
