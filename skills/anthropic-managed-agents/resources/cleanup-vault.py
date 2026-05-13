"""Vault hygiene script:
  1. Fix display_name + metadata on the vault.
  2. Hard-delete archived credentials left over from debugging.

`archive` is reversible; `delete` is final. Once a credential is archived
and confirmed unused, delete it so it stops cluttering credentials.list.
Archived creds still appear in credentials.list(include_archived=True).

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:VAULT_ID="vlt_..."
    $env:AGENT_ID="agent_..."
    $env:VAULT_DISPLAY_NAME="My Vault"
    python resources/cleanup-vault.py
"""

import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

VAULT_ID = os.environ.get("VAULT_ID") or "vlt_REPLACE_ME"
AGENT_ID = os.environ.get("AGENT_ID") or "agent_REPLACE_ME"
VAULT_DISPLAY_NAME = os.environ.get("VAULT_DISPLAY_NAME") or "Managed Agent Vault"


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)
    if VAULT_ID == "vlt_REPLACE_ME":
        print("XX VAULT_ID env var not set"); sys.exit(1)

    client = anthropic.Anthropic()

    print(">> renaming vault and adding metadata")
    updated = client.beta.vaults.update(
        vault_id=VAULT_ID,
        display_name=VAULT_DISPLAY_NAME,
        metadata={
            "agent_id": AGENT_ID,
            "purpose": "MCP credentials for the managed agent",
        },
    )
    print(f"   OK display_name: {updated.display_name}")
    print(f"   OK metadata:     {updated.metadata}")

    print("\n>> hard-deleting archived credentials")
    all_creds = list(client.beta.vaults.credentials.list(
        vault_id=VAULT_ID, limit=50, include_archived=True
    ))
    archived = [c for c in all_creds if getattr(c, "archived_at", None)]
    if not archived:
        print("   (no archived credentials)")
    for c in archived:
        url = getattr(getattr(c, "auth", None), "mcp_server_url", "?")
        print(f"   deleting {c.id}  url={url}  name={c.display_name}")
        client.beta.vaults.credentials.delete(c.id, vault_id=VAULT_ID)
    print(f"   OK deleted {len(archived)} archived credential(s)")

    print("\n>> final state")
    vault = client.beta.vaults.retrieve(vault_id=VAULT_ID)
    print(f"   vault.display_name: {vault.display_name}")
    print(f"   vault.metadata:     {vault.metadata}")
    active = list(client.beta.vaults.credentials.list(vault_id=VAULT_ID, limit=20))
    print(f"   active credentials ({len(active)}):")
    for c in active:
        url = getattr(getattr(c, "auth", None), "mcp_server_url", "?")
        print(f"     - {c.id}  {c.display_name}  ({url})")


if __name__ == "__main__":
    main()
