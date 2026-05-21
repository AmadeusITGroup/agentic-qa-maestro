"""
Configuration loader for Agentic QA Maestro.

Loads application.yaml with environment variable substitution (${env:VAR})
and self-referencing templates (${this:path.to.value}).
"""

import os
import re
import copy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


class ConfigError(Exception):
    """Raised when there's an error in the application configuration."""


class AppConfig:
    """Configuration manager for Agentic QA Maestro application."""

    _ENV_PATTERN = re.compile(r"\$\{env:([^}]+)\}")
    _THIS_PATTERN = re.compile(r"\$\{this:([^}]+)\}")

    def __init__(self, config_path: Optional[str] = None, env_file: Optional[str] = None):
        env_path = env_file or ".env"
        if Path(env_path).exists():
            load_dotenv(env_path)

        config_path = config_path or "application.yaml"
        if not Path(config_path).exists():
            raise ConfigError(f"Configuration file not found: {config_path}")

        with open(config_path, "r") as f:
            raw_config = yaml.safe_load(f)

        if not isinstance(raw_config, dict):
            raise ConfigError("Configuration must be a YAML dictionary")

        self._raw = raw_config
        self._config = self._apply_substitutions(copy.deepcopy(raw_config))

    @property
    def data(self) -> Dict[str, Any]:
        return self._config

    @property
    def models(self) -> Dict[str, Any]:
        return self._config.get("models", {})

    @property
    def agents(self) -> Dict[str, Any]:
        return self._config.get("agents", {})

    @property
    def mcp_servers(self) -> Dict[str, Any]:
        return self._config.get("mcp", {}).get("servers", {})

    @property
    def teams(self) -> Dict[str, Any]:
        return self._config.get("teams", {})

    @property
    def observability(self) -> Dict[str, Any]:
        return self._config.get("observability", {})

    @property
    def web_ui(self) -> Dict[str, Any]:
        return self._config.get("web_ui", {})

    def _apply_substitutions(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self._substitute_string(obj)
        elif isinstance(obj, dict):
            return {k: self._apply_substitutions(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._apply_substitutions(item) for item in obj]
        return obj

    def _substitute_string(self, value: str) -> str:
        result = self._ENV_PATTERN.sub(self._env_replacer, value)
        result = self._THIS_PATTERN.sub(self._this_replacer, result)
        return result

    def _env_replacer(self, match: re.Match) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ConfigError(
                f"Environment variable '{var_name}' is not set "
                f"(referenced as ${{env:{var_name}}})"
            )
        return value

    def _this_replacer(self, match: re.Match) -> str:
        path = match.group(1)
        keys = path.split(".")
        current = self._raw
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                raise ConfigError(
                    f"Config path '{path}' not found (referenced as ${{this:{path}}})"
                )
        if not isinstance(current, str):
            return str(current)
        return current
