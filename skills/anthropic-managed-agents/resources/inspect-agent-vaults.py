"""Inspect an agent's declared MCP servers and ALL vaults + credentials in
the workspace. Use to catch URL-mismatches between an agent's mcp_servers[]
list and the credentials trying to authenticate against them — credentials
only match by EXACT mcp_server_url (trailing slash, version segment, etc.).

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:AGENT_ID="agent_..."
    python resources/inspect-agent-vaults.py
"""

import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

AGENT_ID = os.environ.get("AGENT_ID") or "agent_REPLACE_ME"


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)
    if AGENT_ID == "agent_REPLACE_ME":
        print("XX AGENT_ID env var not set"); sys.exit(1)

    client = anthropic.Anthropic()

    agent = client.beta.agents.retrieve(agent_id=AGENT_ID)
    print("=" * 70)
    print(f"AGENT: {agent.name}  (version {agent.version})")
    print("=" * 70)
    print("\nMCP servers declared on agent:")
    for s in (agent.mcp_servers or []):
        print(f"  - name: {s.name}")
        print(f"    type: {getattr(s, 'type', '?')}")
        print(f"    url:  {getattr(s, 'url', '?')}")

    print("\n" + "=" * 70)
    print("VAULTS in workspace:")
    print("=" * 70)
    vaults = list(client.beta.vaults.list(limit=20))
    if not vaults:
        print("  (no vaults exist)")
    for v in vaults:
        print(f"\n  vault: {v.id}")
        print(f"    full object: {v.model_dump_json(indent=4)}")
        try:
            creds = list(client.beta.vaults.credentials.list(vault_id=v.id, limit=20))
            if not creds:
                print(f"    credentials: (none)")
            for c in creds:
                print(f"    credential: {c.id}")
                print(c.model_dump_json(indent=6))
        except Exception as e:
            print(f"    (error listing credentials: {e})")


if __name__ == "__main__":
    main()
