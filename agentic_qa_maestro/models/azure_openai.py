"""
Azure OpenAI model client factory for Agent Frameworks.

Creates OpenAIChatCompletionClient instances from YAML configuration,
with SSL support for corporate proxies.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from agent_framework.openai import OpenAIChatCompletionClient


def _get_ssl_cert_file() -> Optional[str]:
    """Find the best SSL certificate bundle for corporate proxy environments."""
    project_root = Path(__file__).resolve().parent.parent.parent
    combined_bundle = project_root / ".venv" / "combined_ca_bundle.pem"

    env_cert = os.environ.get("SSL_CERT_FILE")
    if env_cert and os.path.exists(env_cert):
        return env_cert
    elif combined_bundle.exists():
        return str(combined_bundle)
    elif os.path.exists("/etc/ssl/cert.pem"):
        return "/etc/ssl/cert.pem"
    return None


def _configure_ssl_env() -> None:
    """Set SSL environment variables so underlying OpenAI SDK uses correct certs."""
    cert_file = _get_ssl_cert_file()
    if cert_file:
        os.environ.setdefault("SSL_CERT_FILE", cert_file)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_file)


def create_model_client(
    model_config: Dict[str, Any],
    model_name: Optional[str] = None,
) -> OpenAIChatCompletionClient:
    """Create an OpenAIChatCompletionClient for Azure OpenAI from config."""
    _configure_ssl_env()

    endpoint = model_config.get("endpoint")
    if not endpoint:
        raise ValueError("Model config must include 'endpoint'")

    deployment = model_config.get("deployment")
    if not deployment:
        raise ValueError("Model config must include 'deployment'")

    api_key = model_config.get("api_key")
    api_version = model_config.get("api_version", "2024-12-01-preview")

    kwargs: Dict[str, Any] = {
        "azure_endpoint": endpoint,
        "model": deployment,
        "api_version": api_version,
    }

    if api_key:
        kwargs["api_key"] = api_key
    else:
        from azure.identity import DefaultAzureCredential

        kwargs["credential"] = DefaultAzureCredential()

    return OpenAIChatCompletionClient(**kwargs)


def create_model_clients_from_config(
    models_config: Dict[str, Any],
) -> Dict[str, OpenAIChatCompletionClient]:
    """Create model clients for all configured models."""
    clients = {}
    for name, config in models_config.items():
        clients[name] = create_model_client(config, model_name=name)
    return clients
