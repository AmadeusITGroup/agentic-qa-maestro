"""
FastAPI Web UI for Agentic QA Maestro.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from agent_framework import AgentResponseUpdate, Message

from agentic_qa_maestro.config import AppConfig
from agentic_qa_maestro.main import QAMaestro

logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic QA Maestro", version="0.1.0")

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

_maestro: Optional[QAMaestro] = None
_run_history: list = []


@app.on_event("startup")
async def startup():
    global _maestro
    try:
        _maestro = QAMaestro()
        await _maestro.initialize()
        logger.info("Agentic QA Maestro initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize QA Maestro: {e}")
        _maestro = None


@app.on_event("shutdown")
async def shutdown():
    pass


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Agentic QA Maestro", "run_history": _run_history[-20:]},
    )


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "")

    if not message:
        return {"error": "Message cannot be empty"}
    if not _maestro:
        return {"error": "QA Maestro is not initialized"}

    try:
        from agentic_qa_maestro.teams.group_chat_team import create_group_chat_team

        team_config = _maestro.config.teams.get("interactive", {})
        workflow = create_group_chat_team(agents=_maestro.agents, team_config=team_config)

        messages: List[Dict[str, Any]] = []
        async for event in workflow.run(message, stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, AgentResponseUpdate):
                    messages.append({
                        "source": data.author_name or "agent",
                        "content": data.text or "",
                    })
                elif isinstance(data, list):
                    for msg in data:
                        if isinstance(msg, Message):
                            messages.append({
                                "source": msg.author_name or msg.role,
                                "content": msg.text or "",
                            })

        _run_history.append({
            "timestamp": datetime.now().isoformat(),
            "task": message[:100],
            "status": "completed",
            "message_count": len(messages),
        })

        return {
            "status": "completed",
            "messages": messages,
        }

    except Exception as e:
        logger.error(f"Chat error: {e}")
        _run_history.append({
            "timestamp": datetime.now().isoformat(),
            "task": message[:100],
            "status": "error",
            "error": str(e),
        })
        return {"error": str(e)}


@app.get("/api/status")
async def status():
    return {
        "status": "running" if _maestro else "not_initialized",
        "agents": list(_maestro.agents.keys()) if _maestro else [],
        "total_runs": len(_run_history),
    }


_pipeline_cancel = False


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _detect_phase(text: str) -> Optional[int]:
    """Detect which phase is being discussed in agent output."""
    text_lower = text.lower()
    if "phase 1" in text_lower or "requirement analysis" in text_lower:
        return 1
    if "phase 2" in text_lower or "app discovery" in text_lower or "targeted app" in text_lower:
        return 2
    if "phase 3" in text_lower or "test case generation" in text_lower:
        return 3
    if "phase 4" in text_lower or "test execution" in text_lower:
        return 4
    if "phase 5" in text_lower or "bug report" in text_lower:
        return 5
    if "phase 6" in text_lower or "cleanup" in text_lower:
        return 6
    return None


def _parse_test_results(text: str) -> List[Dict[str, str]]:
    """Try to extract test results from agent output."""
    results = []
    seen_ids = set()

    # Pattern 1: Table format | TC001 | Title | PASS |
    pattern1 = re.compile(
        r"\|\s*(TC[-_]?\d+)\s*\|\s*(.+?)\s*\|\s*(PASS|FAIL|BLOCKED)\s*\|",
        re.IGNORECASE,
    )
    for match in pattern1.finditer(text):
        tid = match.group(1).upper()
        if tid not in seen_ids:
            seen_ids.add(tid)
            results.append({"id": tid, "title": match.group(2).strip(), "status": match.group(3).upper(), "evidence": ""})

    # Pattern 2: TC001: Title - PASS or TC001 - Title: PASS
    pattern2 = re.compile(
        r"(TC[-_]?\d+)\s*[-:]\s*(.+?)\s*[-:–—]\s*(PASS|FAIL|BLOCKED|PASSED|FAILED)",
        re.IGNORECASE,
    )
    for match in pattern2.finditer(text):
        tid = match.group(1).upper()
        if tid not in seen_ids:
            seen_ids.add(tid)
            status = match.group(3).upper().rstrip("ED")  # PASSED -> PASS, FAILED -> FAIL
            if status == "FAIL":
                status = "FAIL"
            elif status == "PASS":
                status = "PASS"
            results.append({"id": tid, "title": match.group(2).strip(), "status": status, "evidence": ""})

    # Pattern 3: **TC001** ... PASS/FAIL or "TC001" ... PASS/FAIL (within same line)
    pattern3 = re.compile(
        r"\*{0,2}(TC[-_]?\d+)\*{0,2}\s*[:\-–—]?\s*(.+?)\s*(?:Result|Status|Outcome)?\s*[:=]?\s*(PASS|FAIL|BLOCKED|PASSED|FAILED)",
        re.IGNORECASE,
    )
    for match in pattern3.finditer(text):
        tid = match.group(1).upper()
        if tid not in seen_ids:
            seen_ids.add(tid)
            status = "PASS" if "PASS" in match.group(3).upper() else "FAIL"
            results.append({"id": tid, "title": match.group(2).strip().rstrip("-:– "), "status": status, "evidence": ""})

    # Pattern 4: "Test N" or "Test Case N" ... PASS/FAIL (no TC prefix)
    if not results:
        pattern4 = re.compile(
            r"(?:Test(?:\s+Case)?\s+(\d+))\s*[-:]\s*(.+?)\s*[-:–—]\s*(PASS|FAIL|BLOCKED|PASSED|FAILED)",
            re.IGNORECASE,
        )
        for match in pattern4.finditer(text):
            tid = f"TC{match.group(1)}"
            if tid not in seen_ids:
                seen_ids.add(tid)
                status = "PASS" if "PASS" in match.group(3).upper() else "FAIL"
                results.append({"id": tid, "title": match.group(2).strip(), "status": status, "evidence": ""})

    return results


def _parse_bugs(text: str) -> List[Dict[str, str]]:
    """Try to extract created bug ticket keys from agent output."""
    bugs = []
    # Match JIRA keys like SACP-12345 followed by summary text
    pattern = re.compile(r"([A-Z][A-Z0-9]+-\d+)\s*[-:–—]\s*(.+?)(?:\n|$)")
    for match in pattern.finditer(text):
        bugs.append({"key": match.group(1), "summary": match.group(2).strip()})
    # Also match "created bug SACP-12345" or "filed SACP-12345"
    pattern2 = re.compile(r"(?:created|filed|logged|raised)\s+(?:bug\s+)?([A-Z][A-Z0-9]+-\d+)", re.IGNORECASE)
    for match in pattern2.finditer(text):
        key = match.group(1)
        if not any(b["key"] == key for b in bugs):
            bugs.append({"key": key, "summary": "Bug filed during test execution"})
    return bugs


async def _pipeline_stream(ticket: str, url: str, username: str, password: str) -> AsyncGenerator[str, None]:
    """Stream pipeline events as SSE."""
    global _pipeline_cancel
    _pipeline_cancel = False

    if not _maestro:
        yield _sse_event({"type": "error", "message": "QA Maestro is not initialized"})
        return

    # Set credentials for browser agent
    os.environ["CREDENTIAL_USERNAME"] = username
    os.environ["CREDENTIAL_PASSWORD"] = password

    from agentic_qa_maestro.teams.group_chat_team import create_group_chat_team

    # Build the E2E prompt
    prompt = (
        f"Run the FULL 6-phase E2E test pipeline for JIRA ticket {ticket} "
        f"against the application at {url}.\n\n"
        f"Execute ALL phases in order:\n\n"
        f"PHASE 1 — REQUIREMENT ANALYSIS:\n"
        f"  Use jira_get_issue to fetch {ticket}. Extract ALL acceptance criteria,\n"
        f"  testable scenarios, and functional requirements.\n\n"
        f"PHASE 2 — TARGETED APP DISCOVERY:\n"
        f"  Use browser tools to:\n"
        f"  1. start_browser (headless=true)\n"
        f"  2. open_url({url})\n"
        f"  3. get_page_content to discover real UI elements and selectors\n"
        f"  4. screenshot('discovery.png') as evidence of initial state\n"
        f"  Report what you found: pages, forms, buttons, navigation elements.\n\n"
        f"PHASE 3 — TEST CASE GENERATION:\n"
        f"  Using Phase 1 requirements AND Phase 2 UI discovery, generate test cases.\n"
        f"  Each test case must include: Test ID, Title, Priority, Steps (with real selectors),\n"
        f"  Expected Result, AC Coverage.\n\n"
        f"PHASE 4 — TEST EXECUTION:\n"
        f"  Execute ALL test cases against the live application using browser tools.\n"
        f"  For each test: navigate, interact, validate, take screenshots.\n"
        f"  Report PASS/FAIL for each with evidence.\n\n"
        f"PHASE 5 — BUG REPORTING:\n"
        f"  For FAILED tests: use jira_create_bug to create Bug tickets linked to {ticket}.\n"
        f"  Post a comprehensive summary comment on {ticket} with jira_add_comment.\n"
        f"  Include: total tests, passed, failed, bug ticket links.\n\n"
        f"PHASE 6 — CLEANUP:\n"
        f"  Use close_browser to cleanup. Provide final pipeline status summary.\n\n"
        f"IMPORTANT: Execute ALL phases autonomously. Never ask for user input."
    )

    team_config = _maestro.config.teams.get("interactive", {})
    team_config = {**team_config, "max_messages": 80}
    workflow = create_group_chat_team(agents=_maestro.agents, team_config=team_config)

    current_phase = 0
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    seen_test_ids = set()
    seen_bug_keys = set()

    try:
        async for event in workflow.run(prompt, stream=True):
            if _pipeline_cancel:
                yield _sse_event({"type": "pipeline_complete", "summary": "Cancelled by user"})
                return

            if event.type == "output":
                data = event.data
                text_to_process = []

                if isinstance(data, AgentResponseUpdate):
                    agent_name = data.author_name or "agent"
                    text = data.text or ""
                    if text.strip():
                        text_to_process.append((agent_name, text))

                elif isinstance(data, list):
                    for msg in data:
                        if isinstance(msg, Message):
                            agent_name = msg.author_name or msg.role or "agent"
                            text = msg.text or ""
                            if text.strip():
                                text_to_process.append((agent_name, text))

                elif isinstance(data, Message):
                    agent_name = data.author_name or data.role or "agent"
                    text = data.text or ""
                    if text.strip():
                        text_to_process.append((agent_name, text))

                for agent_name, text in text_to_process:

                    # Detect phase transitions
                    detected = _detect_phase(text)
                    if detected and detected != current_phase:
                        if current_phase > 0:
                            yield _sse_event({"type": "phase_end", "phase": current_phase, "status": "ok"})
                        current_phase = detected
                        phase_names = {1: "Requirement Analysis", 2: "App Discovery", 3: "Test Case Generation", 4: "Test Execution", 5: "Bug Reporting", 6: "Cleanup"}
                        yield _sse_event({"type": "phase_start", "phase": current_phase, "name": phase_names.get(current_phase, "")})

                    # Emit agent message
                    yield _sse_event({"type": "agent_message", "agent": agent_name, "content": text[:500]})

                    # Try to parse test results
                    results = _parse_test_results(text)
                    for r in results:
                        if r["id"] in seen_test_ids:
                            continue
                        seen_test_ids.add(r["id"])
                        total_tests += 1
                        if r["status"] == "PASS":
                            passed_tests += 1
                        else:
                            failed_tests += 1
                        yield _sse_event({"type": "test_result", **r})

                    # Try to parse bug tickets
                    bugs = _parse_bugs(text)
                    for b in bugs:
                        if b["key"] in seen_bug_keys:
                            continue
                        seen_bug_keys.add(b["key"])
                        yield _sse_event({"type": "bug_created", **b})

                    await asyncio.sleep(0)  # yield control

        # Final phase end
        if current_phase > 0:
            yield _sse_event({"type": "phase_end", "phase": current_phase, "status": "ok"})

        # Test summary
        if total_tests > 0:
            yield _sse_event({"type": "test_summary", "total": total_tests, "passed": passed_tests, "failed": failed_tests})

        yield _sse_event({"type": "pipeline_complete", "summary": f"{total_tests} tests | {passed_tests} passed | {failed_tests} failed"})

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        yield _sse_event({"type": "error", "message": str(e)})

    yield "data: [DONE]\n\n"


@app.post("/api/pipeline")
async def run_pipeline(request: Request):
    body = await request.json()
    ticket = body.get("ticket", "")
    url = body.get("url", "")
    username = body.get("username", "")
    password = body.get("password", "")

    if not all([ticket, url, username, password]):
        return {"error": "All fields are required: ticket, url, username, password"}

    return StreamingResponse(
        _pipeline_stream(ticket, url, username, password),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/pipeline/stop")
async def stop_pipeline():
    global _pipeline_cancel
    _pipeline_cancel = True
    return {"status": "stopping"}


@app.get("/api/history")
async def history():
    return {"runs": _run_history[-50:]}


# Settings management
_settings_file = Path(__file__).parent.parent.parent / ".settings.json"


def _load_settings() -> dict:
    if _settings_file.exists():
        try:
            return json.loads(_settings_file.read_text())
        except Exception:
            return {}
    return {}


def _save_settings(settings: dict):
    # Never persist passwords/keys in plaintext - store only non-sensitive settings
    safe_keys = ["azure_endpoint", "azure_model", "azure_version", "jira_url", "jira_project", "headless", "screenshot_dir"]
    to_save = {k: v for k, v in settings.items() if k in safe_keys and v}
    _settings_file.write_text(json.dumps(to_save, indent=2))


@app.get("/api/settings")
async def get_settings():
    settings = _load_settings()
    # Also populate from env vars if available
    settings.setdefault("azure_endpoint", os.environ.get("DEFAULT_OPENAI_ENDPOINT", ""))
    settings.setdefault("azure_model", os.environ.get("DEFAULT_OPENAI_MODEL", ""))
    settings.setdefault("azure_version", os.environ.get("DEFAULT_OPENAI_API_VERSION", ""))
    settings.setdefault("jira_url", os.environ.get("JIRA_BASE_URL", ""))
    settings.setdefault("jira_project", "")
    settings.setdefault("headless", "true")
    settings.setdefault("screenshot_dir", "test_evidence/")
    return settings


@app.post("/api/settings")
async def save_settings(request: Request):
    body = await request.json()

    # Apply sensitive settings to environment (session only, not persisted to disk)
    if body.get("azure_endpoint"):
        os.environ["DEFAULT_OPENAI_ENDPOINT"] = body["azure_endpoint"]
    if body.get("azure_key"):
        os.environ["AZURE_OPENAI_API_KEY"] = body["azure_key"]
    if body.get("azure_model"):
        os.environ["DEFAULT_OPENAI_MODEL"] = body["azure_model"]
        os.environ["DEFAULT_OPENAI_DEPLOYMENT"] = body["azure_model"]
    if body.get("azure_version"):
        os.environ["DEFAULT_OPENAI_API_VERSION"] = body["azure_version"]
    if body.get("jira_url"):
        os.environ["JIRA_BASE_URL"] = body["jira_url"]
    if body.get("jira_pat"):
        os.environ["JIRA_API_TOKEN"] = body["jira_pat"]

    # Persist non-sensitive settings
    _save_settings(body)

    return {"status": "saved"}


def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
