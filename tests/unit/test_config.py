"""Unit tests for Agentic QA Maestro configuration loader."""

import os
from pathlib import Path

import pytest
import yaml

from agentic_qa_maestro.config import AppConfig, ConfigError
from agentic_qa_maestro.runtime_assets import scaffold_runtime_files


@pytest.fixture
def sample_config(tmp_path):
    config = {
        "models": {
            "default": {
                "endpoint": "https://test.openai.azure.com/",
                "deployment": "gpt-4",
                "api_key": "test-key",
            }
        },
        "agents": {
            "orchestrator": {"model": "default", "description": "Test orchestrator", "tools": []}
        },
        "mcp": {"servers": {}},
        "teams": {"interactive": {"type": "group_chat", "max_messages": 10}},
    }
    config_path = tmp_path / "application.yaml"
    config_path.write_text(yaml.dump(config))
    return str(config_path)


@pytest.fixture
def config_with_env_vars(tmp_path):
    config = {
        "models": {
            "default": {
                "endpoint": "${env:TEST_ENDPOINT}",
                "deployment": "${env:TEST_DEPLOYMENT}",
                "api_key": "${env:TEST_API_KEY}",
            }
        },
        "agents": {},
        "mcp": {"servers": {}},
    }
    config_path = tmp_path / "application.yaml"
    config_path.write_text(yaml.dump(config))
    return str(config_path)


def test_load_config_basic(sample_config):
    config = AppConfig(config_path=sample_config)
    assert config.models["default"]["endpoint"] == "https://test.openai.azure.com/"
    assert config.models["default"]["deployment"] == "gpt-4"
    assert "orchestrator" in config.agents


def test_load_config_env_substitution(config_with_env_vars, monkeypatch):
    monkeypatch.setenv("TEST_ENDPOINT", "https://my-endpoint.openai.azure.com/")
    monkeypatch.setenv("TEST_DEPLOYMENT", "gpt-4.1")
    monkeypatch.setenv("TEST_API_KEY", "secret-key-123")

    config = AppConfig(config_path=config_with_env_vars)
    assert config.models["default"]["endpoint"] == "https://my-endpoint.openai.azure.com/"
    assert config.models["default"]["api_key"] == "secret-key-123"


def test_load_config_missing_env_var(config_with_env_vars):
    for var in ["TEST_ENDPOINT", "TEST_DEPLOYMENT", "TEST_API_KEY"]:
        os.environ.pop(var, None)
    with pytest.raises(ConfigError, match="Environment variable"):
        AppConfig(config_path=config_with_env_vars)


def test_load_config_file_not_found():
    with pytest.raises(ConfigError, match="not found"):
        AppConfig(config_path="/nonexistent/path.yaml")


def test_config_properties(sample_config):
    config = AppConfig(config_path=sample_config)
    assert isinstance(config.models, dict)
    assert isinstance(config.agents, dict)
    assert isinstance(config.mcp_servers, dict)
    assert isinstance(config.teams, dict)


def test_this_reference_substitution(tmp_path):
    config = {
        "common": {"base_url": "https://api.example.com"},
        "agents": {"api_agent": {"endpoint": "${this:common.base_url}"}},
    }
    config_path = tmp_path / "application.yaml"
    config_path.write_text(yaml.dump(config))

    app_config = AppConfig(config_path=str(config_path))
    assert app_config.agents["api_agent"]["endpoint"] == "https://api.example.com"


def test_load_packaged_default_config_without_local_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEFAULT_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("DEFAULT_OPENAI_DEPLOYMENT", "gpt-test")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "dummy-key")
    monkeypatch.setenv("DEFAULT_OPENAI_API_VERSION", "2024-12-01-preview")
    monkeypatch.setenv("JIRA_BASE_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "dummy-token")

    config = AppConfig()
    assert config.models["default"]["deployment"] == "gpt-test"
    assert config.mcp_servers["jira"]["env"]["JIRA_URL"] == "https://jira.example.com"


def test_scaffold_runtime_files_creates_templates(tmp_path):
    result = scaffold_runtime_files(tmp_path)

    assert str(tmp_path / "application.yaml") in result["created"]
    assert str(tmp_path / ".env") in result["created"]
    assert str(tmp_path / "app_flows" / "example-app.yaml") in result["created"]
    assert (tmp_path / "application.yaml").exists()
    assert (tmp_path / ".env").exists()
    assert (tmp_path / "app_flows" / "example-app.yaml").exists()
