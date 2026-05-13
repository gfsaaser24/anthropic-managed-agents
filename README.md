<p align="center">
  <img src="assets/hero.png" alt="anthropic-managed-agents-skill" width="100%" />
  <br/>
  <sub><i>(credit to <a href="https://twitter.com/rubenhassid">@rubenhassid</a> for photo idea)</i></sub>
</p>

# anthropic-managed-agents-skill

A catalog repository of [Agent Skills](https://agentskills.io/) for working with Anthropic's hosted agent platform.

Follows the [`vercel-labs/agent-skills`](https://github.com/vercel-labs/agent-skills) convention: each skill is a directory under `skills/` containing a `SKILL.md`.

## Available skills

### anthropic-managed-agents

Complete coverage of Anthropic's **Claude Managed Agents** API. When this skill loads, the model has the full operational surface: agent/environment/session lifecycle, vault and memory semantics, skill attachment, multiagent threads, outcomes/rubrics, webhooks, the `ant` CLI, and both Python and TypeScript SDK shapes.

**Use when:**
- Building, deploying, or operating Claude Managed Agents.
- Asking about `/v1/agents`, `/v1/sessions`, `/v1/environments`, `/v1/memory_stores`, or `/v1/vaults`.
- Writing code that imports `client.beta.agents`, `client.beta.sessions`, `client.beta.memory_stores`, or `client.beta.vaults`.
- Using the `ant` CLI.
- Designing multiagent coordinators or outcome-driven evaluation loops.
- Debugging session events, webhooks, or vault credential refresh.

**Sub-modes:**
- **Build** — creating and configuring agents, environments, tools, skills, MCP servers. See [`skills/anthropic-managed-agents/references/build.md`](skills/anthropic-managed-agents/references/build.md).
- **Status check** — listing resources, polling status, reading events, observability, webhooks. See [`skills/anthropic-managed-agents/references/status.md`](skills/anthropic-managed-agents/references/status.md).
- **Test** — running sessions, streaming SSE, custom-tool round trips, outcomes/rubric loop. See [`skills/anthropic-managed-agents/references/test.md`](skills/anthropic-managed-agents/references/test.md).
- **Local dev playbook** — hands-on learnings the docs don't cover: vault `Authorization: Bearer`-only injection limit, Composio + Asana OAuth quirks, Windows UTF-8, sentinel-patched versioning workflow, error triage. See [`skills/anthropic-managed-agents/references/local-dev-playbook.md`](skills/anthropic-managed-agents/references/local-dev-playbook.md).

**Bundled helpers** (`resources/`): dynamic-registration OAuth helper (`mcp-oauth-helper.py`), credential validator, vault inspector, vault cleanup, prompt snapshotter, sentinel-patched versioning template, end-to-end smoke test, memory-store setup, recent-error surfacing, plus curl wrappers for pure-shell workflows.

## Installation

### Via the Agent Skills CLI

```bash
npx skills add gfsaaser24/anthropic-managed-agents-skill
```

**Non-interactive, Claude Code only** — accept defaults and scope the install to Claude Code without prompting:

```bash
npx skills add -y gfsaaser24/anthropic-managed-agents-skill --agent claude-code
```

### Manual install (Claude Code)

```bash
git clone https://github.com/gfsaaser24/anthropic-managed-agents-skill
mkdir -p ~/.claude/skills
cp -r anthropic-managed-agents-skill/skills/anthropic-managed-agents ~/.claude/skills/
```

### Claude.ai sandbox

Upload `skills/anthropic-managed-agents/` (or its zipped form) via the sandbox UI.

## Skill structure

Each skill contains:

- `SKILL.md` — instructions for the agent (loaded at trigger time)
- `references/` — supporting documentation (loaded as needed via progressive disclosure)
- `resources/` — helper scripts (optional)
- `metadata.json` — package-level info that doesn't fit in YAML frontmatter
- `README.md` — human-readable description

## Snapshot date

Skills in this repo reflect Anthropic's documentation as of **2026-05-12**. The Managed Agents beta header is `managed-agents-2026-04-01`. Research-preview features (Outcomes, Multiagent) require access via [Anthropic's form](https://claude.com/form/claude-managed-agents).

## Contributing

Open a PR. CI validates the YAML frontmatter on every `SKILL.md` in `skills/`.

## License

MIT — see [LICENSE](LICENSE).
