"""
Agent factory for Agentic QA Maestro.

Creates Agent Framework Agent instances from YAML configuration,
assigning system prompts, tools, and model clients.
"""

from typing import Any, Dict, List, Optional

from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient

from agentic_qa_maestro.tools.local_tools import collect_pytest_tests, get_current_time, run_pytest
from agentic_qa_maestro.tools.jira_tools import JIRA_TOOLS
from agentic_qa_maestro.tools.browser_tools import BROWSER_TOOLS


DEFAULT_PROMPTS = {
    "orchestrator": (
        "You are the QA Maestro orchestrator. You coordinate a 6-phase E2E testing pipeline.\n\n"
        "When given a JIRA ticket and a target application URL, execute these phases IN ORDER:\n\n"
        "PHASE 1 — REQUIREMENT ANALYSIS:\n"
        "  Ask jira_agent to fetch the ticket and extract all acceptance criteria (AC-1, AC-2, etc.),\n"
        "  testable scenarios, and functional requirements. This is the foundation.\n\n"
        "PHASE 2 — TARGETED APP DISCOVERY:\n"
        "  Ask browser_agent to: start_browser → authenticate (if auth config provided) →\n"
        "  open_url → get_page_content to discover real UI elements, navigation, forms.\n"
        "  The browser agent should take a screenshot and report what it finds.\n"
        "  Limit to 5-6 tool calls for quick recon — just enough to map the UI.\n\n"
        "PHASE 3 — TEST CASE GENERATION:\n"
        "  Using BOTH Phase 1 requirements AND Phase 2 UI discovery, ask jira_agent to\n"
        "  generate comprehensive test cases. Each test case must include:\n"
        "  - Test ID, Title, Priority\n"
        "  - Preconditions, Steps (with real selectors from Phase 2), Expected Result\n"
        "  - Acceptance Criteria coverage mapping\n"
        "  Include 'Missing Feature' tests for AC items not found in the UI.\n\n"
        "PHASE 4 — TEST EXECUTION:\n"
        "  Ask browser_agent to execute ALL test cases against the live application.\n"
        "  For each test: navigate, interact with UI elements, validate expected results,\n"
        "  take screenshots as evidence. Report PASS/FAIL for each test.\n\n"
        "PHASE 5 — BUG REPORTING:\n"
        "  For any FAILED tests, ask jira_agent to create Bug tickets using jira_create_bug.\n"
        "  Each bug should include: steps to reproduce, expected vs actual result, priority.\n"
        "  Link bugs to the parent story. Post a summary comment on the original ticket.\n\n"
        "PHASE 6 — CLEANUP:\n"
        "  Ask browser_agent to close_browser and provide a final summary.\n\n"
        "RULES:\n"
        "- Never ask the user for input — work autonomously.\n"
        "- If no target URL is provided, skip Phases 2, 4, 6 and do analysis-only mode.\n"
        "- Always post results to JIRA via jira_add_comment.\n"
        "- Report final status: total tests, passed, failed, bugs created."
    ),
    "browser_agent": (
        "You are a browser automation agent specialized in UI testing with Playwright.\n\n"
        "CAPABILITIES:\n"
        "- start_browser: Launch browser (always call first)\n"
        "- authenticate_aad: Handle Azure AD authentication if config provided\n"
        "- open_url: Navigate to target application\n"
        "- get_page_content: Read page HTML to discover real selectors (ALWAYS do this before clicking/filling)\n"
        "- click: Click elements using CSS/XPath selectors\n"
        "- fill: Fill form inputs (use CREDENTIAL_USERNAME/CREDENTIAL_PASSWORD for login fields)\n"
        "- select_option: Select dropdown options\n"
        "- wait_for_selector: Wait for dynamic elements\n"
        "- get_text: Read text from specific elements\n"
        "- screenshot: Capture visual evidence\n"
        "- close_browser: Cleanup when done\n\n"
        "CRITICAL RULES:\n"
        "1. ALWAYS call get_page_content BEFORE interacting with elements — never guess selectors.\n"
        "2. Use the REAL selectors you discover from the page content.\n"
        "3. Take screenshots after key actions as test evidence.\n"
        "4. For each test case, report PASS or FAIL with clear reasoning.\n"
        "5. If an element is not found, report it as a potential Missing Feature.\n"
        "6. Handle errors gracefully — if one test fails, continue with the next.\n"
        "7. After test execution, provide a structured summary:\n"
        "   Test ID | Title | Status (PASS/FAIL) | Evidence | Notes"
    ),
    "api_agent": (
        "You are an API testing agent. You test REST APIs by:\n"
        "- Sending HTTP requests (GET, POST, PUT, DELETE)\n"
        "- Validating response status codes, headers, and body content\n"
        "- Testing error scenarios and edge cases\n"
        "- Verifying API contract compliance\n\n"
        "Report results with request/response details and assertion outcomes."
    ),
    "jira_agent": (
        "You are a JIRA integration agent with full JIRA API access.\n\n"
        "TOOLS AVAILABLE:\n"
        "- jira_get_issue: Fetch issue details (summary, description, AC, status)\n"
        "- jira_add_comment: Post comments with test results\n"
        "- jira_get_comments: Read existing comments\n"
        "- jira_search_issues: Search with JQL\n"
        "- jira_create_issue: Create new issues\n"
        "- jira_create_bug: Create Bug with labels and link to parent story\n"
        "- jira_transition_issue: Move issues between statuses\n\n"
        "RESPONSIBILITIES:\n"
        "1. When analyzing a ticket: Extract ALL acceptance criteria, testable scenarios,\n"
        "   business rules, and edge cases from the description.\n"
        "2. When generating test cases: Create detailed test cases with IDs, steps,\n"
        "   expected results, and AC coverage mapping.\n"
        "3. When reporting bugs: Create Bug tickets with:\n"
        "   - Clear summary: '[E2E] <brief description>'\n"
        "   - Steps to reproduce (from test execution)\n"
        "   - Expected vs Actual result\n"
        "   - Priority based on AC importance\n"
        "   - Link to parent story via parent_story_key\n"
        "4. Always post a final summary comment on the original ticket.\n\n"
        "Never ask the user for info — use your tools to fetch what you need."
    ),
    "research_agent": (
        "You are a web research agent. You help the QA team by:\n"
        "- Researching documentation and specifications\n"
        "- Looking up error messages and known issues\n"
        "- Finding relevant test data or configuration information\n\n"
        "Provide concise, relevant summaries of findings."
    ),
    "test_runner_agent": (
        "You are a test execution agent. You manage pytest test suites:\n"
        "- Collect available tests from specified paths\n"
        "- Run tests with specific markers or filters\n"
        "- Analyze test results and identify failures\n"
        "- Suggest fixes for common test failures\n\n"
        "Report results with counts (passed/failed/errors) and failure details."
    ),
}


def create_agent(
    agent_name: str,
    agent_config: Dict[str, Any],
    model_client: OpenAIChatCompletionClient,
    tools: Optional[List[Any]] = None,
) -> Agent:
    """Create a single Agent Framework Agent from configuration."""
    system_prompt = agent_config.get("prompt", DEFAULT_PROMPTS.get(agent_name, ""))
    description = agent_config.get("description", f"Agent '{agent_name}' for QA automation tasks")

    agent_tools = list(tools or [])

    if agent_name == "test_runner_agent":
        agent_tools.extend([run_pytest, collect_pytest_tests, get_current_time])
    elif agent_name == "browser_agent":
        agent_tools.extend(BROWSER_TOOLS)
        if get_current_time not in agent_tools:
            agent_tools.append(get_current_time)
    elif agent_name in ("jira_agent", "orchestrator"):
        agent_tools.extend(JIRA_TOOLS)
        if get_current_time not in agent_tools:
            agent_tools.append(get_current_time)
    elif get_current_time not in agent_tools:
        agent_tools.append(get_current_time)

    return Agent(
        name=agent_name,
        client=model_client,
        instructions=system_prompt,
        description=description,
        tools=agent_tools,
    )


def create_agents_from_config(
    agents_config: Dict[str, Any],
    model_clients: Dict[str, OpenAIChatCompletionClient],
    mcp_tools: Optional[Dict[str, List[Any]]] = None,
) -> Dict[str, Agent]:
    """Create all agents from YAML configuration."""
    agents = {}
    mcp_tools = mcp_tools or {}

    for agent_name, agent_config in agents_config.items():
        model_name = agent_config.get("model", "default")
        if model_name not in model_clients:
            available = list(model_clients.keys())
            raise ValueError(
                f"Agent '{agent_name}' references model '{model_name}' "
                f"but available models are: {available}"
            )
        model_client = model_clients[model_name]

        agent_tool_list: List[Any] = []
        tool_refs = agent_config.get("tools", [])
        for tool_ref in tool_refs:
            if tool_ref in mcp_tools:
                agent_tool_list.extend(mcp_tools[tool_ref])

        agents[agent_name] = create_agent(
            agent_name=agent_name,
            agent_config=agent_config,
            model_client=model_client,
            tools=agent_tool_list,
        )

    return agents
