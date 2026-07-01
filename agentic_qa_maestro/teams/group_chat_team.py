"""
GroupChat team for interactive QA orchestration.

Uses Agent Framework GroupChatBuilder with an agent-based orchestrator
to dynamically select the next agent based on conversation context.
"""

from typing import Any, Dict, Optional

from agent_framework import Agent
from agent_framework.orchestrations import GroupChatBuilder


def create_group_chat_team(
    agents: Dict[str, Agent],
    team_config: Optional[Dict[str, Any]] = None,
) -> Any:
    """Build a GroupChatBuilder workflow for interactive multi-agent orchestration."""
    team_config = team_config or {}
    max_messages = team_config.get("max_messages", 30)

    orchestrator = agents.get("orchestrator")
    if not orchestrator:
        raise ValueError("An 'orchestrator' agent is required for GroupChat")

    participants = [a for name, a in agents.items() if name != "orchestrator"]

    builder_kwargs = {
        "participants": participants,
        "termination_condition": lambda msgs: len(msgs) >= max_messages,
        "orchestrator_agent": orchestrator,
    }

    # Keep compatibility across Agent Framework versions.
    try:
        builder = GroupChatBuilder(
            **builder_kwargs,
            intermediate_output_from="all",
        )
    except TypeError:
        try:
            builder = GroupChatBuilder(
                **builder_kwargs,
                intermediate_outputs=True,
            )
        except TypeError:
            builder = GroupChatBuilder(**builder_kwargs)

    workflow = builder.with_termination_condition(lambda msgs: len(msgs) >= max_messages).build()

    return workflow
