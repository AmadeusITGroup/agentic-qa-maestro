"""Unit tests for local tools."""

import json
import pytest

try:
    from agent_framework import tool
    MAF_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    MAF_AVAILABLE = False


maf_required = pytest.mark.skipif(not MAF_AVAILABLE, reason="agent-framework not installed")


@maf_required
def test_get_current_time():
    from qa_maestro_maf.tools.local_tools import get_current_time

    # MAF tools are sync functions, call directly
    result = get_current_time()
    assert "T" in result
    assert len(result) > 10


@maf_required
def test_get_current_time_with_timezone():
    from qa_maestro_maf.tools.local_tools import get_current_time

    result = get_current_time(timezone="UTC")
    assert "+00:00" in result or "UTC" in result


@maf_required
def test_run_pytest_nonexistent_path():
    from qa_maestro_maf.tools.local_tools import run_pytest

    result = run_pytest(test_path="/nonexistent/tests")
    data = json.loads(result)
    assert data.get("exit_code", 1) != 0 or "error" in data


@maf_required
def test_collect_pytest_tests_nonexistent():
    from qa_maestro_maf.tools.local_tools import collect_pytest_tests

    result = collect_pytest_tests(test_path="/nonexistent/tests")
    data = json.loads(result)
    assert "tests" in data or "error" in data


@maf_required
def test_jira_tools_exist():
    from qa_maestro_maf.tools.jira_tools import JIRA_TOOLS

    assert len(JIRA_TOOLS) == 7
    tool_names = [getattr(t, "__name__", getattr(t, "name", "")) for t in JIRA_TOOLS]
    assert "jira_get_issue" in tool_names or any("jira_get_issue" in str(t) for t in JIRA_TOOLS)
