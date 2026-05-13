"""Validate each MCP OAuth credential in a vault using Anthropic's
/mcp_oauth_validate diagnostic endpoint.

Tells you: valid / invalid / unknown, plus the actual MCP handshake response
and refresh-token outcome. Use this when an agent session reports
mcp_authentication_failed_error to confirm the root cause.

Note: a credential can show `status: valid` (Anthropic can reach the MCP server
and the probe handshake works) but still be rejected at runtime when the agent
makes its first real tool call — that means the server reads auth from a header
that vaults cannot inject. The fix is full OAuth via mcp-oauth-helper.py.

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:VAULT_ID="vlt_..."
    python resources/validate-vault-credentials.py
"""

import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

VAULT_ID = os.environ.get("VAULT_ID") or "vlt_REPLACE_ME"


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)
    if VAULT_ID == "vlt_REPLACE_ME":
        print("XX VAULT_ID env var not set"); sys.exit(1)

    client = anthropic.Anthropic()

    creds = list(client.beta.vaults.credentials.list(vault_id=VAULT_ID, limit=20))
    if not creds:
        print("(no credentials in vault)")
        return

    for c in creds:
        url = getattr(getattr(c, "auth", None), "mcp_server_url", None) or "?"
        print(f"\n== {c.id} ==")
        print(f"   display_name: {getattr(c, 'display_name', None)}")
        print(f"   mcp_url:      {url}")
        try:
            v = client.beta.vaults.credentials.mcp_oauth_validate(c.id, vault_id=VAULT_ID)
            print(f"   status:           {v.status}")
            print(f"   has_refresh_token: {getattr(v, 'has_refresh_token', None)}")
            probe = getattr(v, "mcp_probe", None)
            if probe and getattr(probe, "http_response", None):
                hr = probe.http_response
                print(f"   mcp_probe.status: {hr.status_code}")
                body = (hr.body or "")[:200]
                print(f"   mcp_probe.body:   {body}")
            refresh = getattr(v, "refresh", None)
            if refresh:
                print(f"   refresh.status:   {getattr(refresh, 'status', None)}")
                rhr = getattr(refresh, "http_response", None)
                if rhr:
                    print(f"   refresh.http:     {rhr.status_code} {(rhr.body or '')[:200]}")
        except anthropic.APIStatusError as e:
            print(f"   XX validate failed: {e.status_code} {e.message}")


if __name__ == "__main__":
    main()
