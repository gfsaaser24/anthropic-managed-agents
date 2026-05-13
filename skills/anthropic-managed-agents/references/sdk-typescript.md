# TypeScript SDK — Managed Agents

The official `@anthropic-ai/sdk` package supports Managed Agents under `client.beta.*`. The beta header is added automatically.

```bash
npm install @anthropic-ai/sdk
```

```ts
import Anthropic from "@anthropic-ai/sdk";
const client = new Anthropic(); // reads ANTHROPIC_API_KEY
```

## Method tree (mirrors Python)

```ts
client.beta.agents.create({ name, model, system, tools, mcp_servers, skills, multiagent, metadata });
client.beta.agents.retrieve(agentId);
client.beta.agents.list({ limit, after });
client.beta.agents.update(agentId, { version, system, tools /* ... */ });
client.beta.agents.archive(agentId);
client.beta.agents.versions.list(agentId);

client.beta.environments.create({ name, config });
client.beta.environments.retrieve(envId);
client.beta.environments.list();
client.beta.environments.archive(envId);
client.beta.environments.delete(envId);

client.beta.sessions.create({ agent, environment_id, title, vault_ids, resources });
client.beta.sessions.retrieve(sessionId);
client.beta.sessions.list({ status });
client.beta.sessions.archive(sessionId);
client.beta.sessions.delete(sessionId);

client.beta.sessions.events.send(sessionId, { events: [...] });
client.beta.sessions.events.list(sessionId, { types, created_at_gte });
client.beta.sessions.events.stream(sessionId); // async iterable

client.beta.sessions.resources.add(sessionId, { type, file_id, mount_path });
client.beta.sessions.resources.list(sessionId);
client.beta.sessions.resources.delete(sessionId, resourceId);

client.beta.sessions.threads.list(sessionId);
client.beta.sessions.threads.archive(sessionId, threadId);
client.beta.sessions.threads.events.list(sessionId, threadId, { types });
client.beta.sessions.threads.events.streamEvents(sessionId, threadId);

client.beta.memoryStores.create({ name, description });
client.beta.memoryStores.retrieve(storeId);
client.beta.memoryStores.update(storeId, { name, description });
client.beta.memoryStores.list({ include_archived });
client.beta.memoryStores.archive(storeId);
client.beta.memoryStores.delete(storeId);

client.beta.memoryStores.memories.create(storeId, { path, content });
client.beta.memoryStores.memories.retrieve(storeId, memoryId);
client.beta.memoryStores.memories.update(storeId, memoryId, { content, precondition });
client.beta.memoryStores.memories.list(storeId, { path_prefix, depth, order_by });
client.beta.memoryStores.memories.delete(storeId, memoryId);

client.beta.memoryStores.memoryVersions.list(storeId, { memory_id });
client.beta.memoryStores.memoryVersions.retrieve(storeId, versionId);
client.beta.memoryStores.memoryVersions.redact(storeId, versionId);

client.beta.vaults.create({ display_name, metadata });
client.beta.vaults.retrieve(vaultId);
client.beta.vaults.list();
client.beta.vaults.archive(vaultId);
client.beta.vaults.delete(vaultId);

client.beta.vaults.credentials.create(vaultId, { display_name, auth });
client.beta.vaults.credentials.update(vaultId, credId, { auth });
client.beta.vaults.credentials.archive(vaultId, credId);
client.beta.vaults.credentials.delete(vaultId, credId);

client.beta.files.upload({ file: fileBlob });
client.beta.files.list({ scope_id });
client.beta.files.download(fileId);

client.beta.webhooks.unwrap(rawBody, { headers });
```

## End-to-end example

```ts
import Anthropic from "@anthropic-ai/sdk";
import fs from "node:fs";

const client = new Anthropic();

const agent = await client.beta.agents.create({
  name: "Data Analyst",
  model: "claude-opus-4-7",
  system: "You are a data analyst. Use pandas. Be concise.",
  tools: [{ type: "agent_toolset_20260401" }],
  skills: [{ type: "anthropic", skill_id: "xlsx" }],
});

const env = await client.beta.environments.create({
  name: "data-analysis",
  config: {
    type: "cloud",
    packages: { pip: ["pandas==2.2.0", "numpy"] },
    networking: { type: "limited", allowed_hosts: ["api.example.com"] },
  },
});

const file = await client.beta.files.upload({
  file: fs.createReadStream("sales.csv"),
});

const session = await client.beta.sessions.create({
  agent: { type: "agent", id: agent.id, version: agent.version },
  environment_id: env.id,
  resources: [
    { type: "file", file_id: file.id, mount_path: "/workspace/sales.csv" },
  ],
  title: "Q1 sales analysis",
});

// OPEN STREAM FIRST. Otherwise the first event is lost.
const stream = client.beta.sessions.events.stream(session.id);

await client.beta.sessions.events.send(session.id, {
  events: [{
    type: "user.message",
    content: [{ type: "text", text: "Summarize Q1 sales by region. Write q1.xlsx to /mnt/session/outputs/." }],
  }],
});

for await (const event of stream) {
  switch (event.type) {
    case "agent.message":
      for (const block of event.content) {
        if (block.type === "text") console.log(block.text);
      }
      break;

    case "agent.custom_tool_use": {
      const result = await runMyTool(event.name, event.input);
      await client.beta.sessions.events.send(session.id, {
        events: [{
          type: "user.custom_tool_result",
          custom_tool_use_id: event.tool_use_id,
          content: [{ type: "text", text: result }],
        }],
      });
      break;
    }

    case "session.status_idle":
      if (event.stop_reason.type === "end_turn") return;
      break;

    case "session.error":
      console.error("ERR:", event.error);
      break;
  }
}
```

## Webhook verification (Next.js route handler)

```ts
import Anthropic from "@anthropic-ai/sdk";
const client = new Anthropic();

export async function POST(request: Request) {
  const raw = await request.text();
  const headers = Object.fromEntries(request.headers);

  let event;
  try {
    event = client.beta.webhooks.unwrap(raw, { headers });
  } catch {
    return new Response("invalid signature", { status: 401 });
  }

  if (event.data.type === "session.status_idled") {
    const session = await client.beta.sessions.retrieve(event.data.id);
    // …
  }

  return new Response("ok");
}
```

`unwrap` throws on invalid signature or stale payload (>5 minutes). Set the `ANTHROPIC_WEBHOOK_SIGNING_KEY` env var.

## Type imports

```ts
import type {
  AgentCreateParams,
  Session,
  SessionEvent,
  AgentMessageEvent,
  SessionStatusIdleEvent,
} from "@anthropic-ai/sdk/resources/beta";
```

The SDK's generated types follow the JSON shapes documented in [`build.md`](build.md) and [`test.md`](test.md).

## Error handling

```ts
import { APIError, RateLimitError } from "@anthropic-ai/sdk";

try {
  await client.beta.sessions.create({ agent, environment_id });
} catch (err) {
  if (err instanceof RateLimitError) { /* back off */ }
  else if (err instanceof APIError && err.status === 409) { /* concurrency conflict */ }
  else throw err;
}
```

## Common gotchas in TS

- The Memory Store path uses **camelCase** in TS: `client.beta.memoryStores.*` (Python uses `memory_stores`).
- `stream()` returns an `AsyncIterable` — use `for await`.
- The `agent` field on `sessions.create` accepts either a string (latest version) or an object `{ type: "agent", id, version }`.
- File uploads: pass a `ReadStream` or a `Blob`. `Buffer` works too but stream is preferred for large files.
