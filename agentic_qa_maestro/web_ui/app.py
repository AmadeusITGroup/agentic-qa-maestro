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
import tempfile
import base64

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from agent_framework import AgentResponseUpdate, Message

from agentic_qa_maestro.main import QAMaestro
from agentic_qa_maestro.tools.english_test_parser import parse_english_test_cases

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
        project_root = Path(__file__).resolve().parents[2]
        local_env = project_root / ".env"
        if local_env.exists():
            load_dotenv(local_env, override=False)

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
                    messages.append(
                        {
                            "source": data.author_name or "agent",
                            "content": data.text or "",
                        }
                    )
                elif isinstance(data, list):
                    for msg in data:
                        if isinstance(msg, Message):
                            messages.append(
                                {
                                    "source": msg.author_name or msg.role,
                                    "content": msg.text or "",
                                }
                            )

        _run_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "task": message[:100],
                "status": "completed",
                "message_count": len(messages),
            }
        )

        return {
            "status": "completed",
            "messages": messages,
        }

    except Exception as e:
        logger.error(f"Chat error: {e}")
        _run_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "task": message[:100],
                "status": "error",
                "error": str(e),
            }
        )
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
            results.append(
                {
                    "id": tid,
                    "title": match.group(2).strip(),
                    "status": match.group(3).upper(),
                    "evidence": "",
                }
            )

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
            results.append(
                {"id": tid, "title": match.group(2).strip(), "status": status, "evidence": ""}
            )

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
            results.append(
                {
                    "id": tid,
                    "title": match.group(2).strip().rstrip("-:– "),
                    "status": status,
                    "evidence": "",
                }
            )

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
                results.append(
                    {"id": tid, "title": match.group(2).strip(), "status": status, "evidence": ""}
                )

    # Pattern 5: multi-line TEST RESULT block from the agent prompt format:
    #   TEST RESULT: TC001 - Login Test
    #   Status: PASS
    #   Details: ...
    pattern5 = re.compile(
        r"TEST RESULT:\s*(TC[-_]?\d+)\s*[-–—]?\s*(.+?)\s*\nStatus:\s*(PASS|FAIL|BLOCKED)"
        r"(?:\s*\nDetails:\s*(.+))?",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in pattern5.finditer(text):
        tid = match.group(1).upper().replace("-", "").replace("_", "")
        tid = re.sub(r"TC(\d+)", lambda m: f"TC{int(m.group(1)):03d}", tid)
        if tid not in seen_ids:
            seen_ids.add(tid)
            results.append({
                "id": tid,
                "title": match.group(2).strip(),
                "status": match.group(3).upper(),
                "evidence": (match.group(4) or "").strip(),
            })

    return results


def _parse_bugs(text: str) -> List[Dict[str, str]]:
    """Try to extract created bug ticket keys from agent output."""
    bugs = []
    # Match JIRA keys like SACP-12345 followed by summary text
    pattern = re.compile(r"([A-Z][A-Z0-9]+-\d+)\s*[-:–—]\s*(.+?)(?:\n|$)")
    for match in pattern.finditer(text):
        bugs.append({"key": match.group(1), "summary": match.group(2).strip()})
    # Also match "created bug SACP-12345" or "filed SACP-12345"
    pattern2 = re.compile(
        r"(?:created|filed|logged|raised)\s+(?:bug\s+)?([A-Z][A-Z0-9]+-\d+)", re.IGNORECASE
    )
    for match in pattern2.finditer(text):
        key = match.group(1)
        if not any(b["key"] == key for b in bugs):
            bugs.append({"key": key, "summary": "Bug filed during test execution"})
    return bugs


async def _pipeline_stream(
    ticket: str, url: str, username: str, password: str, nav_hints: str = ""
) -> AsyncGenerator[str, None]:
    """Stream pipeline events as SSE."""
    global _pipeline_cancel
    _pipeline_cancel = False

    if not _maestro:
        yield _sse_event({"type": "error", "message": "QA Maestro is not initialized"})
        return

    # Read headless setting (default true)
    _settings = _load_settings()
    _headless_val = str(_settings.get("headless", "true")).lower() != "false"
    _headless_str = "true" if _headless_val else "false"

    # Emit an immediate event so clients receive early bytes and keep the stream alive
    # while agents initialize and the first model/tool output is pending.
    yield _sse_event(
        {
            "type": "agent_message",
            "agent": "system",
            "content": "Pipeline accepted. Initializing agents...",
        }
    )

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
        f"PHASE 2 — APP DISCOVERY (login + navigate + discover REAL selectors):\n"
        f"  The goal is to discover the ACTUAL application UI — not just the login page.\n"
        f"  Use browser tools to:\n"
        f"  1. start_browser (headless={_headless_str})\n"
        f"  2. open_url({url})\n"
        f"  3. LOGIN:\n"
        f"     a) wait_for_selector('input[type=password]', timeout=30000) — waits for JS to render the login form.\n"
        f"     b) get_page_content — now the form is rendered, find the actual username and password selectors.\n"
        f"     c) fill the username field with CREDENTIAL_USERNAME and password field with CREDENTIAL_PASSWORD.\n"
        f"     d) click the login/submit button.\n"
        f"     NOTE: Many login pages render via JavaScript and may take 10-20 seconds to appear.\n"
        f"     The wait_for_selector in step (a) ensures the form is ready before you interact.\n"
        f"  4. AFTER login, navigate to the target application page:\n"
    )

    if nav_hints:
        prompt += f"     NAVIGATION: {nav_hints}\n"
    else:
        prompt += "     (explore the main page and navigate to the relevant app section)\n"

    prompt += (
        f"  5. get_page_content ON THE APPLICATION PAGE (not the login page!)\n"
        f"     This is the critical step — discover all real selectors, buttons, tables,\n"
        f"     forms, links, tabs, and sections on the actual app page.\n"
        f"  6. screenshot('discovery.png') as evidence of the app state\n"
        f"  Report: List ALL real selectors, elements, and interactive components found.\n"
        f"  IMPORTANT: Do NOT guess selectors. Only report what get_page_content actually returns.\n\n"
        f"PHASE 3 — TEST CASE GENERATION:\n"
        f"  Using Phase 1 requirements AND Phase 2 discovered selectors, generate test cases.\n"
        f"  RULES:\n"
        f"  - ONLY use selectors that were actually found in Phase 2 get_page_content output.\n"
        f"  - If a required feature's selector was NOT found in Phase 2, mark that test as\n"
        f"    'BLOCKED — selector not discovered' and flag it as a potential Missing Feature.\n"
        f"  - Do NOT invent selectors like .history-section or .add-ticket-btn.\n"
        f"  - Each test case: Test ID, Title, Priority, Steps (with REAL selectors from Phase 2),\n"
        f"    Expected Result, AC Coverage.\n\n"
        f"PHASE 4 — TEST EXECUTION:\n"
        f"  Execute test cases against the live application. The browser is still open from Phase 2.\n"
        f"  RULES:\n"
        f"  - Before EACH interaction, call get_page_content to see the current page state.\n"
        f"  - Only click/fill elements that actually exist in the current page content.\n"
        f"  - If an element is not found, mark the test FAIL with 'element not present'.\n"
        f"  - After each navigation or click that changes the page, call get_page_content again.\n"
        f"  - Take screenshots as evidence after key actions.\n"
        f"  - Report PASS/FAIL for each test with evidence.\n\n"
        f"PHASE 5 — BUG REPORTING:\n"
        f"  For FAILED tests: use jira_create_bug to create Bug tickets linked to {ticket}.\n"
        f"  Post a comprehensive summary comment on {ticket} with jira_add_comment.\n"
        f"  Include: total tests, passed, failed, bug ticket links.\n\n"
        f"PHASE 6 — CLEANUP:\n"
        f"  Use close_browser to cleanup. Provide final pipeline status summary.\n\n"
        f"IMPORTANT: Execute ALL phases autonomously. Never ask for user input.\n"
        f"IMPORTANT: The browser stays open across phases — do NOT close and reopen between phases."
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
                            yield _sse_event(
                                {"type": "phase_end", "phase": current_phase, "status": "ok"}
                            )
                        current_phase = detected
                        phase_names = {
                            1: "Requirement Analysis",
                            2: "App Discovery",
                            3: "Test Case Generation",
                            4: "Test Execution",
                            5: "Bug Reporting",
                        }
                        yield _sse_event(
                            {
                                "type": "phase_start",
                                "phase": current_phase,
                                "name": phase_names.get(current_phase, ""),
                            }
                        )

                    # Emit agent message
                    yield _sse_event(
                        {"type": "agent_message", "agent": agent_name, "content": text[:500]}
                    )

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
            yield _sse_event(
                {
                    "type": "test_summary",
                    "total": total_tests,
                    "passed": passed_tests,
                    "failed": failed_tests,
                }
            )

        yield _sse_event(
            {
                "type": "pipeline_complete",
                "summary": f"{total_tests} tests | {passed_tests} passed | {failed_tests} failed",
            }
        )

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
    nav_hints = body.get("nav_hints", "")

    if not all([ticket, url, username, password]):
        return {"error": "All fields are required: ticket, url, username, password"}

    return StreamingResponse(
        _pipeline_stream(ticket, url, username, password, nav_hints),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================================
# ENGLISH TEST PIPELINE - NEW FEATURE
# ============================================================================

_english_pipeline_cancel = False
_english_pipeline_state = {
    "parsed_cases": [],
    "current_results": [],
    "report_html": "",
}


def _sse_english_event(data: dict) -> str:
    """Format SSE event for English pipeline"""
    return f"data: {json.dumps(data)}\n\n"


async def _english_pipeline_stream(
    test_cases_text: str, 
    app_url: str, 
    username: str, 
    password: str
) -> AsyncGenerator[str, None]:
    """Stream English test pipeline events as SSE - Real Execution"""
    global _english_pipeline_cancel
    _english_pipeline_cancel = False

    if not _maestro:
        yield _sse_english_event({"type": "error", "message": "QA Maestro is not initialized"})
        return

    # Read headless setting (default true)
    _settings = _load_settings()
    _headless_val = str(_settings.get("headless", "true")).lower() != "false"
    _headless_str = "true" if _headless_val else "false"

    try:
        # PHASE 1: Parse English Test Cases
        yield _sse_english_event({
            "type": "phase_start",
            "phase": 1,
            "name": "Parse English Test Cases"
        })

        if not test_cases_text or test_cases_text.strip() == "":
            yield _sse_english_event({
                "type": "error",
                "message": "Error: No test cases provided. Please upload a valid test file."
            })
            return

        parsed_cases = parse_english_test_cases(test_cases_text)
        
        if not parsed_cases:
            yield _sse_english_event({
                "type": "error",
                "message": "Error: Could not parse any test cases from the file. Please check the format."
            })
            return

        _english_pipeline_state["parsed_cases"] = parsed_cases

        for case in parsed_cases:
            yield _sse_english_event({
                "type": "test_case_parsed",
                "test_id": case.get("test_id"),
                "title": case.get("title"),
                "steps_count": len(case.get("steps", []))
            })
            await asyncio.sleep(0.05)

        yield _sse_english_event({
            "type": "phase_end",
            "phase": 1,
            "status": "ok",
            "message": f"Parsed {len(parsed_cases)} test cases"
        })

        # Build single unified agent prompt for phases 2+3+4
        # Using one workflow keeps the browser session alive across all phases
        os.environ["CREDENTIAL_USERNAME"] = username
        os.environ["CREDENTIAL_PASSWORD"] = password

        from agentic_qa_maestro.teams.group_chat_team import create_group_chat_team
        team_config = _maestro.config.teams.get("interactive", {})
        team_config = {**team_config, "max_messages": 80}

        # Build test cases section
        test_cases_section = ""
        for i, case in enumerate(parsed_cases, 1):
            test_cases_section += f"\n--- TEST CASE {i}: {case.get('test_id')} - {case.get('title')} ---\n"
            test_cases_section += f"Priority: {case.get('priority', 'Medium')}\n"
            test_cases_section += f"Description: {case.get('description', 'N/A')}\n"
            test_cases_section += f"Preconditions: {case.get('preconditions', 'N/A')}\n"
            test_cases_section += f"Steps:\n"
            for step in case.get('steps', []):
                desc = step.get('description', '')
                action = step.get('action', '')
                target = step.get('target', '')
                value = step.get('value', '')
                line = f"  {step.get('step_number','?')}. {desc}"
                if action:
                    extras = f"action={action}"
                    if target:
                        extras += f", target={target}"
                    if value:
                        extras += f", value={value}"
                    line += f" [{extras}]"
                test_cases_section += line + "\n"
            test_cases_section += f"Expected Result: {case.get('expected_result', 'N/A')}\n"
            test_cases_section += (
                f"\nAfter executing, output exactly:\n"
                f"TEST RESULT: {case.get('test_id')} - {case.get('title')}\n"
                f"Status: PASS\n"
                f"  OR\n"
                f"Status: FAIL\n"
                f"Details: <what went wrong>\n"
                f"---\n"
            )

        unified_prompt = (
            f"You are a QA automation agent. Complete ALL of the following steps in order.\n"
            f"Application URL: {app_url}\n"
            f"Credentials are in environment variables CREDENTIAL_USERNAME and CREDENTIAL_PASSWORD.\n\n"
            f"== STEP A: OPEN BROWSER AND LOGIN ==\n"
            f"1. Call start_browser (headless={_headless_str})\n"
            f"2. Call open_url('{app_url}')\n"
            f"3. Call get_page_content to see the login form\n"
            f"4. Fill the username field using fill_field\n"
            f"5. Fill the password field using fill_field\n"
            f"6. Click the login/submit button using click_element\n"
            f"7. Call get_page_content to confirm you are now logged in\n"
            f"When login is done, output exactly: PHASE_DISCOVERY_DONE\n\n"
            f"== STEP B: EXECUTE TEST CASES ==\n"
            f"The browser is still open from Step A. Execute each test case below.\n"
            f"For each test case:\n"
            f"  - Use get_page_content to inspect the current page before acting\n"
            f"  - Use fill_field for text inputs\n"
            f"  - Use click_element for buttons and links\n"
            f"  - Use take_screenshot after key steps for evidence\n"
            f"  - Output the TEST RESULT block in the format shown after each test\n\n"
            f"TEST CASES:\n{test_cases_section}\n"
            f"When all test cases are done, output exactly: PHASE_EXECUTION_DONE\n\n"
            f"IMPORTANT RULES:\n"
            f"- Do NOT close the browser until ALL test cases are executed\n"
            f"- Do NOT repeat actions already completed\n"
            f"- Do NOT ask for user input\n"
            f"- If a browser tool call succeeds, consider that step done and move to the next\n"
            f"- If a step fails, mark that test as FAIL and continue to next test case"
        )

        # PHASE 2: emit start, then run unified workflow
        yield _sse_english_event({
            "type": "phase_start",
            "phase": 2,
            "name": "App Discovery & Login"
        })

        workflow = create_group_chat_team(agents=_maestro.agents, team_config=team_config)

        test_results = []
        passed_count = 0
        failed_count = 0
        seen_test_ids = set()
        current_streaming_phase = 2
        phase3_emitted = False
        phase4_emitted = False
        agent_text_buffer = ""  # accumulate all agent output for multiline result parsing

        async for event in workflow.run(unified_prompt, stream=True):
            if _english_pipeline_cancel:
                yield _sse_english_event({"type": "pipeline_complete", "summary": "Cancelled by user"})
                return

            if event.type == "output":
                data = event.data
                texts = []

                if isinstance(data, AgentResponseUpdate):
                    t = data.text or ""
                    if t.strip():
                        texts.append((data.author_name or "agent", t))
                elif isinstance(data, list):
                    for msg in data:
                        if isinstance(msg, Message):
                            t = msg.text or ""
                            if t.strip():
                                texts.append((msg.author_name or msg.role or "agent", t))
                elif isinstance(data, Message):
                    t = data.text or ""
                    if t.strip():
                        texts.append((data.author_name or data.role or "agent", t))

                for agent_name, text in texts:
                    # Detect phase transition markers from the agent
                    if "PHASE_DISCOVERY_DONE" in text and not phase3_emitted:
                        phase3_emitted = True
                        yield _sse_english_event({"type": "phase_end", "phase": 2, "status": "ok",
                                                   "message": "App discovery & login completed"})
                        yield _sse_english_event({"type": "phase_start", "phase": 3, "name": "Test Formatting"})
                        # Format phase is instant - emit all formatted cases
                        for case in parsed_cases:
                            yield _sse_english_event({
                                "type": "test_formatted",
                                "test_id": case.get("test_id"),
                                "title": case.get("title")
                            })
                        yield _sse_english_event({"type": "phase_end", "phase": 3, "status": "ok",
                                                   "message": f"Formatted {len(parsed_cases)} test cases"})
                        yield _sse_english_event({"type": "phase_start", "phase": 4, "name": "Test Execution"})
                        phase4_emitted = True
                        current_streaming_phase = 4

                    if "PHASE_EXECUTION_DONE" in text:
                        pass  # execution done marker - results already parsed below

                    # Emit agent message (strip internal markers from display)
                    display_text = text.replace("PHASE_DISCOVERY_DONE", "").replace("PHASE_EXECUTION_DONE", "").strip()
                    if display_text:
                        yield _sse_english_event({
                            "type": "agent_message",
                            "agent": agent_name,
                            "content": display_text[:500]
                        })
                        await asyncio.sleep(0.05)

                    # Accumulate all agent text for multiline result parsing
                    agent_text_buffer += "\n" + text

                    # Parse test results from accumulated buffer (handles multi-line TEST RESULT blocks)
                    results = _parse_test_results(agent_text_buffer)
                    for r in results:
                        test_id = r.get("id", "")
                        if test_id and test_id not in seen_test_ids:
                            seen_test_ids.add(test_id)
                            test_results.append(r)
                            yield _sse_english_event({
                                "type": "test_result",
                                "id": r.get("id"),
                                "title": r.get("title"),
                                "status": r.get("status")
                            })
                            if r.get("status") == "PASS":
                                passed_count += 1
                            else:
                                failed_count += 1

        # Close any phases not yet closed
        if not phase3_emitted:
            yield _sse_english_event({"type": "phase_end", "phase": 2, "status": "ok",
                                       "message": "App discovery completed"})
            yield _sse_english_event({"type": "phase_start", "phase": 3, "name": "Test Formatting"})
            for case in parsed_cases:
                yield _sse_english_event({"type": "test_formatted",
                                           "test_id": case.get("test_id"), "title": case.get("title")})
            yield _sse_english_event({"type": "phase_end", "phase": 3, "status": "ok",
                                       "message": f"Formatted {len(parsed_cases)} test cases"})
            yield _sse_english_event({"type": "phase_start", "phase": 4, "name": "Test Execution"})

        yield _sse_english_event({
            "type": "phase_end",
            "phase": 4,
            "status": "ok",
            "message": f"Execution completed: {passed_count} passed, {failed_count} failed"
        })

        # PHASE 5: Report Generation
        yield _sse_english_event({
            "type": "phase_start",
            "phase": 5,
            "name": "Report Generation"
        })

        report_html = _generate_english_test_report(
            parsed_cases, 
            test_results, 
            passed_count, 
            failed_count,
            app_url
        )
        _english_pipeline_state["report_html"] = report_html

        yield _sse_english_event({
            "type": "agent_message",
            "agent": "reporter",
            "content": "HTML test report generated successfully"
        })

        yield _sse_english_event({
            "type": "phase_end",
            "phase": 5,
            "status": "ok",
            "message": "Report generated"
        })

        # Cleanup by closing browser
        try:
            from agent_framework import BrowserTool
            tool = BrowserTool()
            tool.close_browser()
        except Exception as e:
            logger.debug(f"Browser cleanup: {e}")

        # Summary
        _english_pipeline_state["current_results"] = test_results
        yield _sse_english_event({
            "type": "test_summary",
            "total": len(test_results),
            "passed": passed_count,
            "failed": failed_count
        })

        yield _sse_english_event({
            "type": "pipeline_complete",
            "summary": f"{len(test_results)} tests executed | {passed_count} passed | {failed_count} failed"
        })

    except Exception as e:
        logger.error(f"English pipeline error: {e}", exc_info=True)
        yield _sse_english_event({"type": "error", "message": f"Pipeline error: {str(e)}"})

    yield "data: [DONE]\n\n"


def _generate_english_test_report(
    parsed_cases: List[Dict],
    test_results: List[Dict],
    passed_count: int,
    failed_count: int,
    app_url: str
) -> str:
    """Generate HTML test report"""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Report - English Test Pipeline</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header p {{ font-size: 14px; opacity: 0.9; }}
        .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; padding: 20px; background: #f9f9f9; border-bottom: 1px solid #eee; }}
        .metric {{ text-align: center; padding: 15px; background: white; border-radius: 6px; border-left: 4px solid #667eea; }}
        .metric .value {{ font-size: 32px; font-weight: bold; color: #667eea; }}
        .metric .label {{ font-size: 12px; color: #999; text-transform: uppercase; margin-top: 5px; }}
        .metric.pass {{ border-left-color: #22c55e; }}
        .metric.pass .value {{ color: #22c55e; }}
        .metric.fail {{ border-left-color: #ef4444; }}
        .metric.fail .value {{ color: #ef4444; }}
        .section {{ padding: 20px; border-bottom: 1px solid #eee; }}
        .section h2 {{ font-size: 18px; color: #333; margin-bottom: 15px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background: #f9f9f9; padding: 12px; text-align: left; font-weight: 600; color: #666; border-bottom: 2px solid #eee; font-size: 13px; }}
        td {{ padding: 12px; border-bottom: 1px solid #eee; font-size: 14px; }}
        tr:hover td {{ background: #f9f9f9; }}
        .status-pass {{ color: #22c55e; font-weight: 600; }}
        .status-fail {{ color: #ef4444; font-weight: 600; }}
        .footer {{ padding: 20px; background: #f9f9f9; border-radius: 0 0 8px 8px; text-align: center; font-size: 12px; color: #999; }}
        .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
        .badge-pass {{ background: #dcfce7; color: #166534; }}
        .badge-fail {{ background: #fee2e2; color: #991b1b; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>English Test Pipeline Report</h1>
            <p>Application: {app_url} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="metrics">
            <div class="metric">
                <div class="value">{len(test_results)}</div>
                <div class="label">Total Tests</div>
            </div>
            <div class="metric pass">
                <div class="value">{passed_count}</div>
                <div class="label">Passed</div>
            </div>
            <div class="metric fail">
                <div class="value">{failed_count}</div>
                <div class="label">Failed</div>
            </div>
            <div class="metric">
                <div class="value">{round(passed_count / len(test_results) * 100) if test_results else 0}%</div>
                <div class="label">Pass Rate</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Test Results</h2>
            <table>
                <thead>
                    <tr>
                        <th>Test ID</th>
                        <th>Title</th>
                        <th>Status</th>
                        <th>Priority</th>
                        <th>Evidence</th>
                    </tr>
                </thead>
                <tbody>
"""

    # Add test results rows
    for result in test_results:
        status = result.get("status", "N/A")
        status_class = "status-pass" if status == "PASS" else "status-fail"
        badge_class = "badge-pass" if status == "PASS" else "badge-fail"
        
        html += f"""                    <tr>
                        <td><strong>{result.get('id', 'N/A')}</strong></td>
                        <td>{result.get('title', 'N/A')}</td>
                        <td><span class="{status_class}">{status}</span></td>
                        <td><span class="badge {badge_class}">HIGH</span></td>
                        <td>{result.get('evidence', 'N/A')}</td>
                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>Test Cases Summary</h2>
            <table>
                <thead>
                    <tr>
                        <th>Test ID</th>
                        <th>Title</th>
                        <th>Priority</th>
                        <th>Steps</th>
                    </tr>
                </thead>
                <tbody>
"""

    for case in parsed_cases:
        html += f"""                    <tr>
                        <td><strong>{case.get('test_id', 'N/A')}</strong></td>
                        <td>{case.get('title', 'N/A')}</td>
                        <td>{case.get('priority', 'Medium')}</td>
                        <td>{len(case.get('steps', []))}</td>
                    </tr>
"""

    html += """                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>Report generated by Agentic QA Maestro - English Test Pipeline</p>
        </div>
    </div>
</body>
</html>"""
    
    return html


@app.post("/api/english-pipeline/parse")
async def parse_english_tests(file: UploadFile = File(...)):
    """Parse English test cases from uploaded file"""
    try:
        content = await file.read()
        text = content.decode('utf-8')
        
        parsed_cases = parse_english_test_cases(text)
        
        return {
            "status": "success",
            "cases_count": len(parsed_cases),
            "cases": parsed_cases
        }
    except Exception as e:
        logger.error(f"Error parsing test file: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/english-pipeline/run")
async def run_english_pipeline(request: Request):
    """Run English test pipeline"""
    async def error_stream(msg: str):
        yield _sse_english_event({"type": "error", "message": msg})
        yield "data: [DONE]\n\n"

    try:
        body = await request.json()
        test_cases_text = body.get("test_cases_text", "").strip()
        app_url = body.get("app_url", "").strip()
        username = body.get("username", "").strip()
        password = body.get("password", "").strip()

        if not test_cases_text:
            return StreamingResponse(error_stream("Test cases text cannot be empty. Please upload a test file."),
                                     media_type="text/event-stream")
        if not app_url:
            return StreamingResponse(error_stream("Application URL is required."),
                                     media_type="text/event-stream")
        if not username:
            return StreamingResponse(error_stream("Username is required."),
                                     media_type="text/event-stream")
        if not password:
            return StreamingResponse(error_stream("Password is required."),
                                     media_type="text/event-stream")

        # Pre-validate test cases can be parsed
        try:
            parsed = parse_english_test_cases(test_cases_text)
            if not parsed:
                return StreamingResponse(
                    error_stream(
                        "Could not parse any test cases from the file. "
                        "Supported formats:\n"
                        "  Format A: ## Test Case 1  (then ID:, Title:, Steps:)\n"
                        "  Format B: # TC001 - Login Test  (then numbered steps)\n"
                        "  Format C: Test Case: Title  (then numbered steps)\n"
                        "See sample_test_cases.md in the project folder for a working example."
                    ),
                    media_type="text/event-stream")
        except Exception as e:
            return StreamingResponse(error_stream(f"Error parsing test cases: {str(e)}"),
                                     media_type="text/event-stream")

        return StreamingResponse(
            _english_pipeline_stream(test_cases_text, app_url, username, password),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        logger.error(f"Error in English pipeline: {e}")
        return StreamingResponse(error_stream(str(e)), media_type="text/event-stream")


@app.post("/api/english-pipeline/stop")
async def stop_english_pipeline():
    """Stop English test pipeline"""
    global _english_pipeline_cancel
    _english_pipeline_cancel = True
    return {"status": "stopping"}


@app.get("/api/english-pipeline/report")
async def download_english_report():
    """Download generated test report"""
    try:
        report_html = _english_pipeline_state.get("report_html", "")
        if not report_html:
            return {"error": "No report available. Run pipeline first."}
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(report_html)
            temp_path = f.name
        
        return FileResponse(
            path=temp_path,
            filename=f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            media_type="text/html"
        )
    except Exception as e:
        logger.error(f"Error downloading report: {e}")
        return {"error": str(e)}


@app.get("/api/english-pipeline/report-preview")
async def preview_english_report():
    """Get HTML report as string (for preview in UI)"""
    try:
        report_html = _english_pipeline_state.get("report_html", "")
        if not report_html:
            return {"status": "no_report", "message": "No report available. Run pipeline first."}
        
        return {
            "status": "success",
            "html": report_html,
            "test_count": len(_english_pipeline_state.get("current_results", [])),
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error previewing report: {e}")
        return {"error": str(e)}


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
    safe_keys = [
        "azure_endpoint",
        "azure_model",
        "azure_version",
        "jira_url",
        "jira_project",
        "headless",
        "screenshot_dir",
    ]
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
        os.environ["JIRA_PAT"] = body["jira_pat"]
        os.environ["JIRA_API_TOKEN"] = body["jira_pat"]

    # Persist non-sensitive settings
    _save_settings(body)

    return {"status": "saved"}


def run_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn

    uvicorn.run(app, host=host, port=port)
