"""Unit tests for Agent Framework factory."""

from unittest.mock import MagicMock
import pytest

try:
    from agent_framework import Agent  # noqa: F401

    AF_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    AF_AVAILABLE = False

af_required = pytest.mark.skipif(not AF_AVAILABLE, reason="agent-framework not installed")


@af_required
def test_default_prompts_exist():
    from agentic_qa_maestro.agents.factory import DEFAULT_PROMPTS

    expected = [
        "orchestrator",
        "browser_agent",
        "api_agent",
        "jira_agent",
        "research_agent",
        "test_runner_agent",
    ]
    for agent_name in expected:
        assert agent_name in DEFAULT_PROMPTS
        assert len(DEFAULT_PROMPTS[agent_name]) > 50


@af_required
def test_create_agent_with_mock_model():
    from agentic_qa_maestro.agents.factory import create_agent

    mock_model = MagicMock()
    agent_config = {"description": "Test agent"}

    agent = create_agent(
        agent_name="test_runner_agent",
        agent_config=agent_config,
        model_client=mock_model,
        tools=[],
    )
    assert agent.name == "test_runner_agent"
    assert agent.description == "Test agent"


@af_required
def test_create_agents_from_config():
    from agentic_qa_maestro.agents.factory import create_agents_from_config

    mock_model = MagicMock()
    agents_config = {
        "orchestrator": {"model": "default", "description": "Test orchestrator", "tools": []},
        "jira_agent": {"model": "default", "description": "Test JIRA", "tools": []},
    }
    model_clients = {"default": mock_model}

    agents = create_agents_from_config(
        agents_config=agents_config,
        model_clients=model_clients,
    )
    assert "orchestrator" in agents
    assert "jira_agent" in agents
    assert len(agents) == 2


@af_required
def test_create_agents_invalid_model():
    from agentic_qa_maestro.agents.factory import create_agents_from_config

    mock_model = MagicMock()
    agents_config = {
        "orchestrator": {"model": "nonexistent", "description": "Bad ref", "tools": []},
    }
    model_clients = {"default": mock_model}

    with pytest.raises(ValueError, match="nonexistent"):
        create_agents_from_config(
            agents_config=agents_config,
            model_clients=model_clients,
        )
