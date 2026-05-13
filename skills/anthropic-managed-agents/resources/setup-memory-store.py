"""Memory store one-time setup template:
  1. Set a precise `description` field (auto-injected into system prompt).
  2. Seed /README.md inside the store with the directory layout.

The description and README together teach the agent the read-first /
write-last contract without bloating the system prompt.

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:MEMORY_STORE_ID="memstore_..."
    python resources/setup-memory-store.py
"""

import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

MEMORY_STORE_ID = os.environ.get("MEMORY_STORE_ID") or "memstore_REPLACE_ME"

# Customize for your use case. This auto-prepends to the agent's system prompt
# along with the mount path and `instructions` from the session resource.
NEW_DESCRIPTION = (
    "Persistent state for the agent. Layout: `clients/<id>.md` holds the "
    "last-run summary per client; `patterns.md` holds operational notes. "
    "ALWAYS read `clients/<id>.md` BEFORE starting work — use `next_start` "
    "to skip overlap. ALWAYS write back after completing the task."
)

README_CONTENT = """# Agent memory store

Persistent state. Survives across sessions. Read/write via normal file tools
under `/mnt/memory/<store-name>/`.

## Layout

```
/mnt/memory/<store-name>/
+-- README.md                    (this file)
+-- clients/
|   +-- <id>.md                  (one per client/entity, template below)
+-- patterns.md                  (agent-curated operational notes — optional)
```

## clients/<id>.md template

```markdown
# <Name>
- id: <stable id>
- last_run: <ISO date>
- last_covered: <start_date> -> <end_date>
- next_start: <end_date>
- last_summary: <one-paragraph plain English>
- quirks: <preserve across runs; modify only on new context>
```

## Operating rules

1. **Read first.** Before any work, read `clients/<id>.md` for the target.
2. **Write last.** After confirming the deliverable, overwrite the file with
   updated `last_run`, `last_covered`, `next_start`, `last_summary`.
3. **Memory is a hint, not truth.** Reconcile against external systems (the
   true source of truth) before treating memory as authoritative.
4. **Append, don't replace, `patterns.md`.** Use for cross-client findings
   (new API quirks, integration patterns, etc.).

## Constraints

- 100 kB max per file (~25k tokens). Keep entries concise.
"""


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)
    if MEMORY_STORE_ID == "memstore_REPLACE_ME":
        print("XX MEMORY_STORE_ID env var not set"); sys.exit(1)

    client = anthropic.Anthropic()

    print(">> updating memory store description")
    updated = client.beta.memory_stores.update(
        memory_store_id=MEMORY_STORE_ID,
        description=NEW_DESCRIPTION,
    )
    print(f"   OK new description ({len(updated.description)} chars)")

    print("\n>> seeding /README.md")
    try:
        readme = client.beta.memory_stores.memories.create(
            memory_store_id=MEMORY_STORE_ID,
            path="/README.md",
            content=README_CONTENT,
        )
        print(f"   OK created {readme.id} ({readme.content_size_bytes} bytes)")
    except anthropic.APIStatusError as e:
        if e.status_code == 409:
            print("   (already exists — skipping)")
        else:
            raise


if __name__ == "__main__":
    main()
