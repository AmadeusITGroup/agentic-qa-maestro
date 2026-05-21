"""
Main entry point for Agentic QA Maestro.

Loads configuration, creates agents and teams,
then runs the selected orchestration mode (interactive or pipeline).
"""

import asyncio
import signal
import sys
from typing import Any, Dict, List, Optional, cast

from agent_framework import AgentResponseUpdate, Message

from agentic_qa_maestro.config import AppConfig
from agentic_qa_maestro.models.azure_openai import create_model_clients_from_config
from agentic_qa_maestro.agents.factory import create_agents_from_config
from agentic_qa_maestro.teams.group_chat_team import create_group_chat_team
from agentic_qa_maestro.teams.sequential_team import create_sequential_team


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
            raise ValueError(
                f"Pipeline '{pipeline_name}' not found. Available: {available}"
            )

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


async def async_main(
    config_path: Optional[str] = None,
    mode: str = "chat",
    task: Optional[str] = None,
    pipeline: Optional[str] = None,
) -> None:
    """Async main entry point."""
    maestro = QAMaestro(config_path=config_path)

    def signal_handler(sig, frame):
        maestro.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await maestro.initialize()

        if mode == "chat":
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
            print("  qa-maestro --mode run --task 'Test the login page'")
            print("  qa-maestro --mode pipeline --pipeline e2e_test_pipeline")

    finally:
        maestro.shutdown()


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Agentic QA Maestro")
    parser.add_argument(
        "--config", default="application.yaml", help="Path to configuration file"
    )
    parser.add_argument(
        "--mode",
        choices=["chat", "run", "pipeline"],
        default="chat",
        help="Execution mode",
    )
    parser.add_argument("--task", help="Task to execute")
    parser.add_argument("--pipeline", help="Pipeline name")

    args = parser.parse_args()

    asyncio.run(
        async_main(
            config_path=args.config, mode=args.mode, task=args.task, pipeline=args.pipeline
        )
    )


if __name__ == "__main__":
    main()
