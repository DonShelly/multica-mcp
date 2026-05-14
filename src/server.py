#!/usr/bin/env python3
"""
Multica MCP Server
==================
A FastMCP server that exposes the Multica agent platform as MCP tools.
Designed for deployment on Render.com and connection to Poke (interaction.co/mcp).

Required environment variables:
    MULTICA_TOKEN          Bearer token from `multica auth status` (the mul_... value)
    MULTICA_WORKSPACE_ID   UUID of the workspace to operate in

Optional environment variables:
    MULTICA_SERVER_URL   Default: https://api.multica.ai
    MCP_API_KEY          API key that clients must present (Bearer or X-API-Key header).
                         If unset, the server accepts all requests (not recommended).
    POKE_API_KEY         API key for poke_send_message (from poke.com/settings/advanced)
    PORT                 HTTP port (default: 8000)
    ENVIRONMENT          Tag shown in get_server_info (default: production)
"""

import os
from typing import Any, Optional

import httpx
import uvicorn
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

# ─── Configuration ────────────────────────────────────────────────────────────

MULTICA_TOKEN = os.environ.get("MULTICA_TOKEN", "")
MULTICA_WORKSPACE_ID = os.environ.get("MULTICA_WORKSPACE_ID", "")
MULTICA_SERVER_URL = os.environ.get("MULTICA_SERVER_URL", "https://api.multica.ai").rstrip("/")
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")
POKE_API_KEY = os.environ.get("POKE_API_KEY", "")


# ─── API key authentication middleware ────────────────────────────────────────

class ApiKeyAuth(BaseHTTPMiddleware):
    """Reject requests that do not present the configured MCP_API_KEY.

    Clients may send the key as:
      Authorization: Bearer <key>
      X-API-Key: <key>

    If MCP_API_KEY is not set the middleware passes all requests through,
    so existing deployments without the env var keep working until it is set.
    """

    async def dispatch(self, request: Request, call_next):
        if not MCP_API_KEY:
            return await call_next(request)

        provided = ""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[len("Bearer "):]
        if not provided:
            provided = request.headers.get("X-API-Key", "")

        if provided != MCP_API_KEY:
            return JSONResponse(
                {"error": "Unauthorized", "message": "A valid MCP_API_KEY is required."},
                status_code=401,
            )
        return await call_next(request)

# ─── HTTP client helpers ───────────────────────────────────────────────────────

def _headers(workspace_id: Optional[str] = None) -> dict[str, str]:
    """Build request headers with auth and workspace context."""
    if not MULTICA_TOKEN:
        raise RuntimeError(
            "MULTICA_TOKEN environment variable is required. "
            "Get it from `multica auth status` (the mul_... value) and set it in Render."
        )
    ws = workspace_id or MULTICA_WORKSPACE_ID
    if not ws:
        raise RuntimeError(
            "MULTICA_WORKSPACE_ID environment variable is required. "
            "Set it to your workspace UUID in Render."
        )
    return {
        "Authorization": f"Bearer {MULTICA_TOKEN}",
        "X-Workspace-ID": ws,
        "Content-Type": "application/json",
    }


def _api(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    workspace_id: Optional[str] = None,
) -> Any:
    """Synchronous HTTP call to the Multica API. Returns parsed JSON or None."""
    url = f"{MULTICA_SERVER_URL}{path}"
    # Remove None values from params
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    with httpx.Client(timeout=30.0) as client:
        resp = client.request(
            method,
            url,
            headers=_headers(workspace_id),
            params=clean_params or None,
            json=json_body,
        )
    if resp.status_code >= 400:
        try:
            err = resp.json()
            msg = err.get("error") or err.get("message") or resp.text
        except Exception:
            msg = resp.text
        raise RuntimeError(f"{method} {path} → {resp.status_code}: {msg}")
    if not resp.content or resp.status_code == 204:
        return None
    return resp.json()


# ─── Server ───────────────────────────────────────────────────────────────────

mcp = FastMCP("Multica MCP Server")


# ─── Meta ─────────────────────────────────────────────────────────────────────

@mcp.tool(description="Get information about this MCP server and the connected Multica workspace.")
def get_server_info() -> dict:
    return {
        "server": "multica-mcp",
        "version": "0.3.0",
        "environment": os.environ.get("ENVIRONMENT", "production"),
        "multica_server_url": MULTICA_SERVER_URL,
        "workspace_id": MULTICA_WORKSPACE_ID or "(not set)",
        "api_key_auth": bool(MCP_API_KEY),
        "poke_enabled": bool(POKE_API_KEY),
    }


# ─── Issues ───────────────────────────────────────────────────────────────────

@mcp.tool(description="Fetch full details of a single Multica issue by its UUID.")
def issue_get(issue_id: str, workspace_id: Optional[str] = None) -> dict:
    return _api("GET", f"/api/issues/{issue_id}", workspace_id=workspace_id)


@mcp.tool(
    description=(
        "List issues in the workspace. Filter by status, priority, or assignee. "
        "Use limit/offset for pagination. The response includes `issues`, `total`, and `has_more`."
    )
)
def issue_list(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    """
    status: todo | in_progress | in_review | done | blocked | backlog | cancelled
    priority: none | low | medium | high | urgent
    assignee: name or UUID of assignee member/agent
    """
    return _api(
        "GET",
        "/api/issues",
        params={
            "status": status,
            "priority": priority,
            "assignee": assignee,
            "limit": limit,
            "offset": offset,
        },
        workspace_id=workspace_id,
    )


@mcp.tool(
    description=(
        "Search issues by title or description text. "
        "Supports identifier lookups (e.g. 'ELS-91') and bare numbers."
    )
)
def issue_search(
    query: str,
    include_closed: Optional[bool] = None,
    limit: Optional[int] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    return _api(
        "GET",
        "/api/issues/search",
        params={
            "q": query,
            "include_closed": "true" if include_closed else None,
            "limit": limit,
        },
        workspace_id=workspace_id,
    )


@mcp.tool(description="Create a new issue in the workspace.")
def issue_create(
    title: str,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    assignee_id: Optional[str] = None,
    assignee_type: Optional[str] = None,
    parent_issue_id: Optional[str] = None,
    status: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    """
    priority: none | low | medium | high | urgent
    assignee_type: member | agent
    status: todo | in_progress | in_review | done | blocked | backlog
    """
    body: dict = {"title": title}
    if description is not None:
        body["description"] = description
    if priority:
        body["priority"] = priority
    if assignee_id:
        body["assignee_id"] = assignee_id
    if assignee_type:
        body["assignee_type"] = assignee_type
    if parent_issue_id:
        body["parent_issue_id"] = parent_issue_id
    if status:
        body["status"] = status
    return _api("POST", "/api/issues", json_body=body, workspace_id=workspace_id)


@mcp.tool(description="Update fields on an existing issue. Only pass fields you want to change.")
def issue_update(
    issue_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    assignee_type: Optional[str] = None,
    parent_issue_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    body: dict = {}
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if priority is not None:
        body["priority"] = priority
    if status is not None:
        body["status"] = status
    if assignee_id is not None:
        body["assignee_id"] = assignee_id
    if assignee_type is not None:
        body["assignee_type"] = assignee_type
    if parent_issue_id is not None:
        body["parent_issue_id"] = parent_issue_id
    return _api("PUT", f"/api/issues/{issue_id}", json_body=body, workspace_id=workspace_id)


@mcp.tool(
    description=(
        "Change the status of an issue. "
        "Valid values: todo, in_progress, in_review, done, blocked, backlog, cancelled."
    )
)
def issue_status(issue_id: str, status: str, workspace_id: Optional[str] = None) -> dict:
    return _api(
        "PUT",
        f"/api/issues/{issue_id}",
        json_body={"status": status},
        workspace_id=workspace_id,
    )


@mcp.tool(
    description=(
        "Assign an issue to a member or agent. "
        "Provide assignee_id (UUID) and assignee_type ('member' or 'agent'). "
        "To clear the assignee, pass assignee_id=null and assignee_type=null."
    )
)
def issue_assign(
    issue_id: str,
    assignee_id: Optional[str] = None,
    assignee_type: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    return _api(
        "PUT",
        f"/api/issues/{issue_id}",
        json_body={"assignee_id": assignee_id, "assignee_type": assignee_type},
        workspace_id=workspace_id,
    )


@mcp.tool(description="Delete an issue permanently.")
def issue_delete(issue_id: str, workspace_id: Optional[str] = None) -> dict:
    _api("DELETE", f"/api/issues/{issue_id}", workspace_id=workspace_id)
    return {"deleted": True, "issue_id": issue_id}


@mcp.tool(description="List all agent execution runs (task runs) for an issue.")
def issue_runs(issue_id: str, workspace_id: Optional[str] = None) -> list:
    return _api("GET", f"/api/issues/{issue_id}/task-runs", workspace_id=workspace_id) or []


@mcp.tool(description="List child issues of a parent issue.")
def issue_children(issue_id: str, workspace_id: Optional[str] = None) -> list:
    return _api("GET", f"/api/issues/{issue_id}/children", workspace_id=workspace_id) or []


# ─── Comments ─────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "List comments on an issue with optional pagination. "
        "Pass `since` (RFC3339 timestamp) to fetch only comments after that time."
    )
)
def issue_comment_list(
    issue_id: str,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    since: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> list:
    return _api(
        "GET",
        f"/api/issues/{issue_id}/comments",
        params={"limit": limit, "offset": offset, "since": since},
        workspace_id=workspace_id,
    ) or []


@mcp.tool(
    description=(
        "Post a comment on an issue. "
        "Use parent_id to reply to an existing comment (creates a thread)."
    )
)
def issue_comment_add(
    issue_id: str,
    content: str,
    parent_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    body: dict = {"content": content}
    if parent_id:
        body["parent_id"] = parent_id
    return _api(
        "POST", f"/api/issues/{issue_id}/comments", json_body=body, workspace_id=workspace_id
    )


@mcp.tool(description="Update the text of an existing comment.")
def issue_comment_update(
    comment_id: str, content: str, workspace_id: Optional[str] = None
) -> dict:
    return _api(
        "PUT",
        f"/api/comments/{comment_id}",
        json_body={"content": content},
        workspace_id=workspace_id,
    )


@mcp.tool(description="Delete a comment by its UUID.")
def issue_comment_delete(comment_id: str, workspace_id: Optional[str] = None) -> dict:
    _api("DELETE", f"/api/comments/{comment_id}", workspace_id=workspace_id)
    return {"deleted": True, "comment_id": comment_id}


# ─── Issue subscribers ────────────────────────────────────────────────────────

@mcp.tool(description="List subscribers of an issue.")
def issue_subscriber_list(issue_id: str, workspace_id: Optional[str] = None) -> list:
    return _api("GET", f"/api/issues/{issue_id}/subscribers", workspace_id=workspace_id) or []


@mcp.tool(description="Subscribe to an issue to receive notifications.")
def issue_subscribe(issue_id: str, workspace_id: Optional[str] = None) -> dict:
    return _api("POST", f"/api/issues/{issue_id}/subscribe", workspace_id=workspace_id) or {}


@mcp.tool(description="Unsubscribe from an issue.")
def issue_unsubscribe(issue_id: str, workspace_id: Optional[str] = None) -> dict:
    return _api("POST", f"/api/issues/{issue_id}/unsubscribe", workspace_id=workspace_id) or {}


# ─── Workspace ────────────────────────────────────────────────────────────────

@mcp.tool(description="Get details of the active workspace (name, ID, settings).")
def workspace_get(workspace_id: Optional[str] = None) -> dict:
    ws = workspace_id or MULTICA_WORKSPACE_ID
    return _api("GET", f"/api/workspaces/{ws}", workspace_id=workspace_id)


@mcp.tool(
    description=(
        "List members of the workspace including both humans and agents with their UUIDs. "
        "Use these UUIDs for issue assignment and mentions."
    )
)
def workspace_members(workspace_id: Optional[str] = None) -> list:
    ws = workspace_id or MULTICA_WORKSPACE_ID
    return _api("GET", f"/api/workspaces/{ws}/members", workspace_id=workspace_id) or []


# ─── Agents ───────────────────────────────────────────────────────────────────

@mcp.tool(description="List all agents in the workspace.")
def agent_list(workspace_id: Optional[str] = None) -> list:
    return _api("GET", "/api/agents", workspace_id=workspace_id) or []


@mcp.tool(description="Get full details for a specific agent by UUID.")
def agent_get(agent_id: str, workspace_id: Optional[str] = None) -> dict:
    return _api("GET", f"/api/agents/{agent_id}", workspace_id=workspace_id)


@mcp.tool(description="List tasks/runs assigned to a specific agent.")
def agent_tasks(agent_id: str, workspace_id: Optional[str] = None) -> list:
    return _api("GET", f"/api/agents/{agent_id}/tasks", workspace_id=workspace_id) or []


# ─── Autopilots ───────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "List autopilots (scheduled/triggered agent automations) in the workspace. "
        "Filter by status: 'active' or 'paused'."
    )
)
def autopilot_list(status: Optional[str] = None, workspace_id: Optional[str] = None) -> list:
    result = _api("GET", "/api/autopilots", params={"status": status}, workspace_id=workspace_id)
    # API returns {"autopilots": [...], "total": N}
    if isinstance(result, dict) and "autopilots" in result:
        return result["autopilots"]
    return result or []


@mcp.tool(description="Get full details for an autopilot including its trigger schedule.")
def autopilot_get(autopilot_id: str, workspace_id: Optional[str] = None) -> dict:
    return _api("GET", f"/api/autopilots/{autopilot_id}", workspace_id=workspace_id)


@mcp.tool(description="Manually trigger an autopilot to run once immediately.")
def autopilot_trigger(autopilot_id: str, workspace_id: Optional[str] = None) -> dict:
    return _api("POST", f"/api/autopilots/{autopilot_id}/trigger", workspace_id=workspace_id) or {
        "triggered": True,
        "autopilot_id": autopilot_id,
    }


@mcp.tool(description="Create a new autopilot and assign it to an agent.")
def autopilot_create(
    title: str,
    assignee_id: str,
    description: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    body: dict = {"title": title, "assignee_id": assignee_id}
    if description:
        body["description"] = description
    return _api("POST", "/api/autopilots", json_body=body, workspace_id=workspace_id)


@mcp.tool(description="Update an autopilot's title, description, or status (active/paused).")
def autopilot_update(
    autopilot_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    body: dict = {}
    if title is not None:
        body["title"] = title
    if description is not None:
        body["description"] = description
    if status is not None:
        body["status"] = status
    return _api(
        "PATCH", f"/api/autopilots/{autopilot_id}", json_body=body, workspace_id=workspace_id
    )


@mcp.tool(description="Delete an autopilot permanently.")
def autopilot_delete(autopilot_id: str, workspace_id: Optional[str] = None) -> dict:
    _api("DELETE", f"/api/autopilots/{autopilot_id}", workspace_id=workspace_id)
    return {"deleted": True, "autopilot_id": autopilot_id}


@mcp.tool(description="List execution runs/history for an autopilot.")
def autopilot_runs(autopilot_id: str, workspace_id: Optional[str] = None) -> list:
    return _api("GET", f"/api/autopilots/{autopilot_id}/runs", workspace_id=workspace_id) or []


# ─── Projects ─────────────────────────────────────────────────────────────────

@mcp.tool(description="List projects in the workspace.")
def project_list(workspace_id: Optional[str] = None) -> list:
    return _api("GET", "/api/projects", workspace_id=workspace_id) or []


@mcp.tool(description="Get a project by UUID.")
def project_get(project_id: str, workspace_id: Optional[str] = None) -> dict:
    return _api("GET", f"/api/projects/{project_id}", workspace_id=workspace_id)


@mcp.tool(description="Create a new project.")
def project_create(
    title: str,
    description: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    body: dict = {"title": title}
    if description:
        body["description"] = description
    return _api("POST", "/api/projects", json_body=body, workspace_id=workspace_id)


# ─── Poke integration ─────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Send a message to Poke (poke.com) via the inbound webhook. "
        "Requires POKE_API_KEY environment variable to be configured. "
        "Use this to push Multica updates, issue notifications, or alerts into Poke."
    )
)
def poke_send_message(message: str) -> dict:
    """Send a message to Poke via the inbound SMS webhook API."""
    if not POKE_API_KEY:
        raise RuntimeError(
            "POKE_API_KEY environment variable is not set. "
            "Generate an API key at https://poke.com/settings/advanced and set it in Render."
        )
    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            "https://poke.com/api/v1/inbound-sms/webhook",
            headers={
                "Authorization": f"Bearer {POKE_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"message": message},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"Poke webhook returned {resp.status_code}: {resp.text}")
    try:
        return resp.json()
    except Exception:
        return {"status": "sent", "response": resp.text}


# ─── Server entry point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    print(f"Starting Multica MCP Server on {host}:{port}")
    print(f"  Endpoint : http://{host}:{port}/mcp  (Streamable HTTP)")
    print(f"  Workspace: {MULTICA_WORKSPACE_ID or '(not set — set MULTICA_WORKSPACE_ID)'}")
    print(f"  Token    : {'set' if MULTICA_TOKEN else '(not set — set MULTICA_TOKEN)'}")
    print(f"  API key  : {'enabled' if MCP_API_KEY else 'DISABLED (set MCP_API_KEY to enable)'}")
    print(f"  Poke     : {'enabled' if POKE_API_KEY else 'disabled (set POKE_API_KEY to enable)'}")

    app = mcp.http_app(stateless_http=True)
    app.add_middleware(ApiKeyAuth)

    uvicorn.run(app, host=host, port=port)
