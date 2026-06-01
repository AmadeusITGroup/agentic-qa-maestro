"""
Full E2E Pipeline Runner for Agentic QA Maestro.

Runs the complete 6-phase test pipeline:
  Phase 1 — Requirement Analysis (JIRA fetch + AC extraction)
  Phase 2 — Targeted App Discovery (Playwright browser recon)
  Phase 3 — Test Case Generation (from requirements + UI discovery)
  Phase 4 — Test Execution (run tests against live app)
  Phase 5 — Bug Reporting (create bugs for failures, post summary)
  Phase 6 — Cleanup (close browser, final status)

Usage:
    python scripts/run_e2e_pipeline.py --ticket SACP-282967 --url https://app.example.com
    python scripts/run_e2e_pipeline.py --ticket SACP-282967  (analysis-only, no browser)
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

# SSL certificate setup for corporate proxy
_project_root = Path(__file__).resolve().parent.parent
_combined_bundle = _project_root / ".venv" / "combined_ca_bundle.pem"
if _combined_bundle.exists():
    os.environ.setdefault("SSL_CERT_FILE", str(_combined_bundle))
    os.environ.setdefault("REQUESTS_CA_BUNDLE", str(_combined_bundle))
elif os.path.exists("/etc/ssl/cert.pem"):
    os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
    os.environ.setdefault("REQUESTS_CA_BUNDLE", "/etc/ssl/cert.pem")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("e2e_pipeline")


def build_e2e_prompt(
    jira_ticket: str,
    target_url: str = "",
    auth_config: Optional[dict] = None,
    nav_hints: str = "",
) -> str:
    """Build the full 6-phase E2E pipeline prompt."""

    if target_url:
        # Full E2E mode with browser
        prompt = (
            f"Run the FULL 6-phase E2E test pipeline for JIRA ticket {jira_ticket} "
            f"against the application at {target_url}.\n\n"
            f"Execute ALL phases in order:\n\n"
            f"PHASE 1 — REQUIREMENT ANALYSIS:\n"
            f"  Use jira_get_issue to fetch {jira_ticket}. Extract ALL acceptance criteria,\n"
            f"  testable scenarios, and functional requirements.\n\n"
            f"PHASE 2 — APP DISCOVERY (login + navigate + discover REAL selectors):\n"
            f"  The goal is to discover the ACTUAL application UI — not just the login page.\n"
            f"  Use browser tools to:\n"
            f"  1. start_browser (headless=true)\n"
            f"  2. open_url({target_url})\n"
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
            f"  For FAILED tests: use jira_create_bug to create Bug tickets linked to {jira_ticket}.\n"
            f"  Post a comprehensive summary comment on {jira_ticket} with jira_add_comment.\n"
            f"  Include: total tests, passed, failed, bug ticket links.\n\n"
            f"PHASE 6 — CLEANUP:\n"
            f"  Use close_browser to cleanup. Provide final pipeline status summary.\n\n"
            f"IMPORTANT: Execute ALL phases autonomously. Never ask for user input.\n"
            f"IMPORTANT: The browser stays open across phases — do NOT close and reopen between phases."
        )
    else:
        # Analysis-only mode (no browser)
        prompt = (
            f"Run the E2E test pipeline for JIRA ticket {jira_ticket} in ANALYSIS-ONLY mode "
            f"(no target URL provided, skip browser phases).\n\n"
            f"Execute these phases:\n\n"
            f"PHASE 1 — REQUIREMENT ANALYSIS:\n"
            f"  Use jira_get_issue to fetch {jira_ticket}. Extract ALL acceptance criteria,\n"
            f"  testable scenarios, and functional requirements.\n\n"
            f"PHASE 3 — TEST CASE GENERATION:\n"
            f"  Generate comprehensive test cases from the requirements.\n"
            f"  Each test case: Test ID, Title, Priority, Steps, Expected Result, AC Coverage.\n\n"
            f"PHASE 5 — REPORTING:\n"
            f"  Post the generated test plan as a comment on {jira_ticket} using jira_add_comment.\n"
            f"  Include: scope, approach, all test cases, and coverage summary.\n\n"
            f"IMPORTANT: Execute ALL phases autonomously. Never ask for user input."
        )

    return prompt


async def run_e2e_pipeline(
    jira_ticket: str,
    target_url: str = "",
    config_path: str = "application.yaml",
    auth_config: Optional[dict] = None,
    nav_hints: str = "",
):
    """Run the full E2E pipeline."""
    mode = "FULL E2E" if target_url else "ANALYSIS ONLY"

    logger.info("=" * 70)
    logger.info("Agentic QA Maestro — E2E Test Pipeline")
    logger.info("=" * 70)
    logger.info(f"Mode:       {mode}")
    logger.info(f"Ticket:     {jira_ticket}")
    logger.info(f"Target URL: {target_url or '(none - analysis only)'}")
    logger.info(f"Started:    {datetime.now().isoformat()}")
    logger.info("=" * 70)

    # Load credentials from local .env
    local_env = Path(__file__).parent.parent / ".env"
    if local_env.exists():
        logger.info(f"Loading credentials from: {local_env}")
        from dotenv import load_dotenv

        load_dotenv(str(local_env), override=True)
        env_file = str(local_env)
    else:
        logger.warning("No .env file found, using current environment")
        env_file = None

    from agentic_qa_maestro.config import AppConfig, ConfigError

    try:
        _config = AppConfig(config_path=config_path, env_file=env_file)
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return False

    from agent_framework import AgentResponseUpdate, Message
    from agentic_qa_maestro.main import QAMaestro
    from agentic_qa_maestro.teams.group_chat_team import create_group_chat_team

    maestro = QAMaestro(config_path=config_path)

    try:
        logger.info("Initializing agents...")
        await maestro.initialize()
        logger.info(f"Agents ready: {list(maestro.agents.keys())}")

        prompt = build_e2e_prompt(jira_ticket, target_url, auth_config, nav_hints)

        logger.info(f"\nPipeline prompt ({len(prompt)} chars):")
        logger.info("-" * 40)

        # Build team with higher message limit for E2E
        team_config = maestro.config.teams.get("interactive", {})
        if target_url:
            team_config = {**team_config, "max_messages": 80}  # More messages for full E2E

        workflow = create_group_chat_team(agents=maestro.agents, team_config=team_config)

        logger.info("Starting pipeline execution...\n")
        start_time = datetime.now()

        last_response_id: Optional[str] = None
        message_count = 0
        async for event in workflow.run(prompt, stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, AgentResponseUpdate):
                    rid = data.response_id
                    if rid != last_response_id:
                        if last_response_id is not None:
                            print("\n")
                            message_count += 1
                        print(f"\n{'─' * 60}")
                        print(f"[{data.author_name}]:", end=" ", flush=True)
                        last_response_id = rid
                    print(data.text or "", end="", flush=True)
                elif isinstance(data, list):
                    print("\n" + "=" * 70)
                    print("\nPipeline Complete — Final Conversation:\n")
                    for msg in data:
                        if isinstance(msg, Message):
                            name = msg.author_name or msg.role
                            print(
                                f"[{name}] {msg.text[:500]}...\n"
                                if len(msg.text or "") > 500
                                else f"[{name}] {msg.text}\n"
                            )

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"\n{'=' * 70}")
        logger.info(f"Pipeline completed for {jira_ticket}")
        logger.info(f"Mode: {mode} | Messages: {message_count} | Duration: {elapsed:.1f}s")
        logger.info(f"{'=' * 70}")
        return True

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise
    finally:
        maestro.shutdown()


def main():
    parser = argparse.ArgumentParser(
        description="Run Full E2E Test Pipeline via Agentic QA Maestro"
    )
    parser.add_argument("--ticket", "-t", required=True, help="JIRA ticket key (e.g. SACP-282967)")
    parser.add_argument(
        "--url", "-u", required=True, help="Target application URL for browser testing (mandatory)"
    )
    parser.add_argument(
        "--username", required=True, help="App login username (or set APP_USERNAME env var)"
    )
    parser.add_argument(
        "--password", required=True, help="App login password (or set APP_PASSWORD env var)"
    )
    parser.add_argument("--config", "-c", default="application.yaml", help="Config file path")
    parser.add_argument("--tenant-id", default="", help="Azure AD tenant ID for authentication")
    parser.add_argument("--client-id", default="", help="Azure AD client ID")
    parser.add_argument("--client-secret", default="", help="Azure AD client secret")
    parser.add_argument("--scope", default="", help="Azure AD scope")
    parser.add_argument(
        "--auth-method",
        default="header",
        help="Auth method: header, token_url, easyauth, msal_cache",
    )
    parser.add_argument(
        "--nav-hints",
        default="",
        help="Navigation hints for the browser agent (e.g. 'After login, open Apps menu and search for ErrorViewer in the search box')",
    )

    args = parser.parse_args()

    # Set app credentials as env vars for the browser agent to use
    os.environ["CREDENTIAL_USERNAME"] = args.username
    os.environ["CREDENTIAL_PASSWORD"] = args.password

    auth_config = None
    if args.tenant_id and args.client_id:
        auth_config = {
            "tenant_id": args.tenant_id,
            "client_id": args.client_id,
            "client_secret": args.client_secret or os.environ.get("AAD_CLIENT_SECRET", ""),
            "scope": args.scope,
            "method": args.auth_method,
        }

    success = asyncio.run(
        run_e2e_pipeline(
            jira_ticket=args.ticket,
            target_url=args.url,
            config_path=args.config,
            auth_config=auth_config,
            nav_hints=args.nav_hints,
        )
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
