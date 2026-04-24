# multica-mcp

Model Context Protocol server for the [Multica](https://github.com/DonShelly/multica) agent platform.

Exposes issues, comments, workspaces, agents, and autopilots as MCP tools so any MCP-compatible client (Claude Desktop, Claude Code, Cursor, Zed, …) can drive Multica without learning the `multica` CLI.

Implementation is a thin stdio wrapper around the already-authenticated `multica` CLI, so it inherits your login and tracks the CLI's feature set automatically.

## Install

```bash
npm install -g multica-mcp
```

Or run directly with `npx multica-mcp`.

## Prerequisites

1. `multica` CLI installed and on `PATH` (`multica --version`).
2. `multica login` completed for the profile the server will use.

## Configure your MCP client

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "multica": {
      "command": "npx",
      "args": ["-y", "multica-mcp"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add multica npx -y multica-mcp
```

### Environment variables

| Variable               | Purpose                                                    |
| ---------------------- | ---------------------------------------------------------- |
| `MULTICA_BIN`          | Path to the `multica` binary (default: `multica` on PATH). |
| `MULTICA_PROFILE`      | CLI profile name, passed as `--profile`.                   |
| `MULTICA_WORKSPACE_ID` | Default workspace UUID (tools can override per-call).      |

## Tools exposed

### Issues
- `issue_get` — Fetch a single issue by UUID.
- `issue_list` — List issues with `status` / `priority` / `assignee` filters + pagination.
- `issue_search` — Full-text search across titles and descriptions.
- `issue_create` — Create a new issue with optional assignee, priority, parent, status.
- `issue_update` — Update title / description / priority on an existing issue.
- `issue_status` — Change status (`todo`, `in_progress`, `in_review`, `done`, `blocked`, `backlog`, `cancelled`).
- `issue_assign` — Assign to a member/agent by name, or clear the assignee.
- `issue_runs` — List agent execution runs for an issue.

### Comments
- `issue_comment_list` — List comments on an issue (pagination + incremental `since`).
- `issue_comment_add` — Post a comment, optionally as a reply.
- `issue_comment_delete` — Delete a comment by UUID.

### Workspace
- `workspace_get` — Details of the active workspace.
- `workspace_members` — List humans + agents with their IDs (useful for mentions / assignment).

### Agents
- `agent_list` — List agents in the workspace.

### Autopilots
- `autopilot_list` — List autopilots (optionally filtered by `active` / `paused`).
- `autopilot_get` — Full details for an autopilot including its triggers.
- `autopilot_trigger` — Manually fire an autopilot once.

All tools accept an optional `workspace_id` to target a workspace other than the CLI default.

## Development

```bash
npm install
npm test   # spawns the server, connects an MCP client, smokes workspace_get + issue_list
```

The server speaks stdio; for manual inspection you can pipe raw JSON-RPC frames to `node server.js`, but the test harness is easier.

## Why a CLI wrapper?

- Auth is already solved: whatever `multica login` gave the user carries through.
- New CLI features become available without a code change here.
- No duplication of the Multica HTTP API surface or token lifecycle.

If upstream adds native MCP support to the Multica server itself, this package should be retired in favour of that.

## License

MIT
