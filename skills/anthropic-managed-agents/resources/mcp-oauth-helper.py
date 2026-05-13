"""One-shot MCP OAuth helper.

Works with any MCP server that advertises standard MCP-authorization-spec
discovery (/.well-known/oauth-protected-resource +
/.well-known/oauth-authorization-server) and supports dynamic client
registration + PKCE. Currently verified for Composio and Asana.

Flow:
  1. Discover OAuth endpoints from the MCP URL's well-known metadata.
  2. Dynamically register a public client at registration_endpoint
     (or use a manually-registered confidential client for servers that
     don't support dynamic registration — e.g. Asana).
  3. Build the authorization URL with PKCE (S256).
  4. Open the browser; catch the redirect on http://localhost:8765/callback.
  5. Exchange the auth code for access_token + refresh_token.
  6. Store the credential in the configured vault with auto-refresh wired up.

Usage (PowerShell):
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:VAULT_ID="vlt_..."
    python resources/mcp-oauth-helper.py composio
    # Asana also requires:
    $env:ASANA_CLIENT_ID="..."; $env:ASANA_CLIENT_SECRET="..."
    python resources/mcp-oauth-helper.py asana

Background:
    Anthropic vaults can only inject `Authorization: Bearer <token>` —
    they cannot inject custom headers. Even MCP servers that accept a
    static API key via a custom header (e.g. Composio's x-consumer-api-key)
    require full OAuth to work through a vault. This script is the path
    of least resistance.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic
import requests

VAULT_ID = os.environ.get("VAULT_ID") or "vlt_REPLACE_ME"
REDIRECT_PORT = int(os.environ.get("OAUTH_REDIRECT_PORT", "8765"))
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
STATE_FILE = ".oauth-state.json"  # gitignored

SERVERS = {
    "composio": {
        "display_name": "Composio",
        "mcp_url": "https://connect.composio.dev/mcp",
        "discovery_host": "https://connect.composio.dev",
        # offline_access gets you a refresh token.
        "scopes": "openid profile email offline_access",
        # Public client — dynamic registration + PKCE only.
        "dynamic_registration": True,
        "token_endpoint_auth_method": "none",
    },
    "asana": {
        "display_name": "Asana",
        "mcp_url": "https://mcp.asana.com/v2/mcp",
        # Asana v2 MCP requires app type "MCP app" registered at
        # app.asana.com/0/my-apps. Standard OAuth/native apps issue tokens
        # that are not valid against the v2 MCP server. The mcp.asana.com
        # well-known metadata advertises a *demo* OAuth server that does NOT
        # issue tokens valid for production v2 — hardcode the real endpoints.
        "authorization_endpoint": "https://app.asana.com/-/oauth_authorize",
        "token_endpoint": "https://app.asana.com/-/oauth_token",
        # MCP apps DO NOT use scopes — including the scope param returns
        # "Invalid scope(s) requested". Use empty string to skip.
        "scopes": "",
        # MCP apps must include the resource parameter on the auth URL.
        "extra_auth_params": {"resource": "https://mcp.asana.com/v2"},
        "dynamic_registration": False,
        "token_endpoint_auth_method": "client_secret_post",
        "env_client_id": "ASANA_CLIENT_ID",
        "env_client_secret": "ASANA_CLIENT_SECRET",
        "oob": False,
    },
}


# ---------- PKCE helpers ----------

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_pkce() -> tuple[str, str]:
    verifier = b64url(secrets.token_bytes(64))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


# ---------- Redirect catcher ----------

class CodeCatcher(http.server.BaseHTTPRequestHandler):
    captured: dict = {}

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/callback":
            self.captured.update({k: v[0] for k, v in params.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body style='font-family:sans-serif;padding:40px'>"
                b"<h2>Authorized.</h2><p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args, **kwargs):  # silence default logging
        pass


def wait_for_code() -> dict:
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), CodeCatcher)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"-- listening on {REDIRECT_URI}")
    try:
        while not CodeCatcher.captured.get("code") and not CodeCatcher.captured.get("error"):
            pass
    finally:
        server.shutdown()
    return dict(CodeCatcher.captured)


# ---------- Main flow ----------

def discover(host: str) -> tuple[dict, dict]:
    pr = requests.get(f"{host}/.well-known/oauth-protected-resource", timeout=10).json()
    auth_server = pr["authorization_servers"][0]
    # Try the authorization server URL first, fall back to host.
    for base in (auth_server, host):
        r = requests.get(f"{base}/.well-known/oauth-authorization-server", timeout=10)
        if r.ok:
            return pr, r.json()
    r.raise_for_status()
    return pr, r.json()  # unreachable


def register_client(registration_endpoint: str, server_name: str) -> dict:
    payload = {
        "redirect_uris": [REDIRECT_URI],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_name": f"Managed Agent client ({server_name})",
    }
    r = requests.post(registration_endpoint, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in SERVERS:
        print(f"Usage: python {sys.argv[0]} {{composio|asana}}")
        sys.exit(2)
    if VAULT_ID == "vlt_REPLACE_ME":
        print("XX VAULT_ID env var not set"); sys.exit(1)
    server_name = sys.argv[1]
    cfg = dict(SERVERS[server_name])
    oob_env = os.environ.get(f"{server_name.upper()}_OOB")
    if oob_env is not None:
        cfg["oob"] = oob_env.lower() in ("1", "true", "yes")
    print(f"== OAuth flow for {server_name} ==")
    print(f"   MCP URL: {cfg['mcp_url']}")
    print(f"   redirect: {REDIRECT_URI if not cfg.get('oob') else 'OOB (paste code)'}")

    # 1. Endpoints + client credentials.
    client_secret: Optional[str] = None
    if cfg["dynamic_registration"]:
        pr, meta = discover(cfg["discovery_host"])
        authorization_endpoint = meta["authorization_endpoint"]
        token_endpoint = meta["token_endpoint"]
        print(f"\nOK discovery")
        print(f"   authorization_endpoint: {authorization_endpoint}")
        print(f"   token_endpoint:         {token_endpoint}")
        client = register_client(meta["registration_endpoint"], server_name)
        client_id = client["client_id"]
        print(f"\nOK client registered: {client_id}")
    else:
        authorization_endpoint = cfg["authorization_endpoint"]
        token_endpoint = cfg["token_endpoint"]
        client_id = os.environ.get(cfg["env_client_id"])
        client_secret = os.environ.get(cfg["env_client_secret"])
        if not client_id or not client_secret:
            print(f"XX {cfg['env_client_id']} and {cfg['env_client_secret']} must be set")
            sys.exit(1)
        print(f"\nOK using manually-registered client: {client_id}")

    # 2. PKCE + auth URL.
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(16)
    redirect_uri = "urn:ietf:wg:oauth:2.0:oob" if cfg.get("oob") else REDIRECT_URI
    auth_params: dict = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if cfg.get("scopes"):
        auth_params["scope"] = cfg["scopes"]
    for k, v in (cfg.get("extra_auth_params") or {}).items():
        auth_params[k] = v
    auth_url = authorization_endpoint + "?" + urllib.parse.urlencode(auth_params)
    print(f"\n-- opening browser. If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # 3. Catch code.
    if cfg.get("oob"):
        code = os.environ.get("OAUTH_CODE")
        if not code:
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "server": server_name,
                    "client_id": client_id,
                    "verifier": verifier,
                    "state": state,
                    "redirect_uri": redirect_uri,
                    "token_endpoint": token_endpoint,
                }, f)
            print(f"\nOK state saved to {STATE_FILE}")
            print(f"\n>>> ACTION: open the URL, authorize, copy the code, then re-run:")
            print(f">>> OAUTH_CODE=<code> python {sys.argv[0]} {server_name}")
            sys.exit(0)
        with open(STATE_FILE) as f:
            saved = json.load(f)
        if saved["server"] != server_name:
            print(f"XX state file is for {saved['server']}, not {server_name}"); sys.exit(1)
        verifier = saved["verifier"]
        client_id = saved["client_id"]
        redirect_uri = saved["redirect_uri"]
        token_endpoint = saved["token_endpoint"]
        print("OK code received (OOB)")
    else:
        result = wait_for_code()
        if result.get("error"):
            print(f"XX authorization error: {result}")
            sys.exit(1)
        if result.get("state") != state:
            print("XX state mismatch — possible CSRF; aborting")
            sys.exit(1)
        code = result["code"]
        print("OK code received")

    # 4. Token exchange.
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    if client_secret:
        token_data["client_secret"] = client_secret
    r = requests.post(
        token_endpoint,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if not r.ok:
        print(f"XX token exchange failed: {r.status_code} {r.text}")
        sys.exit(1)
    tokens = r.json()
    print(f"\nOK token exchange")
    print(f"   token_type:    {tokens.get('token_type')}")
    print(f"   expires_in:    {tokens.get('expires_in')}")
    print(f"   has_refresh:   {bool(tokens.get('refresh_token'))}")
    print(f"   scope:         {tokens.get('scope')}")

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
    ).isoformat()

    auth_body = {
        "type": "mcp_oauth",
        "mcp_server_url": cfg["mcp_url"],
        "access_token": tokens["access_token"],
        "expires_at": expires_at,
    }
    if tokens.get("refresh_token"):
        refresh_block = {
            "refresh_token": tokens["refresh_token"],
            "client_id": client_id,
            "token_endpoint": token_endpoint,
            "token_endpoint_auth": {"type": cfg["token_endpoint_auth_method"]},
        }
        if client_secret:
            refresh_block["token_endpoint_auth"]["client_secret"] = client_secret
        auth_body["refresh"] = refresh_block

    # 5. Store in vault — archive any existing credential for the same URL first.
    anthropic_client = anthropic.Anthropic()
    existing = list(anthropic_client.beta.vaults.credentials.list(vault_id=VAULT_ID, limit=20))
    for c in existing:
        url = getattr(getattr(c, "auth", None), "mcp_server_url", None)
        if url == cfg["mcp_url"]:
            print(f"\n-- archiving existing credential {c.id} for same URL")
            anthropic_client.beta.vaults.credentials.archive(c.id, vault_id=VAULT_ID)

    cred = anthropic_client.beta.vaults.credentials.create(
        vault_id=VAULT_ID,
        display_name=cfg["display_name"],
        auth=auth_body,
    )
    print(f"\nOK credential stored in vault: {cred.id}")
    print(f"   pinned to:     {cfg['mcp_url']}")
    print(f"   expires_at:    {expires_at}")
    print(f"   auto-refresh:  {'enabled' if tokens.get('refresh_token') else 'NOT enabled'}")

    if cfg.get("oob") and os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)


if __name__ == "__main__":
    main()
