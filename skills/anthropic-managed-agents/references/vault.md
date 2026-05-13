# Vault and credentials

> ⚠️ **The single most important non-obvious fact about vaults:** Anthropic vaults can **only** inject `Authorization: Bearer <token>` into MCP requests. They cannot inject custom headers. This is not stated in the docs but reproduces every time. If an MCP server uses a custom auth header (e.g. Composio's `x-consumer-api-key`), no `static_bearer` vault credential will ever work — even when you have a perfectly good API key in hand. **The only path is full OAuth.** See [`local-dev-playbook.md`](local-dev-playbook.md) for the helper that handles this end-to-end (dynamic client registration + PKCE + token storage with refresh).

> ⚠️ **`mcp_oauth_validate` can lie.** A credential can return `status: valid` (Anthropic's probe handshake worked) while the MCP server still rejects every real tool call. That means the server reads auth from a header your vault isn't filling. If sessions fail with `mcp_authentication_failed_error` and validation says "valid", suspect a custom-header auth scheme.

Vaults hold credentials that Managed Agents sessions consume at runtime. The two-step model:

1. **At agent build time** — declare MCP servers on the agent (no secrets). See [`build.md`](build.md) §MCP.
2. **At session create time** — attach `vault_ids: [...]` so the session can authenticate to those MCP servers.

Credentials are matched to MCP servers by `mcp_server_url`. When no credential matches, the session attempts the connection unauthenticated — which generally fails for private servers and surfaces as a `session.error` event.

## Endpoints

| Op | Endpoint |
|---|---|
| Create vault | `POST /v1/vaults` |
| Retrieve vault | `GET /v1/vaults/{vid}` |
| List vaults | `GET /v1/vaults` |
| Archive vault | `POST /v1/vaults/{vid}/archive` |
| Delete vault | `DELETE /v1/vaults/{vid}` |
| Add credential | `POST /v1/vaults/{vid}/credentials` |
| Update / rotate credential | `POST /v1/vaults/{vid}/credentials/{cid}` |
| Validate credential | `POST /v1/vaults/{vid}/credentials/{cid}/mcp_oauth_validate?beta=true` |
| Archive credential | `POST /v1/vaults/{vid}/credentials/{cid}/archive` |
| Delete credential | `DELETE /v1/vaults/{vid}/credentials/{cid}` |

## Vault shape

```json
{
  "type": "vault",
  "id": "vlt_01ABC...",
  "display_name": "Alice",
  "metadata": {"external_user_id": "usr_abc123"},
  "created_at": "2026-03-18T10:00:00Z",
  "updated_at": "2026-03-18T10:00:00Z",
  "archived_at": null
}
```

`metadata.external_user_id` is the **conventional way to associate a vault with a downstream user** in your system. Since vaults are workspace-scoped (anyone with API access can use any vault), you build per-user routing yourself.

## Credential types

### `mcp_oauth` — OAuth-backed credential, optionally with refresh

```json
POST /v1/vaults/{vid}/credentials
{
  "display_name": "Alice's Slack",
  "auth": {
    "type": "mcp_oauth",
    "mcp_server_url": "https://mcp.slack.com/mcp",
    "access_token": "xoxp-...",
    "expires_at": "2099-12-31T23:59:59Z",
    "refresh": {
      "token_endpoint": "https://slack.com/api/oauth.v2.access",
      "client_id": "1234567890.0987654321",
      "scope": "channels:read chat:write",
      "refresh_token": "xoxe-1-...",
      "token_endpoint_auth": {
        "type": "client_secret_post",
        "client_secret": "abc123..."
      }
    }
  }
}
```

`token_endpoint_auth.type` values:
- `none` — no client auth on the refresh request.
- `client_secret_basic` — HTTP Basic with client_id + client_secret.
- `client_secret_post` — client_id + client_secret in POST body.

When `refresh` is supplied, Anthropic will automatically refresh the token in the background before expiry. Failures fire `vault_credential.refresh_failed` webhook events.

### `static_bearer` — long-lived API keys, PATs

```json
{
  "display_name": "Linear API key",
  "auth": {
    "type": "static_bearer",
    "mcp_server_url": "https://mcp.linear.app/mcp",
    "token": "lin_api_..."
  }
}
```

No refresh. Use for PATs and bearer tokens that don't expire (or that you manually rotate).

## Constraints

- **Secrets are write-only.** Fields `token`, `access_token`, `refresh_token`, `client_secret` are never returned by GET endpoints. To rotate, POST a new value via the credential update endpoint.
- **One active credential per `mcp_server_url` per vault.** Adding a second to the same URL returns 409. To swap, archive the old one first, or POST an update (which mints a new value but keeps the credential record).
- **`mcp_server_url` is immutable.** To point at a different server, archive the credential and create a new one.
- **Max 20 credentials per vault.** Same as the max MCP servers per agent.
- **Vaults are workspace-scoped.** Anyone with API-key access to the workspace can reference any vault. There's no per-user ACL.

## Reference a vault on session create

```json
{
  "agent": "agent_01...",
  "environment_id": "env_01...",
  "vault_ids": ["vlt_01..."],
  "title": "Alice's Slack digest"
}
```

You can pass multiple vaults: `"vault_ids": ["vlt_alice...", "vlt_shared..."]`. When two vaults contain credentials for the same `mcp_server_url`, **the first vault wins**.

## Validate / diagnose a credential

Probe whether a credential is still good without making the agent's first MCP call fail:

```
POST /v1/vaults/{vid}/credentials/{cid}/mcp_oauth_validate?beta=true
```

Response:

```json
{
  "type": "vault_credential_validation",
  "credential_id": "vcrd_01ABC...",
  "vault_id": "vlt_01XYZ...",
  "validated_at": "2026-04-29T17:12:00Z",
  "has_refresh_token": false,
  "status": "invalid",
  "mcp_probe": {
    "method": "initialize",
    "http_response": {
      "status_code": 401,
      "content_type": "application/json",
      "body": "{\"error\":\"invalid_token\"}",
      "body_truncated": false
    }
  },
  "refresh": {"status": "no_refresh_token", "http_response": null}
}
```

`status` values:
- `valid` — credential probe succeeded.
- `invalid` — re-auth required. Prompt the user.
- `unknown` — transient failure (network glitch, server down). Retry.

## Webhook events for vault lifecycle

Register on these to drive your re-auth UX:

| Event | When |
|---|---|
| `vault.created` | A vault was created. |
| `vault.archived` | A vault was archived. |
| `vault.deleted` | A vault was deleted. |
| `vault_credential.created` | A credential was added. |
| `vault_credential.archived` | A credential was archived. |
| `vault_credential.deleted` | A credential was deleted. |
| `vault_credential.refresh_failed` | Background refresh failed. **Prompt user to re-auth.** |

See [`status.md`](status.md) §Webhooks for verification rules.

## Rotation patterns

### OAuth token expired

If you have a refresh token attached, Anthropic refreshes in the background. If the refresh itself fails (e.g., revoked grant), you'll see `vault_credential.refresh_failed`. Action: start your OAuth flow with the user, then POST a new credential value via the update endpoint:

```
POST /v1/vaults/{vid}/credentials/{cid}
{
  "auth": {
    "type": "mcp_oauth",
    "mcp_server_url": "https://mcp.slack.com/mcp",
    "access_token": "xoxp-new...",
    "expires_at": "...",
    "refresh": {...}
  }
}
```

### Rotating a static bearer

Same update endpoint:

```
POST /v1/vaults/{vid}/credentials/{cid}
{"auth": {"type": "static_bearer", "mcp_server_url": "https://mcp.linear.app/mcp", "token": "lin_api_NEW..."}}
```

### Revoking access for a single user

Either archive the user's vault, or archive specific credentials within it. Existing sessions will see auth failures on their next MCP call; new sessions won't be able to authenticate against that server URL.

## SDK access (Python)

```python
client.beta.vaults.create(display_name="Alice", metadata={"external_user_id": "usr_abc"})
client.beta.vaults.retrieve("vlt_01...")
client.beta.vaults.list()
client.beta.vaults.archive("vlt_01...")
client.beta.vaults.delete("vlt_01...")

client.beta.vaults.credentials.create(vault_id, display_name="...", auth={...})
client.beta.vaults.credentials.update(vault_id, credential_id, auth={...})
client.beta.vaults.credentials.archive(vault_id, credential_id)
client.beta.vaults.credentials.delete(vault_id, credential_id)
```

The validation endpoint is currently exposed as a beta query parameter, not yet a dedicated SDK method — call via the raw HTTP client.
