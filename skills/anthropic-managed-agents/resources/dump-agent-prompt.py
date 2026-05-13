"""Dump full agent system prompt + tools config to a markdown file for review.

Use as the FIRST step before any update-agent-vN.py patch:
  1. python resources/dump-agent-prompt.py   -> writes agent-current-config.md
  2. open agent-current-config.md, review state
  3. write agent-vN-proposed.md showing the new prompt
  4. write update-agent-vN.py that applies the diff via sentinel str.replace()
  5. run update-agent-vN.py (dry run) then update-agent-vN.py --apply

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:AGENT_ID="agent_..."
    python resources/dump-agent-prompt.py
"""

import json
import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

AGENT_ID = os.environ.get("AGENT_ID") or "agent_REPLACE_ME"
OUT = os.environ.get("DUMP_OUT") or "agent-current-config.md"


def main() -> None:
    if AGENT_ID == "agent_REPLACE_ME":
        print("XX AGENT_ID env var not set"); sys.exit(1)
    client = anthropic.Anthropic()
    a = client.beta.agents.retrieve(agent_id=AGENT_ID)

    md = []
    md.append(f"# Agent: {a.name}\n")
    md.append(f"- **id**: `{a.id}`")
    md.append(f"- **version**: {a.version}")
    md.append(f"- **model**: {a.model}")
    md.append(f"- **description**: {a.description}\n")

    md.append("## Metadata\n")
    md.append("```json")
    md.append(json.dumps(getattr(a, "metadata", {}) or {}, indent=2))
    md.append("```\n")

    md.append("## System prompt\n")
    md.append("```")
    md.append(a.system or "")
    md.append("```\n")

    md.append("## Tools\n")
    for t in (a.tools or []):
        tt = getattr(t, "type", "?")
        md.append(f"- **{tt}**")
        if tt == "mcp_toolset":
            md.append(f"  - mcp_server_name: `{getattr(t, 'mcp_server_name', '?')}`")
            md.append(f"  - default_config: `{getattr(t, 'default_config', None)}`")
            md.append(f"  - configs: `{getattr(t, 'configs', None)}`")
        elif tt == "agent_toolset_20260401":
            md.append(f"  - default_config: `{getattr(t, 'default_config', None)}`")
            md.append(f"  - configs: `{getattr(t, 'configs', None)}`")

    md.append("\n## MCP servers\n")
    for s in (a.mcp_servers or []):
        md.append(f"- **{s.name}** -> {getattr(s, 'url', '?')}")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"OK wrote {OUT}")


if __name__ == "__main__":
    main()
