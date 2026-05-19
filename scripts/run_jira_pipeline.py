"""
JIRA E2E Pipeline Runner for QA Maestro MAF.

Runs the 5-phase test pipeline for a given JIRA ticket:
  1. ANALYZE  — Fetch JIRA story, extract acceptance criteria
  2. GENERATE — Create test cases from requirements
  3. SUMMARIZE — Build test plan summary
  4. REPORT   — Log results back to JIRA
  5. SUMMARY  — Final status report

Usage:
    python scripts/run_jira_pipeline.py --ticket SACP-282967
    python scripts/run_jira_pipeline.py --ticket SACP-282967 --url https://app.example.com
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

from qa_maestro_maf.config import AppConfig, ConfigError

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
logger = logging.getLogger("jira_pipeline")


def build_pipeline_prompt(jira_ticket: str, target_url: str = "") -> str:
    prompt = (
        f"Fetch JIRA ticket {jira_ticket} using the jira_get_issue tool, "
        f"then generate test cases based on the story summary and description. "
        f"Do NOT ask for more information — use whatever is in the ticket. "
        f"After generating the test cases, post them as a comment on {jira_ticket} "
        f"using jira_add_comment. Finally, provide a brief summary of what was done."
    )
    if target_url:
        prompt += f"\n\nAlso test the application at: {target_url}"
    return prompt


async def run_pipeline(
    jira_ticket: str, target_url: str = "", config_path: str = "application.yaml"
):
    logger.info("=" * 60)
    logger.info("QA Maestro MAF — JIRA E2E Pipeline")
    logger.info("=" * 60)
    logger.info(f"Ticket:     {jira_ticket}")
    logger.info(f"Target URL: {target_url or '(none - analysis only)'}")
    logger.info(f"Started:    {datetime.now().isoformat()}")
    logger.info("=" * 60)

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

    try:
        config = AppConfig(config_path=config_path, env_file=env_file)
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return False

    try:
        from agent_framework import AgentResponseUpdate, Message
    except ImportError as e:
        logger.error(f"MAF import failed: {e}")
        logger.info("DRY RUN MODE (agent-framework not available)")
        prompt = build_pipeline_prompt(jira_ticket, target_url)
        print(prompt)
        logger.info(f"Agents configured: {list(config.agents.keys())}")
        return True

    from qa_maestro_maf.main import QAMaestro
    from qa_maestro_maf.teams.group_chat_team import create_group_chat_team

    maestro = QAMaestro(config_path=config_path)

    try:
        logger.info("Initializing agents...")
        await maestro.initialize()
        logger.info(f"Agents ready: {list(maestro.agents.keys())}")

        prompt = build_pipeline_prompt(jira_ticket, target_url)

        logger.info("Starting pipeline execution...")

        team_config = maestro.config.teams.get("interactive", {})
        workflow = create_group_chat_team(agents=maestro.agents, team_config=team_config)

        last_response_id: Optional[str] = None
        async for event in workflow.run(prompt, stream=True):
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

        logger.info(f"Pipeline completed for {jira_ticket}")
        return True

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
    finally:
        maestro.shutdown()


def main():
    parser = argparse.ArgumentParser(
        description="Run JIRA E2E Test Pipeline via QA Maestro MAF"
    )
    parser.add_argument("--ticket", "-t", required=True, help="JIRA ticket key")
    parser.add_argument("--url", "-u", default="", help="Target application URL")
    parser.add_argument("--config", "-c", default="application.yaml", help="Config file path")

    args = parser.parse_args()
    success = asyncio.run(
        run_pipeline(
            jira_ticket=args.ticket, target_url=args.url, config_path=args.config
        )
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
