# multica-mcp

Model Context Protocol (MCP) server for the [Multica](https://multica.ai) agent platform.

Exposes issues, comments, workspaces, agents, autopilots, and projects as **34 MCP tools** so any MCP-compatible client can drive Multica:

- **Poke** (interaction.co) — register it as a custom integration via `poke.com/settings/connections/integrations/new`
- **Claude Desktop** — add to `claude_desktop_config.json`
- **Claude Code** — `claude mcp add multica ...`
- **Cursor, Zed, and any other MCP client**

The server uses **FastMCP with streamable HTTP transport** at `/mcp`, making it directly compatible with [Poke's MCP integration guide](https://interaction.co/mcp).

---

## Deploy to Render (Poke-compatible)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/DonShelly/multica-mcp)

1. Click **Deploy to Render** above.
2. In the Render dashboard, set these environment variables (do **not** commit secrets to git):

   | Variable               | Required | Where to get it |
   | ---------------------- | -------- | --------------- |
   | `MULTICA_TOKEN`        | ✅       | Run `multica auth status` — it's the `mul_…` value |
   | `MULTICA_WORKSPACE_ID` | ✅       | Run `multica workspace get --output json` → `id` field |
   | `POKE_API_KEY`         | optional | [poke.com/settings/advanced](https://poke.com/settings/advanced) |
   | `MULTICA_SERVER_URL`   | optional | Default: `https://api.multica.ai` |

3. After deploy, your endpoint is: `https://your-service-name.onrender.com/mcp`

### Connect to Poke

1. Go to [poke.com/settings/connections/integrations/new](https://poke.com/settings/connections/integrations/new).
2. Enter your Render URL: `https://your-service.onrender.com/mcp`
3. Ask Poke: *"Tell the subagent to use the 'multica' integration's 'issue_list' tool"* to test.

> If Poke doesn't pick up the right tool after a rename, send `clearhistory` to Poke to clear message history.

---

## Local development (stdio, Claude Desktop / Claude Code)

For local use, the original Node.js stdio server is also included.

### Setup

```bash
git clone https://github.com/DonShelly/multica-mcp
cd multica-mcp

# Python (Render/Poke):
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MULTICA_TOKEN="mul_..."
export MULTICA_WORKSPACE_ID="your-workspace-uuid"
python src/server.py
# → listening on http://0.0.0.0:8000/mcp

# Node.js (stdio, local):
npm install
node server.js
```

### Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Connect to `http://localhost:8000/mcp` using **Streamable HTTP** transport.

### Claude Desktop (stdio)

```json
{
  "mcpServers": {
    "multica": {
      "command": "node",
      "args": ["/path/to/multica-mcp/server.js"],
      "env": {
        "MULTICA_TOKEN": "mul_...",
        "MULTICA_WORKSPACE_ID": "your-workspace-uuid"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add multica node /path/to/multica-mcp/server.js
```

---

## Tools (34 total)

### Issues
| Tool | Description |
|------|-------------|
| `issue_get` | Fetch a single issue by UUID |
| `issue_list` | List issues with status/priority/assignee filters + pagination |
| `issue_search` | Full-text search across titles and descriptions |
| `issue_create` | Create a new issue |
| `issue_update` | Update title, description, priority, status, assignee |
| `issue_status` | Change status (`todo`, `in_progress`, `in_review`, `done`, `blocked`, `backlog`, `cancelled`) |
| `issue_assign` | Assign to a member or agent by UUID |
| `issue_delete` | Delete an issue permanently |
| `issue_runs` | List agent execution task-runs for an issue |
| `issue_children` | List child issues of a parent issue |

### Comments
| Tool | Description |
|------|-------------|
| `issue_comment_list` | List comments (pagination + `since` timestamp) |
| `issue_comment_add` | Post a comment, optionally as a threaded reply |
| `issue_comment_update` | Edit an existing comment |
| `issue_comment_delete` | Delete a comment by UUID |

### Subscribers
| Tool | Description |
|------|-------------|
| `issue_subscriber_list` | List subscribers of an issue |
| `issue_subscribe` | Subscribe to an issue |
| `issue_unsubscribe` | Unsubscribe from an issue |

### Workspace
| Tool | Description |
|------|-------------|
| `workspace_get` | Get workspace details |
| `workspace_members` | List humans and agents with their UUIDs |

### Agents
| Tool | Description |
|------|-------------|
| `agent_list` | List all agents |
| `agent_get` | Get details for a specific agent |
| `agent_tasks` | List tasks assigned to an agent |

### Autopilots
| Tool | Description |
|------|-------------|
| `autopilot_list` | List autopilots (filter by `active`/`paused`) |
| `autopilot_get` | Get full details including trigger schedule |
| `autopilot_trigger` | Fire an autopilot once manually |
| `autopilot_create` | Create a new autopilot |
| `autopilot_update` | Update title, description, or status |
| `autopilot_delete` | Delete an autopilot |
| `autopilot_runs` | List execution history |

### Projects
| Tool | Description |
|------|-------------|
| `project_list` | List projects |
| `project_get` | Get a project by UUID |
| `project_create` | Create a new project |

### Poke integration
| Tool | Description |
|------|-------------|
| `poke_send_message` | Send a message to Poke via the inbound webhook (requires `POKE_API_KEY`) |
| `get_server_info` | Get server version, workspace ID, and env info |

All tools accept an optional `workspace_id` parameter to override the default workspace.

---

## Architecture

```
MCP Client (Poke / Claude Desktop / Cursor)
        │ MCP protocol (Streamable HTTP or stdio)
        ▼
  multica-mcp server (FastMCP / Python)
        │ REST API calls  Authorization: Bearer {MULTICA_TOKEN}
        ▼                  X-Workspace-ID: {MULTICA_WORKSPACE_ID}
  https://api.multica.ai
```

Uses direct HTTP calls to the Multica REST API — no `multica` CLI dependency on the server, so it works on Render and any container environment.

## License

MIT
