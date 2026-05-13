"""List recent sessions, dump each to JSON, and print every is_error=true
event with a short excerpt. The Console buries error detail; this surfaces
it in seconds.

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    python resources/fetch-recent-errors.py
"""

import json
import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)

    client = anthropic.Anthropic()
    sessions = list(client.beta.sessions.list(limit=8))
    print("Recent sessions (newest first):")
    for s in sessions[:8]:
        print(f"  {s.id}  status={s.status}  created={getattr(s, 'created_at', '?')}  title={getattr(s, 'title', None)}")

    # Focus on the most recent 3.
    for s in sessions[:3]:
        print(f"\n{'=' * 80}\nSession: {s.id}\n{'=' * 80}")
        events = list(client.beta.sessions.events.list(session_id=s.id))
        out = f"session-events-{s.id}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump([e.model_dump(mode="json") for e in events], f, default=str, indent=2)
        print(f"  wrote {out}  ({len(events)} events)")

        errors = []
        for e in events:
            if getattr(e, "is_error", False) or getattr(e, "type", "") == "session.error":
                errors.append(e)
        print(f"  errors: {len(errors)}")
        for e in errors:
            t = getattr(e, "type", "?")
            content = getattr(e, "content", None)
            snippet = ""
            if content:
                try:
                    snippet = (content[0].text if hasattr(content[0], "text") else str(content[0]))[:500]
                except Exception:
                    snippet = str(content)[:500]
            err = getattr(e, "error", None)
            if err:
                snippet = str(err)[:500]
            print(f"\n  [{t}] {getattr(e, 'id', '?')}")
            print(f"    {snippet}")


if __name__ == "__main__":
    main()
