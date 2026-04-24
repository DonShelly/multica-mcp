#!/usr/bin/env node
/**
 * Multica MCP Server
 *
 * Exposes the Multica agent platform (issues, comments, workspaces, agents,
 * autopilots) as MCP tools by shelling out to the authenticated `multica` CLI.
 *
 * Assumes `multica` is on PATH and `multica login` has been completed for the
 * user or profile that will run this server.
 */

import { spawn } from "node:child_process";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const MULTICA_BIN = process.env.MULTICA_BIN || "multica";
const MULTICA_PROFILE = process.env.MULTICA_PROFILE || "";
const DEFAULT_WORKSPACE_ID = process.env.MULTICA_WORKSPACE_ID || "";

/**
 * Run the multica CLI with the given args. Returns stdout on success or throws
 * an Error whose message includes stderr. If `parseJson` is true and stdout
 * looks like JSON, the parsed value is returned; otherwise the raw string.
 */
function runMultica(args, { parseJson = true, workspaceId = "" } = {}) {
  const finalArgs = [];
  if (MULTICA_PROFILE) finalArgs.push("--profile", MULTICA_PROFILE);
  const ws = workspaceId || DEFAULT_WORKSPACE_ID;
  if (ws) finalArgs.push("--workspace-id", ws);
  finalArgs.push(...args);

  return new Promise((resolve, reject) => {
    const child = spawn(MULTICA_BIN, finalArgs, {
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (b) => (stdout += b.toString()));
    child.stderr.on("data", (b) => (stderr += b.toString()));
    child.on("error", (err) => reject(err));
    child.on("close", (code) => {
      if (code !== 0) {
        const msg = stderr.trim() || stdout.trim() || `exit code ${code}`;
        reject(new Error(`multica ${finalArgs.join(" ")}\n${msg}`));
        return;
      }
      if (!parseJson) return resolve(stdout);
      const trimmed = stdout.trim();
      if (!trimmed) return resolve(null);
      try {
        resolve(JSON.parse(trimmed));
      } catch {
        resolve(trimmed);
      }
    });
  });
}

/** Format a value as the text content an MCP tool response expects. */
function ok(value) {
  const text =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return { content: [{ type: "text", text }] };
}

/** Format a CLI error for an MCP tool response. */
function fail(err) {
  return {
    isError: true,
    content: [
      {
        type: "text",
        text: String(err?.message ?? err),
      },
    ],
  };
}

/** Wrap a tool handler so thrown errors become MCP error responses. */
function tool(fn) {
  return async (args) => {
    try {
      return await fn(args);
    } catch (err) {
      return fail(err);
    }
  };
}

const server = new McpServer({
  name: "multica-mcp",
  version: "0.1.0",
});

// ─── Issues ──────────────────────────────────────────────────────────────────

server.tool(
  "issue_get",
  "Fetch full details of a single Multica issue by its UUID.",
  {
    issue_id: z.string().describe("UUID of the issue"),
    workspace_id: z
      .string()
      .optional()
      .describe("Optional workspace UUID override"),
  },
  tool(async ({ issue_id, workspace_id }) => {
    const data = await runMultica(
      ["issue", "get", issue_id, "--output", "json"],
      { workspaceId: workspace_id },
    );
    return ok(data);
  }),
);

server.tool(
  "issue_list",
  "List issues in the active workspace. Supports status/priority/assignee filters and pagination.",
  {
    status: z
      .enum(["todo", "in_progress", "in_review", "done", "blocked", "backlog", "cancelled"])
      .optional()
      .describe("Filter by status"),
    priority: z
      .enum(["none", "low", "medium", "high", "urgent"])
      .optional()
      .describe("Filter by priority"),
    assignee: z
      .string()
      .optional()
      .describe("Filter by assignee name or UUID"),
    limit: z.number().int().positive().optional().describe("Max results (default 50)"),
    offset: z.number().int().nonnegative().optional().describe("Pagination offset"),
    workspace_id: z.string().optional(),
  },
  tool(async ({ status, priority, assignee, limit, offset, workspace_id }) => {
    const args = ["issue", "list", "--output", "json"];
    if (status) args.push("--status", status);
    if (priority) args.push("--priority", priority);
    if (assignee) args.push("--assignee", assignee);
    if (limit != null) args.push("--limit", String(limit));
    if (offset != null) args.push("--offset", String(offset));
    const data = await runMultica(args, { workspaceId: workspace_id });
    return ok(data);
  }),
);

server.tool(
  "issue_search",
  "Search issues by title or description text.",
  {
    query: z.string().min(1).describe("Search query string"),
    include_closed: z
      .boolean()
      .optional()
      .describe("If true, include done/cancelled issues"),
    limit: z.number().int().positive().optional(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ query, include_closed, limit, workspace_id }) => {
    const args = ["issue", "search", query, "--output", "json"];
    if (include_closed) args.push("--include-closed");
    if (limit != null) args.push("--limit", String(limit));
    const data = await runMultica(args, { workspaceId: workspace_id });
    return ok(data);
  }),
);

server.tool(
  "issue_create",
  "Create a new issue in the workspace.",
  {
    title: z.string().min(1),
    description: z.string().optional(),
    priority: z.enum(["none", "low", "medium", "high", "urgent"]).optional(),
    assignee: z.string().optional().describe("Name or UUID of assignee"),
    parent: z.string().optional().describe("UUID of parent issue"),
    status: z
      .enum(["todo", "in_progress", "in_review", "done", "blocked", "backlog"])
      .optional(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ title, description, priority, assignee, parent, status, workspace_id }) => {
    const args = ["issue", "create", "--title", title, "--output", "json"];
    if (description) args.push("--description", description);
    if (priority) args.push("--priority", priority);
    if (assignee) args.push("--assignee", assignee);
    if (parent) args.push("--parent", parent);
    if (status) args.push("--status", status);
    const data = await runMultica(args, { workspaceId: workspace_id });
    return ok(data);
  }),
);

server.tool(
  "issue_update",
  "Update fields on an existing issue. Pass only the fields you want to change.",
  {
    issue_id: z.string(),
    title: z.string().optional(),
    description: z.string().optional(),
    priority: z.enum(["none", "low", "medium", "high", "urgent"]).optional(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ issue_id, title, description, priority, workspace_id }) => {
    const args = ["issue", "update", issue_id];
    if (title != null) args.push("--title", title);
    if (description != null) args.push("--description", description);
    if (priority) args.push("--priority", priority);
    const data = await runMultica(args, { workspaceId: workspace_id, parseJson: false });
    return ok(data);
  }),
);

server.tool(
  "issue_status",
  "Change the status of an issue (todo, in_progress, in_review, done, blocked).",
  {
    issue_id: z.string(),
    status: z.enum([
      "todo",
      "in_progress",
      "in_review",
      "done",
      "blocked",
      "backlog",
      "cancelled",
    ]),
    workspace_id: z.string().optional(),
  },
  tool(async ({ issue_id, status, workspace_id }) => {
    const data = await runMultica(["issue", "status", issue_id, status], {
      workspaceId: workspace_id,
      parseJson: false,
    });
    return ok(data.trim());
  }),
);

server.tool(
  "issue_assign",
  "Assign an issue to a member or agent by name. Use unassign=true to clear the assignee.",
  {
    issue_id: z.string(),
    assignee: z.string().optional().describe("Name or UUID of assignee"),
    unassign: z.boolean().optional(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ issue_id, assignee, unassign, workspace_id }) => {
    const args = ["issue", "assign", issue_id];
    if (unassign) {
      args.push("--unassign");
    } else if (assignee) {
      args.push("--to", assignee);
    } else {
      throw new Error("Provide either `assignee` or `unassign=true`.");
    }
    const data = await runMultica(args, { workspaceId: workspace_id, parseJson: false });
    return ok(data.trim());
  }),
);

server.tool(
  "issue_runs",
  "List execution runs (agent task runs) for an issue.",
  {
    issue_id: z.string(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ issue_id, workspace_id }) => {
    const data = await runMultica(
      ["issue", "runs", issue_id, "--output", "json"],
      { workspaceId: workspace_id },
    );
    return ok(data);
  }),
);

// ─── Comments ────────────────────────────────────────────────────────────────

server.tool(
  "issue_comment_list",
  "List comments on an issue. Supports pagination and incremental fetch by `since` timestamp.",
  {
    issue_id: z.string(),
    limit: z.number().int().positive().optional(),
    offset: z.number().int().nonnegative().optional(),
    since: z.string().optional().describe("RFC3339 timestamp; only return comments after this time"),
    workspace_id: z.string().optional(),
  },
  tool(async ({ issue_id, limit, offset, since, workspace_id }) => {
    const args = ["issue", "comment", "list", issue_id, "--output", "json"];
    if (limit != null) args.push("--limit", String(limit));
    if (offset != null) args.push("--offset", String(offset));
    if (since) args.push("--since", since);
    const data = await runMultica(args, { workspaceId: workspace_id });
    return ok(data);
  }),
);

server.tool(
  "issue_comment_add",
  "Post a comment on an issue. Use parent_id to reply to an existing comment.",
  {
    issue_id: z.string(),
    content: z.string().min(1),
    parent_id: z.string().optional(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ issue_id, content, parent_id, workspace_id }) => {
    const args = ["issue", "comment", "add", issue_id, "--content", content];
    if (parent_id) args.push("--parent", parent_id);
    const data = await runMultica(args, { workspaceId: workspace_id, parseJson: false });
    return ok(data.trim());
  }),
);

server.tool(
  "issue_comment_delete",
  "Delete a comment by its UUID.",
  {
    comment_id: z.string(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ comment_id, workspace_id }) => {
    const data = await runMultica(
      ["issue", "comment", "delete", comment_id],
      { workspaceId: workspace_id, parseJson: false },
    );
    return ok(data.trim());
  }),
);

// ─── Workspace ───────────────────────────────────────────────────────────────

server.tool(
  "workspace_get",
  "Get details of the active workspace.",
  {
    workspace_id: z.string().optional(),
  },
  tool(async ({ workspace_id }) => {
    const data = await runMultica(["workspace", "get", "--output", "json"], {
      workspaceId: workspace_id,
    });
    return ok(data);
  }),
);

server.tool(
  "workspace_members",
  "List members of the workspace (humans and agents with their IDs).",
  {
    workspace_id: z.string().optional(),
  },
  tool(async ({ workspace_id }) => {
    const data = await runMultica(
      ["workspace", "members", "--output", "json"],
      { workspaceId: workspace_id },
    );
    return ok(data);
  }),
);

// ─── Agents ──────────────────────────────────────────────────────────────────

server.tool(
  "agent_list",
  "List agents available in the workspace.",
  {
    workspace_id: z.string().optional(),
  },
  tool(async ({ workspace_id }) => {
    const data = await runMultica(["agent", "list", "--output", "json"], {
      workspaceId: workspace_id,
    });
    return ok(data);
  }),
);

// ─── Autopilots ──────────────────────────────────────────────────────────────

server.tool(
  "autopilot_list",
  "List autopilots (scheduled/triggered agent automations) in the workspace.",
  {
    status: z.enum(["active", "paused"]).optional(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ status, workspace_id }) => {
    const args = ["autopilot", "list", "--output", "json"];
    if (status) args.push("--status", status);
    const data = await runMultica(args, { workspaceId: workspace_id });
    return ok(data);
  }),
);

server.tool(
  "autopilot_get",
  "Get full details for an autopilot, including its triggers.",
  {
    autopilot_id: z.string(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ autopilot_id, workspace_id }) => {
    const data = await runMultica(
      ["autopilot", "get", autopilot_id, "--output", "json"],
      { workspaceId: workspace_id },
    );
    return ok(data);
  }),
);

server.tool(
  "autopilot_trigger",
  "Manually trigger an autopilot to run once immediately.",
  {
    autopilot_id: z.string(),
    workspace_id: z.string().optional(),
  },
  tool(async ({ autopilot_id, workspace_id }) => {
    const data = await runMultica(
      ["autopilot", "trigger", autopilot_id],
      { workspaceId: workspace_id, parseJson: false },
    );
    return ok(data.trim());
  }),
);

// ─── Boot ────────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
