# Agentic QA Maestro

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-alpha-yellow.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Security Policy](https://img.shields.io/badge/security-policy-orange.svg)](SECURITY.md)

Fully automated testing from JIRA stories to defect management, powered by [Microsoft Agent Framework (MAF)](https://github.com/microsoft/agent-framework).

## Overview

QA Maestro MAF is an intelligent QA automation system that uses multiple AI agents
orchestrated through MAF to perform end-to-end testing workflows. It can:

- **Fetch JIRA stories** and extract acceptance criteria
- **Generate test cases** from requirements
- **Run browser tests** via Playwright
- **Test REST APIs** for contract compliance
- **Report results** back to JIRA

## Architecture

```
┌─────────────────────────────────────────────────┐
│              application.yaml                    │
│  (models, agents, teams, observability)          │
└─────────────┬───────────────────────────────────┘
              │
    ┌─────────▼─────────┐
    │    QAMaestro       │
    │  (main.py)         │
    └────┬──────────┬────┘
         │          │
  ┌──────▼──┐  ┌───▼──────────┐
  │GroupChat │  │ Sequential   │
  │Builder   │  │ Builder      │
  └──────┬───┘  └───┬──────────┘
         │          │
    ┌────▼──────────▼────┐
    │   MAF Agents        │
    │  ┌──────────────┐   │
    │  │ Orchestrator  │   │
    │  │ JIRA Agent    │   │
    │  │ Browser Agent │   │
    │  │ API Agent     │   │
    │  │ Research Agent│   │
    │  │ Test Runner   │   │
    │  └──────────────┘   │
    └─────────────────────┘
```

### Key Differences from AutoGen Version

| Feature | AutoGen | MAF |
|---------|---------|-----|
| Agent class | `AssistantAgent` | `Agent` |
| Model client | `AzureOpenAIChatCompletionClient` | `OpenAIChatCompletionClient` |
| Group chat | `SelectorGroupChat` | `GroupChatBuilder` |
| Sequential pipeline | `GraphFlow` / `DiGraphBuilder` | `SequentialBuilder` |
| Tool decorator | plain async functions | `@tool(approval_mode=...)` |
| Orchestration | LLM-based selector prompt | Agent-based orchestrator |
| Package | `autogen-agentchat` | `agent-framework` |

## Quick Start

See [GETTINGSTARTED.md](GETTINGSTARTED.md) for full installation, configuration, and usage instructions.

```bash
pip install -e ".[dev]"
cp example.env .env
pytest
```

## Project Structure

```
qa-maestro-maf/
├── application.yaml          # Main config
├── pyproject.toml             # Dependencies
├── qa_maestro_maf/
│   ├── main.py                # Entry point & QAMaestro class
│   ├── config.py              # YAML config loader with env substitution
│   ├── agents/factory.py      # Agent creation from config
│   ├── models/azure_openai.py # Azure OpenAI client factory
│   ├── teams/
│   │   ├── group_chat_team.py # GroupChatBuilder orchestration
│   │   └── sequential_team.py # SequentialBuilder pipelines
│   ├── tools/
│   │   ├── jira_tools.py      # Native JIRA API tools
│   │   └── local_tools.py     # Pytest runner, time, etc.
│   ├── observability/         # OpenTelemetry tracing
│   └── web_ui/                # FastAPI dashboard
├── scripts/
│   └── run_jira_pipeline.py   # JIRA pipeline runner
└── tests/unit/                # Unit tests
```

## More Usage Examples

### Run a group chat QA session
```bash
python -m qa_maestro_maf.main --team group_chat --query "Test login page for accessibility"
```

### Run a sequential pipeline
```bash
python -m qa_maestro_maf.main --team sequential --ticket SACP-282967
```

### Run with OpenTelemetry tracing enabled
```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
python scripts/run_jira_pipeline.py --ticket SACP-282967
```

## CI/CD Automation

You can integrate QA Maestro MAF into your CI pipeline:

```yaml
# Example GitHub Actions step
- name: Run QA Maestro MAF tests
  run: |
    pip install -e ".[dev]"
    pytest --cov=qa_maestro_maf --cov-report=xml
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute.

## Security

See [SECURITY.md](SECURITY.md) for our security policy and how to report vulnerabilities.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache-2.0 — see [LICENSE](LICENSE) for details.
