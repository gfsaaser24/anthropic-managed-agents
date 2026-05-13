"""Smoke test for a preconfigured Managed Agent.

Retrieves the agent, picks (or creates) an environment, starts a session
with the configured vault + memory store, sends a kickoff message, and
streams events. Reports clearly when anything fails so you can spot a
broken vault credential or wrong env in seconds.

Run with the key inline (PowerShell):
    $env:ANTHROPIC_API_KEY="sk-ant-api03-..."
    $env:AGENT_ID="agent_..."
    $env:VAULT_ID="vlt_..."
    $env:MEMORY_STORE_ID="memstore_..."     # optional
    python resources/test-managed-agent.py
"""

import os
import sys
import traceback

import anthropic

# Force UTF-8 stdout on Windows so emoji/non-ASCII from the agent doesn't crash us.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

AGENT_ID = os.environ.get("AGENT_ID") or "agent_REPLACE_ME"
VAULT_ID = os.environ.get("VAULT_ID") or "vlt_REPLACE_ME"
MEMORY_STORE_ID = os.environ.get("MEMORY_STORE_ID")  # optional
KICKOFF = os.environ.get("KICKOFF") or (
    "Quick smoke test. Don't do the full task yet — just verify your MCP "
    "connections work. Try listing the tools you have available from each "
    "MCP server. If any fails, tell me the exact error. If all succeed, "
    "report what tools you see."
)


def fail(label: str, exc: BaseException) -> None:
    print(f"\nXX {label} failed")
    print(f"   error type: {type(exc).__name__}")
    if isinstance(exc, anthropic.APIStatusError):
        print(f"   http status: {exc.status_code}")
        print(f"   anthropic type: {getattr(exc, 'type', None)}")
        print(f"   message: {exc.message}")
        req_id = getattr(exc.response, "headers", {}).get("request-id") if exc.response else None
        if req_id:
            print(f"   request-id: {req_id}")
    else:
        print(f"   message: {exc}")
        traceback.print_exc()
    sys.exit(1)


def main() -> None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)
    if AGENT_ID == "agent_REPLACE_ME":
        print("XX AGENT_ID env var not set"); sys.exit(1)
    if VAULT_ID == "vlt_REPLACE_ME":
        print("XX VAULT_ID env var not set"); sys.exit(1)

    print(f"-- key prefix: {key[:14]}... (length {len(key)})")
    print(f"-- agent id:   {AGENT_ID}")

    client = anthropic.Anthropic()

    # 1. Retrieve the agent.
    try:
        agent = client.beta.agents.retrieve(agent_id=AGENT_ID)
    except Exception as e:
        fail("agents.retrieve", e)
    print(f"\nOK agent retrieved")
    print(f"   name:    {agent.name}")
    print(f"   model:   {agent.model}")
    print(f"   version: {agent.version}")
    tool_types = [getattr(t, "type", "?") for t in (agent.tools or [])]
    print(f"   tools:   {tool_types}")
    if agent.mcp_servers:
        print(f"   mcp:     {[s.name for s in agent.mcp_servers]}")

    # 2. Pick or create an environment.
    env_id = os.environ.get("ANTHROPIC_ENV_ID")
    if env_id:
        print(f"\n-- using ANTHROPIC_ENV_ID from env: {env_id}")
    else:
        try:
            envs = list(client.beta.environments.list(limit=5))
        except Exception as e:
            fail("environments.list", e)
        if envs:
            env_id = envs[0].id
            print(f"\nOK reusing environment: {env_id} ({envs[0].name})")
        else:
            try:
                env = client.beta.environments.create(
                    name="smoke-test-env",
                    config={"type": "cloud", "networking": {"type": "unrestricted"}},
                )
            except Exception as e:
                fail("environments.create", e)
            env_id = env.id
            print(f"\nOK environment created: {env_id}")

    # 3. Start a session.
    resources = []
    if MEMORY_STORE_ID:
        resources.append({
            "type": "memory_store",
            "memory_store_id": MEMORY_STORE_ID,
            "access": "read_write",
            "instructions": "Test session memory mount. Read /README.md if present.",
        })
    try:
        session = client.beta.sessions.create(
            agent=AGENT_ID,
            environment_id=env_id,
            title="Smoke test",
            vault_ids=[VAULT_ID],
            resources=resources or None,
        )
    except Exception as e:
        fail("sessions.create", e)
    print(f"\nOK session created: {session.id}  (status {session.status})")

    # 4. Stream events while sending the kickoff. Open stream BEFORE sending.
    try:
        with client.beta.sessions.events.stream(session_id=session.id) as stream:
            client.beta.sessions.events.send(
                session_id=session.id,
                events=[{"type": "user.message", "content": [{"type": "text", "text": KICKOFF}]}],
            )
            print("\n-- streaming events --")
            for event in stream:
                t = event.type
                if t == "agent.message":
                    for block in event.content:
                        if getattr(block, "type", None) == "text":
                            print(block.text, end="", flush=True)
                elif t == "agent.thinking":
                    print("\n[thinking...]", end="", flush=True)
                elif t == "agent.tool_use":
                    print(f"\n[tool_use: {getattr(event, 'name', '?')}]")
                elif t == "session.error":
                    print(f"\n[session.error: {event}]")
                elif t == "session.status_idle":
                    stop = getattr(event, "stop_reason", None)
                    reason = getattr(stop, "type", None) if stop else None
                    print(f"\n\n-- idle (stop_reason: {reason}) --")
                    if reason != "requires_action":
                        break
                elif t == "session.status_terminated":
                    print("\n-- terminated --")
                    break
    except Exception as e:
        fail("sessions.events.stream", e)

    print("\nOK smoke test complete")


if __name__ == "__main__":
    main()
