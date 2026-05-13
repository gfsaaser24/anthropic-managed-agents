"""List memory stores in the workspace + dump contents of each.

Useful for confirming what's mounted, finding orphaned stores, and
spotting `memory_prefix` (dir placeholder) vs actual memory entries.

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    python resources/list-memory-stores.py
"""

import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)

    client = anthropic.Anthropic()

    stores = list(client.beta.memory_stores.list(limit=20))
    if not stores:
        print("(no memory stores in workspace)")
        return

    for s in stores:
        print(f"\n== {s.id} ==")
        print(f"   name:        {s.name}")
        print(f"   description: {getattr(s, 'description', None)}")
        print(f"   metadata:    {getattr(s, 'metadata', None)}")
        print(f"   created_at:  {getattr(s, 'created_at', None)}")
        print(f"   archived_at: {getattr(s, 'archived_at', None)}")
        try:
            mems = list(client.beta.memory_stores.memories.list(s.id, limit=50))
            print(f"   memories ({len(mems)}):")
            for m in mems:
                if getattr(m, "type", None) == "memory_prefix":
                    print(f"     [dir]  {m.path}/")
                else:
                    print(f"     [mem]  {m.path}  ({getattr(m, 'content_size_bytes', '?')} bytes)")
        except Exception as e:
            print(f"   (error listing memories: {e})")


if __name__ == "__main__":
    main()
