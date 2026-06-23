"""
Main entry point for Agentic QA Maestro.

Loads configuration, creates agents and teams,
then runs the selected orchestration mode (interactive or pipeline).
"""

import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from agent_framework import AgentResponseUpdate, Message
from dotenv import load_dotenv

from agentic_qa_maestro.config import AppConfig
from agentic_qa_maestro.models.azure_openai import create_model_clients_from_config
from agentic_qa_maestro.agents.factory import create_agents_from_config
from agentic_qa_maestro.runtime_assets import scaffold_runtime_files
from agentic_qa_maestro.teams.group_chat_team import create_group_chat_team
from agentic_qa_maestro.teams.sequential_team import create_sequential_team


def _bootstrap_runtime_environment() -> None:
    """Load the local .env and default SSL trust settings for CLI execution."""
    project_root = Path(__file__).resolve().parent.parent
    local_env = project_root / ".env"
    if local_env.exists():
        load_dotenv(local_env, override=True)

    combined_bundle = project_root / ".venv" / "combined_ca_bundle.pem"
    if combined_bundle.exists():
        os.environ.setdefault("SSL_CERT_FILE", str(combined_bundle))
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(combined_bundle))
    elif os.path.exists("/etc/ssl/cert.pem"):
        os.environ.setdefault("SSL_CERT_FILE", "/etc/ssl/cert.pem")
        os.environ.setdefault("REQUESTS_CA_BUNDLE", "/etc/ssl/cert.pem")


def _run_init_command(argv: list[str]) -> int:
    """Scaffold local runtime files for installed-package usage."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="qa-maestro init",
        description="Create local runtime files for Agentic QA Maestro.",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Destination directory for application.yaml, .env, and app_flows/",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in the destination directory",
    )
    args = parser.parse_args(argv)

    destination = Path(args.path).expanduser().resolve()
    result = scaffold_runtime_files(destination, force=args.force)

    print(f"Initialized Agentic QA Maestro files in {destination}")
    if result["created"]:
        print("Created:")
        for path in result["created"]:
            print(f"  - {path}")
    if result["skipped"]:
        print("Skipped existing files:")
        for path in result["skipped"]:
            print(f"  - {path}")

    print("Next steps:")
    print("  1. Edit .env with your Azure OpenAI and JIRA credentials")
    print("  2. Run `playwright install chromium` before full browser E2E runs")
    return 0


class QAMaestro:
    """Main application class for Agentic QA Maestro."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = AppConfig(config_path=config_path)
        self._shutdown = False
        self.agents: Dict[str, Any] = {}
        self.model_clients: Dict[str, Any] = {}

    async def initialize(self) -> None:
        """Initialize all components: models, agents."""
        self.model_clients = create_model_clients_from_config(self.config.models)

        self.agents = create_agents_from_config(
            agents_config=self.config.agents,
            model_clients=self.model_clients,
            mcp_tools={},
        )

    async def run_interactive(self, task: str) -> None:
        """Run in interactive mode using GroupChat orchestration."""
        team_config = self.config.teams.get("interactive", {})
        workflow = create_group_chat_team(agents=self.agents, team_config=team_config)

        last_response_id: Optional[str] = None
        async for event in workflow.run(task, stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, AgentResponseUpdate):
                    rid = data.response_id
                    if rid != last_response_id:
                        if last_response_id is not None:
                            print("\n")
                        print(f"{data.author_name}:", end=" ", flush=True)
                        last_response_id = rid
                    print(data.text or "", end="", flush=True)
                elif isinstance(data, list):
                    print("\n" + "=" * 60)
                    print("\nFinal Conversation:\n")
                    for msg in data:
                        if isinstance(msg, Message):
                            name = msg.author_name or msg.role
                            print(f"[{name}] {msg.text}\n")

    async def run_pipeline(self, pipeline_name: str, task: str) -> None:
        """Run a deterministic pipeline using SequentialBuilder."""
        pipeline_config = self.config.teams.get(pipeline_name)
        if not pipeline_config:
            available = list(self.config.teams.keys())
            raise ValueError(f"Pipeline '{pipeline_name}' not found. Available: {available}")

        workflow = create_sequential_team(agents=self.agents, pipeline_config=pipeline_config)

        last_response_id: Optional[str] = None
        async for event in workflow.run(task, stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, AgentResponseUpdate):
                    rid = data.response_id
                    if rid != last_response_id:
                        if last_response_id is not None:
                            print("\n")
                        print(f"{data.author_name}:", end=" ", flush=True)
                        last_response_id = rid
                    print(data.text or "", end="", flush=True)
                elif isinstance(data, list):
                    print("\n" + "=" * 60)
                    print("\nPipeline Output:\n")
                    for msg in data:
                        if isinstance(msg, Message):
                            name = msg.author_name or msg.role
                            print(f"[{name}] {msg.text}\n")

    async def run_prompt(self, task: str, max_messages: Optional[int] = None) -> None:
        """Run a single prompt via the interactive team with optional message override."""
        team_config = self.config.teams.get("interactive", {})
        if max_messages is not None:
            team_config = {**team_config, "max_messages": max_messages}

        workflow = create_group_chat_team(agents=self.agents, team_config=team_config)

        last_response_id: Optional[str] = None
        async for event in workflow.run(task, stream=True):
            if event.type == "output":
                data = event.data
                if isinstance(data, AgentResponseUpdate):
                    rid = data.response_id
                    if rid != last_response_id:
                        if last_response_id is not None:
                            print("\n")
                        print(f"{data.author_name}:", end=" ", flush=True)
                        last_response_id = rid
                    print(data.text or "", end="", flush=True)
                elif isinstance(data, list):
                    print("\n" + "=" * 60)
                    print("\nFinal Conversation:\n")
                    for msg in data:
                        if isinstance(msg, Message):
                            name = msg.author_name or msg.role
                            print(f"[{name}] {msg.text}\n")

    async def run_chat_loop(self) -> None:
        """Run an interactive chat loop where users can send messages."""
        print("\nAgentic QA Maestro - Interactive Mode")
        print("=" * 50)
        print("Type your QA task or 'quit' to exit.\n")

        while not self._shutdown:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit", "q"):
                    break

                await self.run_interactive(task=user_input)
                print()

            except (KeyboardInterrupt, EOFError):
                break

        print("\nGoodbye!")

    def shutdown(self) -> None:
        """Clean up resources."""
        self._shutdown = True


def _build_ticket_prompt(
    jira_ticket: str,
    target_url: str = "",
    nav_hints: str = "",
) -> tuple[str, Optional[int]]:
    """Build a ticket-centric prompt for analysis-only or full E2E execution."""

    if target_url:
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
        return prompt, 80

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
    return prompt, None


async def run_full_e2e_ticket(
    jira_ticket: str,
    target_url: str,
    config_path: str = "application.yaml",
    nav_hints: str = "",
) -> bool:
    """Run the full browser-based E2E ticket workflow via the dedicated pipeline path."""
    _bootstrap_runtime_environment()

    # Mirror the dedicated runner's behavior and ensure the local .env wins.
    project_root = Path(__file__).resolve().parent.parent
    local_env = project_root / ".env"
    env_file = str(local_env) if local_env.exists() else None
    if env_file:
        load_dotenv(env_file, override=True)

    _ = AppConfig(config_path=config_path, env_file=env_file)
    maestro = QAMaestro(config_path=config_path)

    try:
        await maestro.initialize()

        prompt, _max_messages = _build_ticket_prompt(jira_ticket, target_url, nav_hints)
        team_config = maestro.config.teams.get("interactive", {})
        team_config = {**team_config, "max_messages": 80}
        workflow = create_group_chat_team(agents=maestro.agents, team_config=team_config)

        last_response_id: Optional[str] = None
        async for event in workflow.run(prompt, stream=True):
            if event.type != "output":
                continue

            data = event.data
            if isinstance(data, AgentResponseUpdate):
                rid = data.response_id
                if rid != last_response_id:
                    if last_response_id is not None:
                        print("\n")
                    print(f"{data.author_name}:", end=" ", flush=True)
                    last_response_id = rid
                print(data.text or "", end="", flush=True)
            elif isinstance(data, list):
                print("\n" + "=" * 60)
                print("\nFinal Conversation:\n")
                for msg in data:
                    if isinstance(msg, Message):
                        name = msg.author_name or msg.role
                        print(f"[{name}] {msg.text}\n")

        return True
    finally:
        maestro.shutdown()


async def async_main(
    config_path: Optional[str] = None,
    mode: str = "chat",
    task: Optional[str] = None,
    pipeline: Optional[str] = None,
    ticket: Optional[str] = None,
    target_url: str = "",
    username: str = "",
    password: str = "",
    nav_hints: str = "",
) -> None:
    """Async main entry point."""
    _bootstrap_runtime_environment()
    maestro = QAMaestro(config_path=config_path)

    def signal_handler(sig, frame):
        maestro.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        if ticket:
            if target_url and (not username or not password):
                raise ValueError("--username and --password are required when --url is provided")

            if username:
                os.environ["CREDENTIAL_USERNAME"] = username
            if password:
                os.environ["CREDENTIAL_PASSWORD"] = password

            if target_url:
                await run_full_e2e_ticket(
                    jira_ticket=ticket,
                    target_url=target_url,
                    config_path=config_path or "application.yaml",
                    nav_hints=nav_hints,
                )
                return

        await maestro.initialize()

        if ticket:
            prompt, max_messages = _build_ticket_prompt(ticket, target_url, nav_hints)
            await maestro.run_prompt(task=prompt, max_messages=max_messages)
        elif mode == "chat":
            await maestro.run_chat_loop()
        elif mode == "run" and task:
            await maestro.run_interactive(task=task)
        elif mode == "pipeline" and pipeline:
            await maestro.run_pipeline(
                pipeline_name=pipeline,
                task=task or f"Execute the {pipeline} pipeline",
            )
        else:
            print("Usage:")
            print("  qa-maestro                     # Interactive chat mode")
            print("  qa-maestro --ticket PROJ-123   # JIRA analysis pipeline")
            print(
                "  qa-maestro --ticket PROJ-123 --url https://app.example.com/login --username user --password pass"
            )
            print("  qa-maestro --mode run --task 'Test the login page'")
            print("  qa-maestro --mode pipeline --pipeline e2e_test_pipeline")

    finally:
        maestro.shutdown()


def main():
    """CLI entry point."""
    import argparse

    if len(sys.argv) > 1 and sys.argv[1] == "init":
        sys.exit(_run_init_command(sys.argv[2:]))

    parser = argparse.ArgumentParser(
        description="Agentic QA Maestro",
        epilog="Bootstrap a local runtime directory with: qa-maestro init",
    )
    parser.add_argument("--config", default="application.yaml", help="Path to configuration file")
    parser.add_argument(
        "--mode",
        choices=["chat", "run", "pipeline"],
        default="chat",
        help="Execution mode",
    )
    parser.add_argument("--task", help="Task to execute")
    parser.add_argument("--pipeline", help="Pipeline name")
    parser.add_argument("--ticket", help="JIRA ticket key for analysis-only or E2E execution")
    parser.add_argument("--url", default="", help="Target application URL for browser testing")
    parser.add_argument("--username", default="", help="Application login username")
    parser.add_argument("--password", default="", help="Application login password")
    parser.add_argument(
        "--nav-hints",
        default="",
        help="Navigation hints for the browser agent after login",
    )

    args = parser.parse_args()

    asyncio.run(
        async_main(
            config_path=args.config,
            mode=args.mode,
            task=args.task,
            pipeline=args.pipeline,
            ticket=args.ticket,
            target_url=args.url,
            username=args.username,
            password=args.password,
            nav_hints=args.nav_hints,
        )
    )


if __name__ == "__main__":
    main()
