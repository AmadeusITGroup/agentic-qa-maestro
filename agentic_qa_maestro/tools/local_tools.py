"""
Built-in local tools for Agentic QA Maestro agents.
"""

import datetime
import subprocess
import sys
import json
from typing import Annotated, Optional

from agent_framework import tool
from pydantic import Field


@tool(approval_mode="never_require")
def get_current_time(
    timezone: Annotated[
        Optional[str], Field(description="IANA timezone name, e.g. UTC, US/Eastern")
    ] = None,
) -> str:
    """Get the current date and time."""
    if timezone:
        try:
            import zoneinfo

            tz = zoneinfo.ZoneInfo(timezone)
            now = datetime.datetime.now(tz)
        except (ImportError, KeyError):
            now = datetime.datetime.now(datetime.timezone.utc)
    else:
        now = datetime.datetime.now()
    return now.isoformat()


@tool(approval_mode="never_require")
def run_pytest(
    test_path: Annotated[str, Field(description="Path to test file or directory")],
    markers: Annotated[Optional[str], Field(description="Pytest markers to filter tests")] = None,
    extra_args: Annotated[Optional[str], Field(description="Extra pytest arguments")] = None,
) -> str:
    """Run pytest on a specified test path and return results."""
    cmd = [sys.executable, "-m", "pytest", test_path, "--tb=short", "-q"]
    if markers:
        cmd.extend(["-m", markers])
    if extra_args:
        cmd.extend(extra_args.split())

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return json.dumps(
            {
                "exit_code": result.returncode,
                "stdout": (result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout),
                "stderr": (result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr),
                "passed": result.returncode == 0,
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Test execution timed out after 300 seconds"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool(approval_mode="never_require")
def collect_pytest_tests(
    test_path: Annotated[str, Field(description="Path to test file or directory")],
) -> str:
    """Collect and list all pytest tests without running them."""
    cmd = [sys.executable, "-m", "pytest", test_path, "--collect-only", "-q"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        tests = [
            line.strip() for line in result.stdout.splitlines() if "::" in line and line.strip()
        ]
        return json.dumps({"tests": tests, "count": len(tests)})
    except Exception as e:
        return json.dumps({"error": str(e)})
