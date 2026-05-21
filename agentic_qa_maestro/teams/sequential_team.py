"""
Sequential team for deterministic QA test pipelines.

Uses Agent Framework SequentialBuilder to chain agents in a defined order.
"""

from typing import Any, Dict, List, Optional

from agent_framework import Agent
from agent_framework.orchestrations import SequentialBuilder


def create_sequential_team(
    agents: Dict[str, Agent],
    pipeline_config: Dict[str, Any],
) -> Any:
    """Build a SequentialBuilder workflow from pipeline configuration."""
    steps = pipeline_config.get("steps", [])

    if not steps:
        raise ValueError("Pipeline config must have at least one step")

    ordered_agents: List[Agent] = []
    for step in steps:
        agent_name = step["agent"]
        if agent_name not in agents:
            raise ValueError(f"Pipeline references unknown agent: '{agent_name}'")
        ordered_agents.append(agents[agent_name])

    workflow = SequentialBuilder(participants=ordered_agents).build()

    return workflow


def create_sequential_pipeline(
    agents: Dict[str, Agent],
    agent_order: List[str],
) -> Any:
    """Build a sequential pipeline from an ordered list of agent names."""
    steps = [{"agent": name} for name in agent_order]
    return create_sequential_team(agents=agents, pipeline_config={"steps": steps})
