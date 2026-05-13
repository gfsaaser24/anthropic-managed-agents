# Python SDK — Managed Agents

The official `anthropic` Python SDK ships with full Managed Agents support under `client.beta.*`. The beta header is added automatically.

```bash
pip install -U anthropic
```

```python
import anthropic
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY env var
```

## Method tree

```python
# Agents
client.beta.agents.create(name, model, system=..., tools=..., mcp_servers=..., skills=..., multiagent=..., metadata=...)
client.beta.agents.retrieve(agent_id)
client.beta.agents.list(limit=..., after=...)
client.beta.agents.update(agent_id, version=..., system=..., tools=..., ...)
client.beta.agents.archive(agent_id)
client.beta.agents.versions.list(agent_id)

# Environments
client.beta.environments.create(name, config={...})
client.beta.environments.retrieve(env_id)
client.beta.environments.list()
client.beta.environments.archive(env_id)
client.beta.environments.delete(env_id)

# Sessions
client.beta.sessions.create(agent=..., environment_id=..., title=..., vault_ids=..., resources=...)
client.beta.sessions.retrieve(session_id)
client.beta.sessions.list(status=..., limit=...)
client.beta.sessions.archive(session_id)
client.beta.sessions.delete(session_id)

# Session events
client.beta.sessions.events.send(session_id, events=[...])
client.beta.sessions.events.list(session_id, types=[...], created_at_gte=...)
client.beta.sessions.events.stream(session_id)  # returns context manager / async iterator

# Session resources (add/remove files mid-session)
client.beta.sessions.resources.add(session_id, type="file", file_id=..., mount_path=...)
client.beta.sessions.resources.list(session_id)
client.beta.sessions.resources.delete(session_id, resource_id)

# Session threads (multiagent)
client.beta.sessions.threads.list(session_id)
client.beta.sessions.threads.archive(session_id, thread_id)
client.beta.sessions.threads.events.list(session_id, thread_id, types=[...])
client.beta.sessions.threads.events.stream_events(session_id, thread_id)

# Memory stores
client.beta.memory_stores.create(name=..., description=...)
client.beta.memory_stores.retrieve(store_id)
client.beta.memory_stores.update(store_id, name=..., description=...)
client.beta.memory_stores.list(include_archived=False)
client.beta.memory_stores.archive(store_id)
client.beta.memory_stores.delete(store_id)

# Memories within a store
client.beta.memory_stores.memories.create(store_id, path=..., content=...)
client.beta.memory_stores.memories.retrieve(store_id, memory_id)
client.beta.memory_stores.memories.update(store_id, memory_id, content=..., precondition=...)
client.beta.memory_stores.memories.list(store_id, path_prefix=..., depth=..., order_by=...)
client.beta.memory_stores.memories.delete(store_id, memory_id)

# Memory versions
client.beta.memory_stores.memory_versions.list(store_id, memory_id=...)
client.beta.memory_stores.memory_versions.retrieve(store_id, version_id)
client.beta.memory_stores.memory_versions.redact(store_id, version_id)

# Vaults
client.beta.vaults.create(display_name=..., metadata=...)
client.beta.vaults.retrieve(vault_id)
client.beta.vaults.list()
client.beta.vaults.archive(vault_id)
client.beta.vaults.delete(vault_id)

# Vault credentials
client.beta.vaults.credentials.create(vault_id, display_name=..., auth={...})
client.beta.vaults.credentials.update(vault_id, cred_id, auth={...})
client.beta.vaults.credentials.archive(vault_id, cred_id)
client.beta.vaults.credentials.delete(vault_id, cred_id)

# Files
client.beta.files.upload(file=open("data.csv", "rb"))
client.beta.files.list(scope_id=...)
client.beta.files.download(file_id)

# Webhooks
client.beta.webhooks.unwrap(raw_body, headers={"x-webhook-signature": sig})
```

## End-to-end example

```python
import anthropic

client = anthropic.Anthropic()

# 1. Define agent
agent = client.beta.agents.create(
    name="Data Analyst",
    model="claude-opus-4-7",
    system="You are a data analyst. Use pandas. Be concise.",
    tools=[{"type": "agent_toolset_20260401"}],
    skills=[{"type": "anthropic", "skill_id": "xlsx"}],
)

# 2. Define environment with pandas pre-installed
env = client.beta.environments.create(
    name="data-analysis",
    config={
        "type": "cloud",
        "packages": {"pip": ["pandas==2.2.0", "numpy"]},
        "networking": {"type": "limited", "allowed_hosts": ["api.example.com"]},
    },
)

# 3. Create memory store (one-time setup)
memstore = client.beta.memory_stores.create(
    name="Analyst Preferences",
    description="Per-analyst column-naming conventions and number formats.",
)

# 4. Upload input file
with open("sales.csv", "rb") as f:
    file = client.beta.files.upload(file=f)

# 5. Create session pinning agent version, mounting file + memory
session = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=env.id,
    resources=[
        {"type": "file", "file_id": file.id, "mount_path": "/workspace/sales.csv"},
        {
            "type": "memory_store",
            "memory_store_id": memstore.id,
            "access": "read_write",
            "instructions": "Analyst preferences. Read /mnt/memory/Analyst Preferences/ before starting.",
        },
    ],
    title="Q1 sales analysis",
)

# 6. Open stream FIRST, then send first event
with client.beta.sessions.events.stream(session.id) as stream:
    client.beta.sessions.events.send(
        session.id,
        events=[{
            "type": "user.message",
            "content": [{"type": "text", "text": "Summarize Q1 sales by region. Save the xlsx to /mnt/session/outputs/q1.xlsx"}],
        }],
    )

    for event in stream:
        et = event.type

        if et == "agent.message":
            for block in event.content:
                if block.type == "text":
                    print(block.text)

        elif et == "agent.custom_tool_use":
            # Handle a custom tool call. Match by event.tool_use_id.
            result = run_my_tool(event.name, event.input)
            client.beta.sessions.events.send(
                session.id,
                events=[{
                    "type": "user.custom_tool_result",
                    "custom_tool_use_id": event.tool_use_id,
                    "content": [{"type": "text", "text": result}],
                }],
            )

        elif et == "session.status_idle":
            if event.stop_reason.type == "end_turn":
                break
            elif event.stop_reason.type == "requires_action":
                # blocked on tool confirmations or custom tool results — handle and continue
                pass

        elif et == "session.error":
            print("ERROR:", event.error)
```

## Async client

```python
import anthropic
client = anthropic.AsyncAnthropic()

async with client.beta.sessions.events.stream(session_id) as stream:
    async for event in stream:
        ...
```

## Webhook verification

```python
from fastapi import FastAPI, Request, HTTPException
import anthropic

app = FastAPI()
client = anthropic.Anthropic()

@app.post("/anthropic-webhook")
async def webhook(request: Request):
    raw = await request.body()
    try:
        event = client.beta.webhooks.unwrap(
            raw,
            headers=dict(request.headers),
        )
    except anthropic.WebhookVerificationError:
        raise HTTPException(401)

    # event.data carries only type+id — fetch full object as needed
    if event.data.type == "session.status_idled":
        session = client.beta.sessions.retrieve(event.data.id)
        ...
```

`unwrap` throws on bad signature or payload older than 5 minutes. Set `ANTHROPIC_WEBHOOK_SIGNING_KEY` env var so the SDK can read it automatically.

## Pinning to a specific beta version

If you're tracking a frozen beta:

```python
client = anthropic.Anthropic(
    default_headers={"anthropic-beta": "managed-agents-2026-04-01"}
)
```

The SDK adds this automatically when you call `client.beta.*` methods, so you only need this if you're calling the raw client directly.

## Error handling

```python
from anthropic import APIError, RateLimitError, APIStatusError

try:
    session = client.beta.sessions.create(agent=..., environment_id=...)
except RateLimitError as e:
    # 429 — back off and retry
    ...
except APIStatusError as e:
    if e.status_code == 409:
        # optimistic concurrency conflict on agent update
        ...
    raise
```

## Common gotchas

- **`agent` accepts a string or an object.** String = latest version. Object form (`{"type": "agent", "id": "...", "version": N}`) pins.
- **`events.stream()` is a context manager.** Use `with` so the connection cleans up.
- **`events.send()` accepts a `events: [...]` list.** Even a single event must be in a list.
- **Resources at session create are immutable.** Use `client.beta.sessions.resources.add/delete` for mid-session file changes; **memory stores cannot be added or removed mid-session.**
