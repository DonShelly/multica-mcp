#!/usr/bin/env node
/**
 * Smoke test for multica-mcp.
 *
 * Spawns the MCP server as a subprocess and drives it over stdio with the
 * official @modelcontextprotocol/sdk client. Verifies:
 *   1. Tool catalogue is non-empty and contains expected tools.
 *   2. A read-only tool (workspace_get) returns structured data.
 *   3. A filtered list call (issue_list with status=todo) succeeds.
 *
 * Requires an authenticated `multica` CLI on PATH.
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const serverPath = join(__dirname, "server.js");

const EXPECTED_TOOLS = [
  "issue_get",
  "issue_list",
  "issue_search",
  "issue_create",
  "issue_update",
  "issue_status",
  "issue_assign",
  "issue_comment_list",
  "issue_comment_add",
  "workspace_get",
  "workspace_members",
  "agent_list",
  "autopilot_list",
];

function assert(cond, msg) {
  if (!cond) throw new Error(`assertion failed: ${msg}`);
}

async function main() {
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [serverPath],
    env: process.env,
  });
  const client = new Client({ name: "multica-mcp-test", version: "0.0.0" });
  await client.connect(transport);

  const { tools } = await client.listTools();
  const names = new Set(tools.map((t) => t.name));
  console.log(`tools exposed (${tools.length}):`, [...names].sort().join(", "));
  for (const expected of EXPECTED_TOOLS) {
    assert(names.has(expected), `missing tool: ${expected}`);
  }

  const wsResult = await client.callTool({
    name: "workspace_get",
    arguments: {},
  });
  assert(!wsResult.isError, `workspace_get errored: ${JSON.stringify(wsResult)}`);
  const wsText = wsResult.content?.[0]?.text ?? "";
  const ws = JSON.parse(wsText);
  assert(typeof ws.id === "string" && ws.id.length > 0, "workspace_get: no id");
  console.log(`workspace_get OK — id=${ws.id} name=${ws.name ?? "(unnamed)"}`);

  const listResult = await client.callTool({
    name: "issue_list",
    arguments: { status: "todo", limit: 5 },
  });
  assert(!listResult.isError, `issue_list errored: ${JSON.stringify(listResult)}`);
  const listText = listResult.content?.[0]?.text ?? "";
  const list = JSON.parse(listText);
  assert(Array.isArray(list.issues), "issue_list: no .issues array");
  console.log(`issue_list OK — returned ${list.issues.length} todo issue(s)`);

  await client.close();
  console.log("PASS");
}

main().catch((err) => {
  console.error("FAIL:", err.message);
  process.exit(1);
});
