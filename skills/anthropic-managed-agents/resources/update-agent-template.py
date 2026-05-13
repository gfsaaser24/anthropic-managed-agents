"""Template for an agent system-prompt update — copy this for each version
bump. The pattern keeps every prompt change reviewable, dry-runnable, and
fail-loud if the prompt has drifted out from under your needles.

Workflow:
  1. Snapshot current state:  python resources/dump-agent-prompt.py
  2. Write the proposal (full new prompt) as agent-vN-proposed.md.
  3. Copy this file to update-agent-vN.py and fill in `EDITS`.
  4. Dry run:  python update-agent-vN.py
  5. Apply:    python update-agent-vN.py --apply

Each EDIT is an exact-string find/replace with surrounding context to make
it unique. If a needle isn't found, the script ABORTS — no partial writes,
no silent skips. This guards against rebasing your changes onto a prompt
that has changed.

Usage:
    $env:ANTHROPIC_API_KEY="sk-ant-..."
    $env:AGENT_ID="agent_..."
    python update-agent-vN.py            # dry run
    python update-agent-vN.py --apply    # actually push
"""

import os
import sys

import anthropic

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

AGENT_ID = os.environ.get("AGENT_ID") or "agent_REPLACE_ME"
DRY_RUN = "--apply" not in sys.argv


# ---------- Edits ----------
# Each entry is (needle, replacement). The needle MUST be unique in the
# current prompt — include enough surrounding context to disambiguate.
# Use this for prompt edits where the change is local; for full prompt
# rewrites, set `new_system` directly below and skip EDITS.
EDITS: list[tuple[str, str]] = [
    # Example:
    # (
    #     "'{START_ISO}' AND change_event.change_date_time <= '{END_ISO}'",
    #     "'{START_DATETIME}' AND change_event.change_date_time <= '{END_DATETIME}'",
    # ),
]

# Optional metadata changes (merge semantics — empty string deletes a key).
METADATA_PATCH: dict | None = None
# Example:
# METADATA_PATCH = {"google_ads_api_version": "v23"}


def apply_edits(prompt: str) -> str:
    for needle, replacement in EDITS:
        if needle not in prompt:
            raise SystemExit(f"XX needle not found in current prompt: {needle!r}")
        if prompt.count(needle) > 1:
            raise SystemExit(f"XX needle is not unique (found {prompt.count(needle)}x): {needle!r}")
        prompt = prompt.replace(needle, replacement)
    return prompt


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("XX ANTHROPIC_API_KEY not set"); sys.exit(1)
    if AGENT_ID == "agent_REPLACE_ME":
        print("XX AGENT_ID env var not set"); sys.exit(1)

    client = anthropic.Anthropic()
    a = client.beta.agents.retrieve(agent_id=AGENT_ID)
    print(f"-- current version: {a.version}")
    print(f"-- system prompt length: {len(a.system or '')}")

    new_system = apply_edits(a.system or "")
    delta = len(new_system) - len(a.system or "")
    print(f"-- prompt delta: {delta:+d} chars  (after edits applied)")

    if EDITS and new_system == (a.system or ""):
        print("XX no changes after applying edits — abort")
        sys.exit(1)

    if DRY_RUN:
        print("\n-- DRY RUN — pass --apply to push")
        if METADATA_PATCH:
            print(f"-- metadata patch: {METADATA_PATCH}")
        return

    kwargs: dict = {"agent_id": AGENT_ID, "version": a.version, "system": new_system}
    if METADATA_PATCH is not None:
        kwargs["metadata"] = METADATA_PATCH

    updated = client.beta.agents.update(**kwargs)
    print(f"\nOK pushed update — new version: {updated.version}")


if __name__ == "__main__":
    main()
