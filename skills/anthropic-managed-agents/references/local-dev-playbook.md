# Local-dev playbook — hard-won lessons from running Managed Agents

This is **the file you read once you stop reading docs and start running real agents.** Everything here is from production work that the official docs either gloss over or get wrong. The scripts referenced live under [`../resources/`](../resources) and are ready to run.

## The single most important non-obvious fact

> **Anthropic vaults can only inject `Authorization: Bearer <token>` into MCP requests. They cannot inject custom headers.**

This is not stated anywhere in the docs. Consequences:

- If an MCP server uses a custom auth header (e.g. Composio's `x-consumer-api-key`), you **cannot** use a vault `static_bearer` credential — Anthropic will send it as `Authorization: Bearer` and the server will reject it.
- The fix is always full OAuth. There is no shortcut, even when you have a working long-lived API key in hand.
- `mcp_oauth_validate` can return `status: valid` for a credential that the MCP server actually rejects — the probe only confirms Anthropic *can call* the server, not that auth lands. If sessions fail with `mcp_authentication_failed_error` and the validate endpoint says "valid", the server is reading auth from a header your vault isn't filling.

## The local OAuth helper (the script you'll use most)

For any MCP server that implements the standard MCP authorization spec (`/.well-known/oauth-protected-resource` + `/.well-known/oauth-authorization-server`), you can self-serve OAuth with zero manual app registration. The helper at [`../resources/mcp-oauth-helper.py`](../resources/mcp-oauth-helper.py) handles:

1. Discovery of OAuth endpoints from the MCP URL's well-known metadata.
2. Dynamic client registration (where supported).
3. PKCE (S256) for the auth request.
4. A local loopback HTTP server on `http://localhost:8765/callback` to catch the redirect.
5. Token exchange.
6. Storing the credential in your Anthropic vault with `refresh` wired up so Anthropic auto-rotates.

### Per-server quirks the helper has been beaten into shape for

#### Composio (`https://connect.composio.dev/mcp`) — works clean

- **Two auth modes:** `Authorization: Bearer <oauth-token>` works; `x-consumer-api-key: ck_...` works as a custom header. Vaults can only use the first one.
- **Full MCP-auth spec support:** dynamic client registration + PKCE + refresh tokens. Use `token_endpoint_auth_method: "none"` (public client).
- **Discovery host:** `https://connect.composio.dev`.
- **Scopes:** `openid profile email offline_access` (the `offline_access` scope is what gets you a refresh token).
- **Tokens expire in ~1 hour.** Anthropic's background refresh handles this transparently as long as the refresh token is attached.

The static `ak_*` / `ck_*` keys you can pluck from the Composio dashboard ONLY work via `x-consumer-api-key`. They will not survive being put in a vault. Forget them and go straight to OAuth.

#### Asana v2 (`https://mcp.asana.com/v2/mcp`) — has three traps

- **There is no dynamic registration.** You must manually register an OAuth app at `https://app.asana.com/0/my-apps`.
- **The OAuth server is NOT `mcp.asana.com`.** It is `https://app.asana.com/-/oauth_authorize` and `https://app.asana.com/-/oauth_token`. The `mcp.asana.com` well-known metadata advertises a *demo* OAuth server that does NOT issue tokens valid against the production v2 MCP endpoint. **Follow the 401's `WWW-Authenticate` header to discover the right one,** don't trust the well-known root.
- **Asana MCP apps reject the `scope` query parameter.** Sending `scope=default` (or any scope) returns "Invalid scope(s) requested". **Omit the `scope` param entirely.**
- **You must include `resource=https://mcp.asana.com/v2`** on the auth URL. Without it, the issued token is not bound to the MCP audience and gets rejected at runtime even though it looks valid.
- Confidential client: `token_endpoint_auth_method: "client_secret_post"`.

App-registration steps (one-time):

1. Go to `https://app.asana.com/0/my-apps`.
2. Click "+ Create new app" → name it → accept terms.
3. Open "OAuth permissions" in the left sidebar.
4. Under Redirect URLs, add `http://localhost:8765/callback`.
5. Copy the Client ID and Client Secret. Export as `ASANA_CLIENT_ID` and `ASANA_CLIENT_SECRET`.

Then run the helper: `python resources/mcp-oauth-helper.py asana`.

### The localhost callback URL

The helper listens on `http://localhost:8765/callback`. You can change the port at the top of the script if 8765 collides. Whatever you pick, register it as a redirect URI on the OAuth provider's side **exactly** (no trailing slash mismatch).

### When dynamic registration produces a one-off client

Anthropic stores `client_id` (and `client_secret` if present) inside the credential's `refresh` block, so the refresh keeps working even after the script exits. **Do not delete the OAuth client from the provider's dashboard** — Anthropic's background refresh will fail.

## When sessions fail with MCP errors

Workflow:

1. **Validate every credential in the vault.** Run [`../resources/validate-vault-credentials.py`](../resources/validate-vault-credentials.py). It calls `mcp_oauth_validate` per credential and prints the actual HTTP probe response, the refresh status, and the server's error body. The probe body is truncated — look for substrings like `invalid_token`, `invalid_audience`, `Invalid scope`.
2. **Read recent session errors.** Run [`../resources/fetch-recent-errors.py`](../resources/fetch-recent-errors.py) — it lists the last 5 sessions, dumps each session's events to JSON, and prints every `is_error=true` event with a 500-char excerpt. The Console UI buries this; the script surfaces it in seconds.
3. **Inspect the agent's actual MCP server declarations.** Run [`../resources/inspect-agent-vaults.py`](../resources/inspect-agent-vaults.py). It prints the agent's `mcp_servers[]` list and every vault + credential in the workspace with their server URLs. A common bug is the credential URL not exactly matching the agent's declared MCP URL (a trailing `/` mismatch, `v1` vs `v2`, etc.) — credentials only match by exact `mcp_server_url`.

## Versioning workflow that survives real iteration

After ~5 versions of a real agent, you'll want a workflow that:
- Never silently mutates an agent.
- Lets you review changes before they ship.
- Fails loud if the system prompt has drifted since the patch was authored.

### Pattern: snapshot → propose → sentinel-patch

1. **Snapshot the current config.** Run [`../resources/dump-agent-prompt.py`](../resources/dump-agent-prompt.py). It writes `agent-current-config.md` with the agent's id, version, model, system prompt, tools, MCP servers, and metadata.
2. **Write a proposed version as a markdown file** (e.g. `agent-v8-proposed.md`) showing the *full* new system prompt + metadata diff. The user reviews this before any API call.
3. **Apply with sentinel-matched `str.replace()`.** Don't write the whole prompt back from scratch — pull the current prompt, do exact-string replacements with surrounding context, and fail loud if a needle isn't found:

```python
# Excerpt from update-agent-vN.py
def patch(old_prompt: str) -> str:
    needles = [
        ("{START_ISO}", "{START_DATETIME}"),  # GAQL date placeholder
        # ...
    ]
    new_prompt = old_prompt
    for needle, replacement in needles:
        if needle not in new_prompt:
            raise SystemExit(f"XX needle not found: {needle!r}")
        new_prompt = new_prompt.replace(needle, replacement)
    return new_prompt
```

4. **Dry-run by default.** Gate the actual `agents.update` call behind `--apply`. Print the diff without `--apply`; only mutate state when explicitly invoked. Example top-of-script:

```python
DRY_RUN = "--apply" not in sys.argv
# ... later ...
if DRY_RUN:
    print("(dry run — pass --apply to push)")
    return
client.beta.agents.update(agent_id=AGENT_ID, version=current_version, system=new_prompt, metadata={...})
```

5. **Bake operational discoveries from session events back into the prompt.** A 24-turn session that wasted 15 turns rediscovering MCC routing collapsed to ~8–10 turns once the routing pattern was baked into the system prompt. The cost of more prompt tokens is more than offset by skipped discovery loops + better cache reuse.

### What's safe to leave unversioned

- The agent's **tools array** can be modified without version bumps for trivial config changes — but anything that adds/removes a tool *will* mint a new version.
- The agent's **metadata** is merge-semantics: pass only the keys you want to change. Empty string deletes a key.
- The agent's **MCP servers** are array-replace; if you want to add one MCP server, pass the full new list.

## Smoke testing pattern

[`../resources/test-managed-agent.py`](../resources/test-managed-agent.py) is a one-shot end-to-end smoke test. It:

1. Retrieves the agent by ID (sanity check that auth + agent exists).
2. Picks an existing environment (or creates one if none exist).
3. Creates a session with vault_ids + memory store.
4. Opens the SSE stream **before** sending the first event (the order matters).
5. Sends a smoke prompt that asks the agent to list its tools across each MCP server and report exact errors. This is the fastest way to know whether vault credentials are landing.
6. Streams agent.message text inline, prints `[tool_use: ...]` markers, surfaces `session.error`, and exits at the first `session.status_idle` with `stop_reason != requires_action`.

Critical Windows quirk baked into every script:

```python
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
```

Without this, the Windows cp1252 default codec will crash on agent output that contains emoji or non-Latin text. You'll see `UnicodeEncodeError: 'charmap' codec can't encode character '✅'`. Always include the reconfigure block at the top.

## Memory store gotchas

[`../resources/setup-memory-store.py`](../resources/setup-memory-store.py) shows the production setup pattern:

1. **Set the `description` field carefully.** It's auto-injected into the agent's system prompt alongside the mount path and `instructions`. Treat it as part of the prompt. Use it to tell the agent the directory layout and the read-first/write-last contract.
2. **Seed a `/README.md` inside the store.** The agent always reads this on session start (if you instruct it to). It defines the directory layout and operating rules in a way the agent can refresh on later without re-loading the system prompt.
3. **`memory_store.memories.create` returns 409 when path already exists.** Catch it and continue; never blindly create on every run.
4. **`memories.list` returns a mix of memory_prefix (directory placeholders) and memory entries.** Filter by `type` if you only want files.

```python
mems = list(client.beta.memory_stores.memories.list(store_id, limit=50))
for m in mems:
    if getattr(m, "type", None) == "memory_prefix":
        print(f"[dir]  {m.path}/")
    else:
        print(f"[mem]  {m.path}  ({m.content_size_bytes} bytes)")
```

5. **Memory is a hint, not a source of truth.** Always reconcile against external state (Asana tasks, Google Ads logs, etc.) before treating memory as authoritative. Adversarial writes via prompt injection are the explicit risk the docs warn about; an agent treating its own memory as gospel is a more common, quieter failure mode.

## Common errors and what they actually mean

| Error message in `session.error` | Real cause |
|---|---|
| `mcp_authentication_failed_error` even after `mcp_oauth_validate` says "valid" | The MCP server reads auth from a custom header that Anthropic vaults can't inject. Use OAuth. |
| `Invalid scope(s) requested` during Asana OAuth | Asana MCP apps reject any `scope` query param. Omit it. |
| `invalid_audience` on Asana token use | OAuth `resource` parameter missing. Set `resource=https://mcp.asana.com/v2` on the auth URL. |
| `Not a recognized ID` from Asana | The URL path `…/list/<id>` looks like a list but the API calls it a **section**. Use `section=...`, not `list=...`. |
| Google Ads change_event GAQL fails with malformed date | The `change_event.change_date_time` filter requires `'YYYY-MM-DD HH:MM:SS'` — space-separated, **no `T`, no `Z`**. ISO 8601 with `T` is rejected. |
| Asana `html_notes` returns `xml_parsing_error` | `html_notes` is parsed as XML. Escape `&`, `<`, `>` and avoid emoji or special unicode. |
| `UnicodeEncodeError: 'charmap'` on local script output | Windows cp1252. Reconfigure stdout to UTF-8 at script entry. |
| Composio dedicated `GOOGLEADS_*` tools silently return MCC data when you pass `customer_id` | Those 5 tools (`GOOGLEADS_SEARCH_STREAM_GAQL`, etc.) don't route to sub-accounts. Use `COMPOSIO_REMOTE_WORKBENCH.proxy_execute` with `login-customer-id` header. |
| `COMPOSIO_REMOTE_BASH_TOOL` times out at 3 min | Hard limit. Use the built-in `bash` from `agent_toolset_20260401` — no timeout. |

## Composio tooling reality check

When you attach the Composio MCP, the agent sees **hundreds of tools** by default. The ones that actually matter for serious work:

- **`COMPOSIO_REMOTE_WORKBENCH`** — a persistent Python notebook with pre-loaded helpers: `proxy_execute(method, url, toolkit, ...)` for direct API passthrough, `run_composio_tool(slug, **inputs)` to invoke any tool from inside Python, `invoke_llm`, `web_search`, `upload_local_file`. State persists across calls in a session. This is the workhorse — most non-trivial work routes through `proxy_execute` here.
- **`COMPOSIO_MULTI_EXECUTE_TOOL`** — batch up to 50 independent tools in parallel in a single call. Use this to fan out parallel queries (e.g. change_event + campaign metrics simultaneously).
- **`COMPOSIO_GET_TOOL_SCHEMAS`** — only when a tool's parameters aren't obvious from context.

Skip:

- **`COMPOSIO_SEARCH_TOOLS`** — bake the known tool surface into the system prompt instead. Search costs turns.
- **`COMPOSIO_MANAGE_CONNECTIONS` / `COMPOSIO_WAIT_FOR_CONNECTIONS`** — handled at session creation by vaults.
- **`COMPOSIO_REMOTE_BASH_TOOL`** — 3-min timeout, prefer built-in `bash`.

If you have a known set of integrations the agent will use, list them by slug in the system prompt and explicitly tell it not to call `COMPOSIO_SEARCH_TOOLS`. This single instruction routinely saves 2–5 turns per session.

## Skill catalog reality

Only **four** skills are reachable via `{type: "anthropic", skill_id: "..."}`:

- `pdf`
- `docx`
- `xlsx`
- `pptx`

Everything else in [`github.com/anthropics/skills`](https://github.com/anthropics/skills) (`web-artifacts-builder`, `canvas-design`, `frontend-design`, `algorithmic-art`, `theme-factory`, etc.) is a **custom** skill you must upload to your workspace via `client.beta.skills.create(...)` first, then attach by `{type: "custom", skill_id: "skill_xxx", version: "latest"}`.

The `web-artifacts-builder` skill in particular targets Claude.ai's chat-UI canvas — its HTML uses CSS variables (`var(--color-text-secondary)`) that come from the chat theme. If you render that HTML in a session container (or send it to Asana), the variables don't resolve. You'll need to inline explicit hex colors yourself.

## Cleanup and hygiene

[`../resources/cleanup-vault.py`](../resources/cleanup-vault.py) is the pattern for vault hygiene:

- Fix `display_name` typos.
- Add `metadata` linking the vault to its owning agent (workspaces are shared, so this matters for future-you).
- Hard-delete archived credentials. `archive` is reversible; `delete` is final. Once a credential is archived and confirmed unused, delete it so it stops cluttering `credentials.list`.

Archived credentials still appear in `credentials.list(include_archived=True)`. Without `include_archived`, they're invisible — easy to forget they're there.

## End-to-end reference flow

The complete sequence from zero to a running, tested agent:

```bash
# Once per workspace
export ANTHROPIC_API_KEY="sk-ant-..."

# Once per MCP server (Asana also needs ASANA_CLIENT_ID / ASANA_CLIENT_SECRET)
python resources/mcp-oauth-helper.py composio
python resources/mcp-oauth-helper.py asana

# Validate credentials landed correctly
python resources/validate-vault-credentials.py

# Set up memory store once (description + README seed)
python resources/setup-memory-store.py

# Snapshot agent before any change
python resources/dump-agent-prompt.py   # -> agent-current-config.md

# Write proposal as agent-vN-proposed.md, review, then patch
python resources/update-agent-vN.py        # dry run prints diff
python resources/update-agent-vN.py --apply  # actually push

# Smoke test
python resources/test-managed-agent.py

# Inspect errors if smoke test surfaced anything
python resources/fetch-recent-errors.py
```

The first three steps are one-time setup; the last four are the iteration loop you run dozens of times during development.

## Set IDs through env vars, not hardcoded constants

The bundled scripts use module-level constants (`AGENT_ID`, `VAULT_ID`, `MEMORY_STORE_ID`) for readability. In real use, parameterize via env vars so the same scripts work across agents:

```python
AGENT_ID = os.environ.get("AGENT_ID") or "agent_01..."
VAULT_ID = os.environ.get("VAULT_ID") or "vlt_..."
MEMORY_STORE_ID = os.environ.get("MEMORY_STORE_ID") or "memstore_..."
```

For multi-agent workspaces, put the IDs in a `.env` file (gitignored) and load with `python-dotenv`.
