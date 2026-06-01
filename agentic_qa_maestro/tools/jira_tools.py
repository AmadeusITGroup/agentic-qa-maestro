"""
Native JIRA API tools for Agentic QA Maestro agents.

Uses httpx sync client for JIRA REST API operations.
Decorated with @tool for Agent Framework integration.
"""

import json
import os
import ssl
from pathlib import Path
from typing import Annotated

import httpx
from agent_framework import tool
from pydantic import Field


def _get_jira_client() -> httpx.Client:
    """Return a configured sync httpx client for JIRA REST API."""
    base_url = os.environ.get("JIRA_BASE_URL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    verify_tls = os.environ.get("JIRA_VERIFY_TLS", "True").lower() in ("true", "1", "yes")

    if not base_url:
        raise ValueError("JIRA_BASE_URL environment variable is not set.")
    if not token:
        raise ValueError("JIRA_API_TOKEN environment variable is not set.")

    verify: bool | ssl.SSLContext = verify_tls
    if verify_tls:
        combined_bundle = (
            Path(__file__).resolve().parent.parent.parent / ".venv" / "combined_ca_bundle.pem"
        )
        env_cert = os.environ.get("SSL_CERT_FILE")
        if env_cert and os.path.exists(env_cert):
            verify = ssl.create_default_context(cafile=env_cert)
        elif combined_bundle.exists():
            verify = ssl.create_default_context(cafile=str(combined_bundle))

    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        verify=verify,
        timeout=30,
    )


@tool(approval_mode="never_require")
def jira_get_issue(
    issue_key: Annotated[str, Field(description="JIRA issue key, e.g. SACP-282967")],
) -> str:
    """Fetch a JIRA issue by key and return its summary, description, status, and other fields."""
    try:
        with _get_jira_client() as client:
            response = client.get(f"/rest/api/2/issue/{issue_key}")

            if response.status_code == 200:
                data = response.json()
                fields = data.get("fields", {})
                result = {
                    "key": data.get("key"),
                    "summary": fields.get("summary"),
                    "description": fields.get("description", "(no description)"),
                    "status": (
                        fields.get("status", {}).get("name") if fields.get("status") else None
                    ),
                    "assignee": (
                        fields.get("assignee", {}).get("displayName")
                        if fields.get("assignee")
                        else None
                    ),
                    "priority": (
                        fields.get("priority", {}).get("name") if fields.get("priority") else None
                    ),
                    "issuetype": (
                        fields.get("issuetype", {}).get("name") if fields.get("issuetype") else None
                    ),
                    "labels": fields.get("labels", []),
                    "components": [c.get("name") for c in fields.get("components", [])],
                    "acceptance_criteria": fields.get("customfield_10001", ""),
                }
                return json.dumps(result, indent=2)
            else:
                return (
                    f"Error fetching issue {issue_key}: "
                    f"HTTP {response.status_code} - {response.text}"
                )
    except Exception as e:
        return f"Error fetching issue {issue_key}: {str(e)}"


@tool(approval_mode="never_require")
def jira_add_comment(
    issue_key: Annotated[str, Field(description="JIRA issue key to add comment to")],
    comment_body: Annotated[str, Field(description="The comment text to post on the issue")],
) -> str:
    """Add a comment to a JIRA issue."""
    try:
        with _get_jira_client() as client:
            response = client.post(
                f"/rest/api/2/issue/{issue_key}/comment",
                json={"body": comment_body},
            )

            if response.status_code in (200, 201):
                data = response.json()
                return json.dumps(
                    {
                        "status": "success",
                        "comment_id": data.get("id"),
                        "issue_key": issue_key,
                        "message": f"Comment added to {issue_key}",
                    },
                    indent=2,
                )
            else:
                return (
                    f"Error adding comment to {issue_key}: "
                    f"HTTP {response.status_code} - {response.text}"
                )
    except Exception as e:
        return f"Error adding comment to {issue_key}: {str(e)}"


@tool(approval_mode="never_require")
def jira_get_comments(
    issue_key: Annotated[str, Field(description="JIRA issue key to get comments from")],
) -> str:
    """Get all comments on a JIRA issue."""
    try:
        with _get_jira_client() as client:
            response = client.get(f"/rest/api/2/issue/{issue_key}/comment")

            if response.status_code == 200:
                data = response.json()
                comments = []
                for c in data.get("comments", []):
                    comments.append(
                        {
                            "id": c.get("id"),
                            "author": c.get("author", {}).get("displayName"),
                            "created": c.get("created"),
                            "body": c.get("body"),
                        }
                    )
                return json.dumps({"total": len(comments), "comments": comments}, indent=2)
            else:
                return (
                    f"Error fetching comments for {issue_key}: "
                    f"HTTP {response.status_code} - {response.text}"
                )
    except Exception as e:
        return f"Error fetching comments for {issue_key}: {str(e)}"


@tool(approval_mode="never_require")
def jira_search_issues(
    jql: Annotated[str, Field(description="JQL query string to search JIRA issues")],
    max_results: Annotated[int, Field(description="Maximum number of results")] = 10,
) -> str:
    """Search JIRA issues using a JQL query."""
    try:
        with _get_jira_client() as client:
            response = client.get(
                "/rest/api/2/search",
                params={
                    "jql": jql,
                    "maxResults": max_results,
                    "fields": "summary,status,assignee,priority,issuetype",
                },
            )

            if response.status_code == 200:
                data = response.json()
                issues = []
                for issue in data.get("issues", []):
                    fields = issue.get("fields", {})
                    issues.append(
                        {
                            "key": issue.get("key"),
                            "summary": fields.get("summary"),
                            "status": (
                                fields.get("status", {}).get("name")
                                if fields.get("status")
                                else None
                            ),
                            "type": (
                                fields.get("issuetype", {}).get("name")
                                if fields.get("issuetype")
                                else None
                            ),
                        }
                    )
                return json.dumps({"total": data.get("total", 0), "issues": issues}, indent=2)
            else:
                return f"Error searching issues: HTTP {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error searching issues: {str(e)}"


@tool(approval_mode="never_require")
def jira_create_issue(
    project_key: Annotated[str, Field(description="JIRA project key, e.g. SACP")],
    summary: Annotated[str, Field(description="Issue summary/title")],
    issue_type: Annotated[str, Field(description="Issue type: Task, Bug, Story, etc.")] = "Task",
    description: Annotated[str, Field(description="Detailed description")] = "",
    parent_key: Annotated[str, Field(description="Parent issue key for sub-tasks")] = "",
) -> str:
    """Create a new JIRA issue."""
    try:
        with _get_jira_client() as client:
            payload = {
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "issuetype": {"name": issue_type},
                    "description": description,
                }
            }
            if parent_key:
                payload["fields"]["parent"] = {"key": parent_key}

            response = client.post("/rest/api/2/issue", json=payload)
            if response.status_code in (200, 201):
                data = response.json()
                return json.dumps(
                    {
                        "status": "success",
                        "key": data.get("key"),
                        "id": data.get("id"),
                        "self": data.get("self"),
                        "message": f"Created {data.get('key')}: {summary}",
                    },
                    indent=2,
                )
            else:
                return f"Error creating issue: HTTP {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error creating issue: {str(e)}"


@tool(approval_mode="never_require")
def jira_create_bug(
    project_key: Annotated[str, Field(description="JIRA project key, e.g. SACP")],
    summary: Annotated[str, Field(description="Bug summary/title")],
    description: Annotated[
        str, Field(description="Detailed bug description with steps to reproduce")
    ],
    priority: Annotated[str, Field(description="Priority: Low, Medium, High, Critical")] = "Medium",
    parent_story_key: Annotated[str, Field(description="Parent story key to link the bug to")] = "",
) -> str:
    """Create a Bug in JIRA with automated-test labels, and link it to a parent story."""
    priority_map = {"Low": "4", "Medium": "3", "High": "2", "Critical": "1"}
    try:
        with _get_jira_client() as client:
            payload = {
                "fields": {
                    "project": {"key": project_key},
                    "summary": summary,
                    "issuetype": {"name": "Bug"},
                    "description": description,
                    "priority": {"id": priority_map.get(priority, "3")},
                    "labels": ["automated-test", "e2e-pipeline"],
                }
            }
            response = client.post("/rest/api/2/issue", json=payload)
            if response.status_code not in (200, 201):
                return f"Error creating bug: HTTP {response.status_code} - {response.text}"

            data = response.json()
            bug_key = data.get("key")
            result = {
                "status": "success",
                "key": bug_key,
                "message": f"Bug {bug_key} created: {summary}",
            }

            # Link to parent story
            if parent_story_key and bug_key:
                link_payload = {
                    "type": {"name": "Hierarchy"},
                    "inwardIssue": {"key": bug_key},
                    "outwardIssue": {"key": parent_story_key},
                }
                link_resp = client.post("/rest/api/2/issueLink", json=link_payload)
                if link_resp.status_code in (200, 201):
                    result["linked_to"] = parent_story_key
                else:
                    result["link_warning"] = (
                        f"Bug created but link failed: HTTP {link_resp.status_code}"
                    )

            return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error creating bug: {str(e)}"


@tool(approval_mode="never_require")
def jira_transition_issue(
    issue_key: Annotated[str, Field(description="JIRA issue key to transition")],
    transition_name: Annotated[
        str, Field(description="Target transition name, e.g. 'In Progress', 'Done'")
    ],
) -> str:
    """Transition a JIRA issue to a new status by transition name."""
    try:
        with _get_jira_client() as client:
            # Get available transitions
            resp = client.get(f"/rest/api/2/issue/{issue_key}/transitions")
            if resp.status_code != 200:
                return f"Error getting transitions: HTTP {resp.status_code} - {resp.text}"

            transitions = resp.json().get("transitions", [])
            target = None
            for t in transitions:
                if t["name"].lower() == transition_name.lower():
                    target = t
                    break

            if not target:
                available = [t["name"] for t in transitions]
                return f"Transition '{transition_name}' not found. Available: {available}"

            # Execute transition
            response = client.post(
                f"/rest/api/2/issue/{issue_key}/transitions",
                json={"transition": {"id": target["id"]}},
            )
            if response.status_code in (200, 204):
                return json.dumps(
                    {
                        "status": "success",
                        "issue_key": issue_key,
                        "transition": transition_name,
                        "message": f"{issue_key} transitioned to '{transition_name}'",
                    },
                    indent=2,
                )
            else:
                return (
                    f"Error transitioning {issue_key}: "
                    f"HTTP {response.status_code} - {response.text}"
                )
    except Exception as e:
        return f"Error transitioning {issue_key}: {str(e)}"


JIRA_TOOLS = [
    jira_get_issue,
    jira_add_comment,
    jira_get_comments,
    jira_search_issues,
    jira_create_issue,
    jira_create_bug,
    jira_transition_issue,
]
