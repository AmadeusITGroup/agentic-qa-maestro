"""Unit tests for team builders."""

from unittest.mock import MagicMock
import pytest

try:
    from agent_framework import Agent
    MAF_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    MAF_AVAILABLE = False

maf_required = pytest.mark.skipif(not MAF_AVAILABLE, reason="agent-framework not installed")


@maf_required
def test_group_chat_requires_orchestrator():
    from qa_maestro_maf.teams.group_chat_team import create_group_chat_team

    mock_agent = MagicMock(spec=Agent)
    agents = {"browser_agent": mock_agent}

    with pytest.raises(ValueError, match="orchestrator"):
        create_group_chat_team(agents=agents)


@maf_required
def test_sequential_team_empty_steps():
    from qa_maestro_maf.teams.sequential_team import create_sequential_team

    with pytest.raises(ValueError, match="at least one step"):
        create_sequential_team(agents={}, pipeline_config={"steps": []})


@maf_required
def test_sequential_team_unknown_agent():
    from qa_maestro_maf.teams.sequential_team import create_sequential_team

    mock_agent = MagicMock(spec=Agent)
    agents = {"browser_agent": mock_agent}

    with pytest.raises(ValueError, match="unknown agent"):
        create_sequential_team(
            agents=agents,
            pipeline_config={"steps": [{"agent": "nonexistent"}]},
        )
