# Connectors

Connectors (`src/spine/connectors.py`) adapt external services to the
spine behind one contract, `MCPConnector`:

- `declare_capabilities() -> list[ToolDef]` — the tools offered.
- `execute(tool, params) -> ConnectorResult` — real HTTP via httpx;
  `success` follows the HTTP status (e.g. ServiceNow incident creation
  succeeds only on 201). `execute` never raises for service errors;
  failures return `success=False` with an error.
- `health_check() -> bool` — a real probe request; False on any
  failure.

| Connector | Service | Tools |
|---|---|---|
| `GitHubConnector` | GitHub | list_repos, create_issue, list_issues |
| `AzureDevOpsConnector` | Azure DevOps | list_work_items, create_work_item, list_repos |
| `JiraConnector` | Jira | search_issues, create_issue, list_projects |
| `ServiceNowConnector` | ServiceNow | list_incidents, create_incident, get_cmdb_ci |
| `DatabricksConnector` | Databricks | list_clusters, execute_sql, list_jobs |
| `ConfluenceConnector` | Confluence | get_page, create_page, search_pages |

All six are exported from the `spine` package. Registration is by
import — there is no plugin auto-discovery (it is on the roadmap).

Tests: `tests/test_connectors.py` (per-connector behavior, including
the Confluence get_page-by-id regression) and
`tests/test_connectors_sweep.py` (every declared tool on every
connector, success and 500 paths, through a mocked httpx layer).
