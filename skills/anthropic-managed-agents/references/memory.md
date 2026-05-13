# Memory stores

Memory stores are **workspace-scoped, version-controlled collections of text documents** that survive across sessions. Attach up to 8 stores to a session at creation time; the agent reads/writes them with normal file tools.

## Endpoints

| Op | Endpoint |
|---|---|
| Create store | `POST /v1/memory_stores` |
| Retrieve store | `GET /v1/memory_stores/{id}` |
| Update store metadata | `POST /v1/memory_stores/{id}` |
| List stores | `GET /v1/memory_stores?include_archived=true` |
| Archive store (one-way) | `POST /v1/memory_stores/{id}/archive` |
| Delete store (purge) | `DELETE /v1/memory_stores/{id}` |
| Create memory | `POST /v1/memory_stores/{sid}/memories` |
| Retrieve memory | `GET /v1/memory_stores/{sid}/memories/{mid}` |
| Update memory | `POST /v1/memory_stores/{sid}/memories/{mid}` |
| List memories | `GET /v1/memory_stores/{sid}/memories?path_prefix=/prefs&order_by=path&depth=2` |
| Delete memory | `DELETE /v1/memory_stores/{sid}/memories/{mid}` |
| List versions | `GET /v1/memory_stores/{sid}/memory_versions?memory_id=...` |
| Retrieve version | `GET /v1/memory_stores/{sid}/memory_versions/{vid}` |
| Redact version | `POST /v1/memory_stores/{sid}/memory_versions/{vid}/redact` |

## Concept

> A memory store is a workspace-scoped collection of text documents optimized for Claude. When you attach a store to a session, it is mounted as a directory inside the session's container. The agent reads and writes it with the same file tools it uses for the rest of the filesystem, and a note describing each mount is automatically added to the system prompt.

The agent toolset (`agent_toolset_20260401`) is **required** for memory interactions — the agent uses `read`, `write`, `edit`, `glob`, `grep` against `/mnt/memory/`.

## Create a store

```json
POST /v1/memory_stores
{"name": "User Preferences", "description": "Per-user preferences and project context."}
```

Returns `id: "memstore_01..."`. The `description` is passed to the agent telling it what's in the store.

## Attach to a session (creation time only)

```json
POST /v1/sessions
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

| Field | Notes |
|---|---|
| `memory_store_id` | Store to mount. |
| `access` | `read_write` (default) or `read_only`. Enforced at the filesystem layer. |
| `instructions` | Max 4,096 chars. Concatenated into the system prompt with the store's `name`+`description`. |

**You cannot attach or detach memory stores mid-session.** Plan up front.

Mount point inside the container: `/mnt/memory/<store-name>/`.

## Hard limits

| Thing | Limit |
|---|---|
| Memory stores per session | **8** |
| Bytes per memory | **100 kB** (~25k tokens) |
| `instructions` length | 4,096 chars |
| Memory version retention | 30 days; recent versions always kept |

**Structure memory as many small focused files, not a few large ones.** This optimizes for partial reads and minimizes context spend when the agent only needs one fact.

## Per-memory operations

### Create

```json
POST /v1/memory_stores/{sid}/memories
{"path": "/preferences/formatting.md", "content": "Always use tabs, not spaces."}
```

### Update (rename, content edit, or both)

```json
POST /v1/memory_stores/{sid}/memories/{mid}
{"path": "/archive/2026_q1_formatting.md"}
```

### Safe optimistic-concurrency edit

```json
{
  "content": "CORRECTED: Always use 2-space indentation.",
  "precondition": {"type": "content_sha256", "content_sha256": "<sha-of-prior-content>"}
}
```

This fails if the memory has changed since you read it. Always use this when you're editing memory you previously read.

### List with prefix

```
GET /v1/memory_stores/{sid}/memories?path_prefix=/prefs&order_by=path&depth=2
```

`depth` controls how many path segments deep the listing goes.

## Memory versions

> Every mutation to a memory creates an immutable memory version (`memver_...`). Versions belong to the store (not the individual memory) and survive even after the memory itself is deleted.

> Versions are retained for 30 days; however, the recent versions are always kept regardless of age, so memories that change infrequently might retain history beyond 30 days. The live `memories.retrieve` call always returns the latest version.

### Roll back

There's no dedicated restore endpoint. Pattern:

1. `GET /v1/memory_stores/{sid}/memory_versions/{vid}` — fetch the desired version's `content`.
2. `POST /v1/memory_stores/{sid}/memories/{mid}` — write that content back as the new latest version (or `POST .../memories` if the parent memory was deleted).

### Redact a version

```
POST /v1/memory_stores/{sid}/memory_versions/{vid}/redact
```

Used to scrub PII or accidentally-written secrets from history. Constraints:

> A version that is the current head of a live memory cannot be redacted. Write a new version first (or delete the memory), then redact the old one.

## Security: read_only by default for untrusted input

> Memory stores attach with `read_write` access by default. If the agent processes untrusted input … a successful prompt injection could write malicious content into the store. Later sessions then read that content as trusted memory. Use `read_only` for reference material.

Practical pattern:
- **Reference material** (style guides, fact sheets, policies the agent should consult): `read_only`.
- **User journaling/state** (preferences, scratchpads): `read_write`, but only on sessions where input is trusted (you control the user identity).
- **Agent self-notes** (multi-day plans): consider a *separate* `read_write` store dedicated to that purpose, and audit version diffs.

## Versioning audit

When you suspect adversarial writes, list versions in time order and diff:

```python
versions = client.beta.memory_stores.memory_versions.list(
    store_id, memory_id=memory_id, order_by="created_at"
)
for v in versions:
    full = client.beta.memory_stores.memory_versions.retrieve(store_id, v.id)
    print(full.created_at, full.content[:200])
```

Anything suspicious can be redacted (after writing a clean head version first).

## When NOT to use memory stores

- For per-session ephemeral state — use the container filesystem; it's preserved by checkpointing.
- For machine-readable structured data — memory is text-optimized. Use files mounted via `resources` for binary/CSV/parquet inputs.
- For secrets — use vaults.

## SDK access (Python)

```python
client.beta.memory_stores.create(name="...", description="...")
client.beta.memory_stores.retrieve("memstore_01...")
client.beta.memory_stores.update("memstore_01...", name="...", description="...")
client.beta.memory_stores.list(include_archived=True)
client.beta.memory_stores.archive("memstore_01...")
client.beta.memory_stores.delete("memstore_01...")

client.beta.memory_stores.memories.create(store_id, path="...", content="...")
client.beta.memory_stores.memories.retrieve(store_id, memory_id)
client.beta.memory_stores.memories.update(store_id, memory_id, content="...", precondition={...})
client.beta.memory_stores.memories.list(store_id, path_prefix="/x", depth=2)
client.beta.memory_stores.memories.delete(store_id, memory_id)

client.beta.memory_stores.memory_versions.list(store_id, memory_id="...")
client.beta.memory_stores.memory_versions.retrieve(store_id, version_id)
client.beta.memory_stores.memory_versions.redact(store_id, version_id)
```
