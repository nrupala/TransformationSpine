# Copyright 2026 Nrupal Akolkar
# SPDX-License-Identifier: Apache-2.0
"""MCP/ACP connectors — fully built, provider-agnostic tool bindings.

Each connector wraps an external service (GitHub, Azure DevOps, Jira,
etc.) behind the spine's unified interface so the spine can dispatch
work through any channel without coupling to a specific API shape.

Connectors implement the MCP (Model Context Protocol) tool contract:
  * declare_capabilities() → what this connector can do
  * execute(tool, params) → call a tool with typed parameters
  * health_check() → is the service reachable

The spine's ProviderRouter dispatches through these connectors as
first-class mechanisms alongside LLM providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class ToolDef:
    """A callable operation this connector exposes."""

    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema for parameters
    output_schema: dict[str, Any]


@dataclass
class ConnectorResult:
    """Result of a connector operation."""

    success: bool
    tool: str
    output: Any
    error: str | None = None
    connector: str = ""
    elapsed_ms: int = 0
    id: str = field(default_factory=lambda: str(uuid4()))


class MCPConnector:
    """Base contract every MCP connector satisfies.

    Subclasses must implement declare_capabilities, execute, and
    health_check. The spine's router calls these without knowing the
    underlying service.
    """

    name: str = "base"
    service_url: str = ""

    def declare_capabilities(self) -> list[ToolDef]:
        """Return the list of tools this connector exposes."""
        raise NotImplementedError

    def execute(self, tool: str, params: dict[str, Any]) -> ConnectorResult:
        """Execute a tool with typed parameters. Returns ConnectorResult."""
        raise NotImplementedError

    def health_check(self) -> bool:
        """Is the service reachable and authenticated?"""
        raise NotImplementedError


# ── GitHub connector ────────────────────────────────────────────


class GitHubConnector(MCPConnector):
    """GitHub MCP connector — issues, PRs, repos, commits."""

    name = "github"
    service_url = "https://api.github.com"

    def __init__(self, token: str | None = None, base_url: str | None = None):
        self.token = token or ""
        self.service_url = base_url or self.service_url

    def declare_capabilities(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="list_repos",
                description="List repositories for the authenticated user.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": [],
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                            "full_name": {"type": "string"},
                            "html_url": {"type": "string"},
                        },
                    },
                },
            ),
            ToolDef(
                name="create_issue",
                description="Create a new issue in a repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["owner", "repo", "title"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "number": {"type": "integer"},
                        "html_url": {"type": "string"},
                        "state": {"type": "string"},
                    },
                },
            ),
            ToolDef(
                name="list_issues",
                description="List issues for a repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    },
                    "required": ["owner", "repo"],
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "number": {"type": "integer"},
                            "title": {"type": "string"},
                            "state": {"type": "string"},
                        },
                    },
                },
            ),
        ]

    def execute(self, tool: str, params: dict[str, Any]) -> ConnectorResult:
        start = __import__("time").time()
        try:
            if tool == "list_repos":
                return self._list_repos(params, start)
            elif tool == "create_issue":
                return self._create_issue(params, start)
            elif tool == "list_issues":
                return self._list_issues(params, start)
            else:
                return ConnectorResult(
                    success=False,
                    tool=tool,
                    output=None,
                    error=f"Unknown GitHub tool: {tool}",
                    connector=self.name,
                    elapsed_ms=int((__import__("time").time() - start) * 1000),
                )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool=tool,
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((__import__("time").time() - start) * 1000),
            )

    def health_check(self) -> bool:
        try:
            import httpx

            resp = httpx.get(
                f"{self.service_url}/rate_limit",
                headers={"Authorization": f"token {self.token}"} if self.token else {},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _list_repos(self, params: dict[str, Any], start: float) -> ConnectorResult:
        per_page = params.get("per_page", 30)
        headers = {"Authorization": f"token {self.token}"} if self.token else {}
        try:
            import httpx

            resp = httpx.get(
                f"{self.service_url}/user/repos",
                params={"per_page": per_page},
                headers=headers,
                timeout=30,
            )
            data = resp.json() if resp.status_code == 200 else []
            return ConnectorResult(
                success=resp.status_code == 200,
                tool="list_repos",
                output=data,
                connector=self.name,
                elapsed_ms=int((__import__("time").time() - start) * 1000),
            )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool="list_repos",
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((__import__("time").time() - start) * 1000),
            )

    def _create_issue(self, params: dict[str, Any], start: float) -> ConnectorResult:
        headers = (
            {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
            }  # noqa: E501
            if self.token
            else {}
        )
        body = {
            "title": params["title"],
            "body": params.get("body", ""),
            "state": "open",
        }  # noqa: E501
        try:
            import httpx

            resp = httpx.post(
                f"{self.service_url}/repos/{params['owner']}/{params['repo']}/issues",
                json=body,
                headers=headers,
                timeout=30,
            )
            data = resp.json() if resp.status_code == 201 else {}
            return ConnectorResult(
                success=resp.status_code == 201,
                tool="create_issue",
                output=data,
                connector=self.name,
                elapsed_ms=int((__import__("time").time() - start) * 1000),
            )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool="create_issue",
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((__import__("time").time() - start) * 1000),
            )

    def _list_issues(self, params: dict[str, Any], start: float) -> ConnectorResult:
        headers = {"Authorization": f"token {self.token}"} if self.token else {}
        try:
            import httpx

            resp = httpx.get(
                f"{self.service_url}/repos/{params['owner']}/{params['repo']}/issues",
                params={"state": params.get("state", "open")},
                headers=headers,
                timeout=30,
            )
            data = resp.json() if resp.status_code == 200 else []
            return ConnectorResult(
                success=resp.status_code == 200,
                tool="list_issues",
                output=data,
                connector=self.name,
                elapsed_ms=int((__import__("time").time() - start) * 1000),
            )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool="list_issues",
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((__import__("time").time() - start) * 1000),
            )


# ── Azure DevOps connector ──────────────────────────────────────


class AzureDevOpsConnector(MCPConnector):
    """Azure DevOps (ADO) MCP connector — work items, repos, pipelines."""

    name = "azure-devops"
    service_url = "https://dev.azure.com"

    def __init__(
        self,
        org: str = "",
        pat: str | None = None,
        base_url: str | None = None,
    ):
        self.org = org
        self.pat = pat or ""
        self.service_url = base_url or f"{self.service_url}/{self.org}"

    def declare_capabilities(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="list_work_items",
                description="List work items for the organization.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "work_item_type": {"type": "string"},
                        "top": {"type": "integer", "minimum": 1, "maximum": 200},
                    },
                    "required": ["project"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "value": {"type": "array"},
                    },
                },
            ),
            ToolDef(
                name="create_work_item",
                description="Create a new work item.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                        "work_item_type": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["project", "work_item_type", "title"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "url": {"type": "string"},
                        "fields": {"type": "object"},
                    },
                },
            ),
            ToolDef(
                name="list_repos",
                description="List repositories for a project.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project": {"type": "string"},
                    },
                    "required": ["project"],
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "web_url": {"type": "string"},
                        },
                    },
                },
            ),
        ]

    def execute(self, tool: str, params: dict[str, Any]) -> ConnectorResult:
        import time

        start = time.time()
        try:
            if tool == "list_work_items":
                return self._list_work_items(params, start)
            elif tool == "create_work_item":
                return self._create_work_item(params, start)
            elif tool == "list_repos":
                return self._list_repos(params, start)
            else:
                return ConnectorResult(
                    success=False,
                    tool=tool,
                    output=None,
                    error=f"Unknown ADO tool: {tool}",
                    connector=self.name,
                    elapsed_ms=int((time.time() - start) * 1000),
                )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool=tool,
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((time.time() - start) * 1000),
            )

    def health_check(self) -> bool:
        try:
            import httpx

            resp = httpx.get(
                f"{self.service_url}/_apis/projects",
                headers={"Authorization": f"Basic {self.pat}"},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _list_work_items(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        headers = {"Authorization": f"Basic {self.pat}"}
        url = f"{self.service_url}/_apis/wit/workitems"
        resp = httpx.get(
            url,
            params={"project": params["project"], "$top": params.get("top", 50)},
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="list_work_items",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _create_work_item(
        self, params: dict[str, Any], start: float
    ) -> ConnectorResult:  # noqa: E501
        import httpx

        headers = {
            "Authorization": f"Basic {self.pat}",
            "Content-Type": "application/json-patch+json",
        }
        body = [
            {"op": "add", "path": "/fields/System.Title", "value": params["title"]},
            {
                "op": "add",
                "path": "/fields/System.Description",
                "value": params.get("description", ""),
            },  # noqa: E501
        ]
        url = f"{self.service_url}/_apis/wit/workitems/${params['work_item_type']}?api-version=7.0"  # noqa: E501
        resp = httpx.post(url, json=body, headers=headers, timeout=30)
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="create_work_item",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _list_repos(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        headers = {"Authorization": f"Basic {self.pat}"}
        url = f"{self.service_url}/_apis/git/repositories?project={params['project']}"
        resp = httpx.get(url, headers=headers, timeout=30)
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="list_repos",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )


# ── Jira connector ──────────────────────────────────────────────


class JiraConnector(MCPConnector):
    """Jira MCP connector — issues, projects, boards."""

    name = "jira"
    service_url = "https://your-domain.atlassian.net"

    def __init__(
        self,
        email: str = "",
        api_token: str | None = None,
        base_url: str | None = None,
    ):
        self.email = email
        self.api_token = api_token or ""
        self.service_url = base_url or self.service_url

    def declare_capabilities(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="search_issues",
                description="Search Jira issues using JQL.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "jql": {"type": "string"},
                        "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "required": ["jql"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "startAt": {"type": "integer"},
                        "maxResults": {"type": "integer"},
                        "total": {"type": "integer"},
                        "issues": {"type": "array"},
                    },
                },
            ),
            ToolDef(
                name="create_issue",
                description="Create a new Jira issue.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_key": {"type": "string"},
                        "issue_type": {"type": "string"},
                        "summary": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["project_key", "issue_type", "summary"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "key": {"type": "string"},
                        "self": {"type": "string"},
                    },
                },
            ),
            ToolDef(
                name="list_projects",
                description="List all Jira projects.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "name": {"type": "string"},
                            "projectTypeKey": {"type": "string"},
                        },
                    },
                },
            ),
        ]

    def execute(self, tool: str, params: dict[str, Any]) -> ConnectorResult:
        import time

        start = time.time()
        try:
            if tool == "search_issues":
                return self._search_issues(params, start)
            elif tool == "create_issue":
                return self._create_issue(params, start)
            elif tool == "list_projects":
                return self._list_projects(params, start)
            else:
                return ConnectorResult(
                    success=False,
                    tool=tool,
                    output=None,
                    error=f"Unknown Jira tool: {tool}",
                    connector=self.name,
                    elapsed_ms=int((time.time() - start) * 1000),
                )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool=tool,
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((time.time() - start) * 1000),
            )

    def health_check(self) -> bool:
        try:
            from base64 import b64encode

            import httpx

            auth = b64encode(f"{self.email}:{self.api_token}".encode()).decode()
            resp = httpx.get(
                f"{self.service_url}/rest/api/2/myself",
                headers={"Authorization": f"Basic {auth}"},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _search_issues(self, params: dict[str, Any], start: float) -> ConnectorResult:
        from base64 import b64encode

        import httpx

        auth = b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        resp = httpx.get(
            f"{self.service_url}/rest/api/2/search",
            params={"jql": params["jql"], "maxResults": params.get("max_results", 50)},
            headers={"Authorization": f"Basic {auth}"},
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="search_issues",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _create_issue(self, params: dict[str, Any], start: float) -> ConnectorResult:
        from base64 import b64encode

        import httpx

        auth = b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        body = {
            "fields": {
                "project": {"key": params["project_key"]},
                "issuetype": {"name": params["issue_type"]},
                "summary": params["summary"],
                "description": params.get("description", ""),
            }
        }
        resp = httpx.post(
            f"{self.service_url}/rest/api/2/issue",
            json=body,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            },  # noqa: E501
            timeout=30,
        )
        data = resp.json() if resp.status_code == 201 else {}
        return ConnectorResult(
            success=resp.status_code == 201,
            tool="create_issue",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _list_projects(self, params: dict[str, Any], start: float) -> ConnectorResult:
        from base64 import b64encode

        import httpx

        auth = b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        resp = httpx.get(
            f"{self.service_url}/rest/api/2/project",
            headers={"Authorization": f"Basic {auth}"},
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else []
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="list_projects",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )


# ── ServiceNow connector ──────────────────────────────────────


class ServiceNowConnector(MCPConnector):
    """ServiceNow MCP connector — incidents, changes, CMDB, service catalog."""

    name = "servicenow"
    service_url = "https://instance.service-now.com"

    def __init__(
        self,
        instance: str = "",
        username: str = "",
        password: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.instance = instance
        self.username = username
        self.password = password or ""
        self.api_key = api_key or ""
        self.service_url = base_url or f"https://{instance}.service-now.com/api/now"

    def declare_capabilities(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="list_incidents",
                description="List incidents from ServiceNow.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                        "offset": {"type": "integer", "minimum": 0},
                    },
                    "required": [],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "total_count": {"type": "integer"},
                        "result": {"type": "array"},
                    },
                },
            ),
            ToolDef(
                name="create_incident",
                description="Create a new incident in ServiceNow.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "short_description": {"type": "string"},
                        "description": {"type": "string"},
                        "category": {"type": "string"},
                        "priority": {
                            "type": "string",
                            "enum": ["1", "2", "3", "4", "5"],
                        },  # noqa: E501
                    },
                    "required": ["short_description"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "result": {"type": "object"},
                    },
                },
            ),
            ToolDef(
                name="get_cmdb_ci",
                description="Get CI (Configuration Item) from CMDB.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "sys_id": {"type": "string"},
                    },
                    "required": ["sys_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "result": {"type": "object"},
                    },
                },
            ),
        ]

    def execute(self, tool: str, params: dict[str, Any]) -> ConnectorResult:
        import time

        start = time.time()
        try:
            if tool == "list_incidents":
                return self._list_incidents(params, start)
            elif tool == "create_incident":
                return self._create_incident(params, start)
            elif tool == "get_cmdb_ci":
                return self._get_cmdb_ci(params, start)
            else:
                return ConnectorResult(
                    success=False,
                    tool=tool,
                    output=None,
                    error=f"Unknown ServiceNow tool: {tool}",
                    connector=self.name,
                    elapsed_ms=int((time.time() - start) * 1000),
                )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool=tool,
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((time.time() - start) * 1000),
            )

    def health_check(self) -> bool:
        try:
            import httpx

            auth = None
            if self.username and self.password:
                from base64 import b64encode

                token = b64encode(f"{self.username}:{self.password}".encode()).decode()
                auth = f"Basic {token}"
            elif self.api_key:
                auth = f"Bearer {self.api_key}"

            headers = {}
            if auth:
                headers["Authorization"] = auth
            headers["Accept"] = "application/json"

            resp = httpx.get(
                f"{self.service_url}/table/incident?sysparm_limit=1",
                headers=headers,
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _list_incidents(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        limit = params.get("limit", 10)
        offset = params.get("offset", 0)

        auth = None
        if self.username and self.password:
            from base64 import b64encode

            token = b64encode(f"{self.username}:{self.password}".encode()).decode()
            auth = f"Basic {token}"
        elif self.api_key:
            auth = f"Bearer {self.api_key}"

        headers = {}
        if auth:
            headers["Authorization"] = auth
        headers["Accept"] = "application/json"

        resp = httpx.get(
            f"{self.service_url}/table/incident",
            params={"sysparm_limit": limit, "sysparm_offset": offset},
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="list_incidents",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _create_incident(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        auth = None
        if self.username and self.password:
            from base64 import b64encode

            token = b64encode(f"{self.username}:{self.password}".encode()).decode()
            auth = f"Basic {token}"
        elif self.api_key:
            auth = f"Bearer {self.api_key}"

        headers = {}
        if auth:
            headers["Authorization"] = auth
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        payload = {
            "short_description": params["short_description"],
            "description": params.get("description", ""),
            "category": params.get("category", "inquiry"),
            "priority": params.get("priority", "3"),
        }

        resp = httpx.post(
            f"{self.service_url}/table/incident",
            json=payload,
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 201 else {}
        return ConnectorResult(
            success=resp.status_code == 201,
            tool="create_incident",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _get_cmdb_ci(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        sys_id = params["sys_id"]

        auth = None
        if self.username and self.password:
            from base64 import b64encode

            token = b64encode(f"{self.username}:{self.password}".encode()).decode()
            auth = f"Basic {token}"
        elif self.api_key:
            auth = f"Bearer {self.api_key}"

        headers = {}
        if auth:
            headers["Authorization"] = auth
        headers["Accept"] = "application/json"

        resp = httpx.get(
            f"{self.service_url}/table/cmdb_ci/{sys_id}",
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="get_cmdb_ci",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )


# ── Databricks connector ──────────────────────────────────────


class DatabricksConnector(MCPConnector):
    """Databricks MCP connector — SQL endpoints, jobs, notebooks, MLflow."""

    name = "databricks"
    service_url = "https://adb-1234567890123456.17.azuredatabricks.net"

    def __init__(
        self,
        instance: str = "",
        token: str | None = None,
        base_url: str | None = None,
    ):
        self.instance = instance
        self.token = token or ""
        self.service_url = base_url or f"https://{instance}.azuredatabricks.net/api/2.0"

    def declare_capabilities(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="list_clusters",
                description="List Databricks clusters.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": [],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "clusters": {"type": "array"},
                    },
                },
            ),
            ToolDef(
                name="execute_sql",
                description="Execute SQL on a Databricks SQL endpoint.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "warehouse_id": {"type": "string"},
                    },
                    "required": ["query", "warehouse_id"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "result": {"type": "array"},
                        "schema": {"type": "object"},
                    },
                },
            ),
            ToolDef(
                name="list_jobs",
                description="List Databricks jobs.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": [],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "jobs": {"type": "array"},
                    },
                },
            ),
        ]

    def execute(self, tool: str, params: dict[str, Any]) -> ConnectorResult:
        import time

        start = time.time()
        try:
            if tool == "list_clusters":
                return self._list_clusters(params, start)
            elif tool == "execute_sql":
                return self._execute_sql(params, start)
            elif tool == "list_jobs":
                return self._list_jobs(params, start)
            else:
                return ConnectorResult(
                    success=False,
                    tool=tool,
                    output=None,
                    error=f"Unknown Databricks tool: {tool}",
                    connector=self.name,
                    elapsed_ms=int((time.time() - start) * 1000),
                )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool=tool,
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((time.time() - start) * 1000),
            )

    def health_check(self) -> bool:
        try:
            import httpx

            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            resp = httpx.get(
                f"{self.service_url}/clusters/list",
                headers=headers,
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _list_clusters(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        resp = httpx.get(
            f"{self.service_url}/clusters/list",
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="list_clusters",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _execute_sql(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        query = params["query"]
        warehouse_id = params["warehouse_id"]

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        headers["Content-Type"] = "application/json"

        payload = {
            "statement": query,
            "warehouse_id": warehouse_id,
            "wait_timeout": "30s",
        }

        resp = httpx.post(
            f"{self.service_url}/sql/statements",
            json=payload,
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="execute_sql",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _list_jobs(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        limit = params.get("limit", 25)

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        resp = httpx.get(
            f"{self.service_url}/jobs/list",
            params={"limit": limit},
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="list_jobs",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )


# ── Confluence connector ──────────────────────────────────────


class ConfluenceConnector(MCPConnector):
    """Confluence MCP connector — pages, spaces, attachments."""

    name = "confluence"
    service_url = "https://instance.atlassian.net/wiki"

    def __init__(
        self,
        instance: str = "",
        username: str = "",
        api_token: str | None = None,
        base_url: str | None = None,
    ):
        self.instance = instance
        self.username = username
        self.api_token = api_token or ""
        self.service_url = base_url or f"https://{instance}.atlassian.net/wiki"

    def declare_capabilities(self) -> list[ToolDef]:
        return [
            ToolDef(
                name="get_page",
                description="Get a Confluence page by ID or title.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string"},
                        "title": {"type": "string"},
                        "space_key": {"type": "string"},
                    },
                    "required": [],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "object"},
                        "version": {"type": "object"},
                    },
                },
            ),
            ToolDef(
                name="create_page",
                description="Create a new Confluence page.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "space_key": {"type": "string"},
                        "body": {"type": "string"},
                        "parent_id": {"type": "string"},
                    },
                    "required": ["title", "space_key", "body"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "type": {"type": "string"},
                    },
                },
            ),
            ToolDef(
                name="search_pages",
                description="Search Confluence pages using CQL.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "cql": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    },
                    "required": ["cql"],
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "results": {"type": "array"},
                        "size": {"type": "integer"},
                        "start": {"type": "integer"},
                    },
                },
            ),
        ]

    def execute(self, tool: str, params: dict[str, Any]) -> ConnectorResult:
        import time

        start = time.time()
        try:
            if tool == "get_page":
                return self._get_page(params, start)
            elif tool == "create_page":
                return self._create_page(params, start)
            elif tool == "search_pages":
                return self._search_pages(params, start)
            else:
                return ConnectorResult(
                    success=False,
                    tool=tool,
                    output=None,
                    error=f"Unknown Confluence tool: {tool}",
                    connector=self.name,
                    elapsed_ms=int((time.time() - start) * 1000),
                )
        except Exception as e:
            return ConnectorResult(
                success=False,
                tool=tool,
                output=None,
                error=str(e),
                connector=self.name,
                elapsed_ms=int((time.time() - start) * 1000),
            )

    def health_check(self) -> bool:
        try:
            import httpx

            auth = None
            if self.username and self.api_token:
                from base64 import b64encode

                token = b64encode(f"{self.username}:{self.api_token}".encode()).decode()
                auth = f"Basic {token}"

            headers = {}
            if auth:
                headers["Authorization"] = auth

            resp = httpx.get(
                f"{self.service_url}/rest/api/space",
                headers=headers,
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _get_page(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        auth = None
        if self.username and self.api_token:
            from base64 import b64encode

            token = b64encode(f"{self.username}:{self.api_token}".encode()).decode()
            auth = f"Basic {token}"

        headers = {}
        if auth:
            headers["Authorization"] = auth
        headers["Accept"] = "application/json"

        page_id = params.get("page_id")
        title = params.get("title")
        space_key = params.get("space_key")

        if page_id:
            url = f"{self.service_url}/rest/api/content/{page_id}?expand=body.storage,version"  # noqa: E501
            resp = httpx.get(url, headers=headers, timeout=30)
            data = resp.json() if resp.status_code == 200 else {}
        elif title and space_key:
            url = f"{self.service_url}/rest/api/content"
            params = {
                "title": title,
                "spaceKey": space_key,
                "expand": "body.storage,version",
            }
            resp = httpx.get(
                url,
                headers=headers,
                params=params,
                timeout=30,
            )
            data = resp.json() if resp.status_code == 200 else {}
            results = data.get("results", [])
            data = results[0] if results else {}
        else:
            data = {}

        return ConnectorResult(
            success=bool(data),
            tool="get_page",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _create_page(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        auth = None
        if self.username and self.api_token:
            from base64 import b64encode

            token = b64encode(f"{self.username}:{self.api_token}".encode()).decode()
            auth = f"Basic {token}"

        headers = {}
        if auth:
            headers["Authorization"] = auth
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        payload = {
            "type": "page",
            "title": params["title"],
            "space": {"key": params["space_key"]},
            "body": {
                "storage": {
                    "value": params["body"],
                    "representation": "storage",
                }
            },
        }

        if params.get("parent_id"):
            payload["ancestors"] = [{"id": params["parent_id"]}]

        resp = httpx.post(
            f"{self.service_url}/rest/api/content",
            json=payload,
            headers=headers,
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="create_page",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )

    def _search_pages(self, params: dict[str, Any], start: float) -> ConnectorResult:
        import httpx

        auth = None
        if self.username and self.api_token:
            from base64 import b64encode

            token = b64encode(f"{self.username}:{self.api_token}".encode()).decode()
            auth = f"Basic {token}"

        headers = {}
        if auth:
            headers["Authorization"] = auth
        headers["Accept"] = "application/json"

        cql = params["cql"]
        limit = params.get("limit", 10)

        resp = httpx.get(
            f"{self.service_url}/rest/api/content/search",
            headers=headers,
            params={"cql": cql, "limit": limit},
            timeout=30,
        )
        data = resp.json() if resp.status_code == 200 else {}
        return ConnectorResult(
            success=resp.status_code == 200,
            tool="search_pages",
            output=data,
            connector=self.name,
            elapsed_ms=int((__import__("time").time() - start) * 1000),
        )
