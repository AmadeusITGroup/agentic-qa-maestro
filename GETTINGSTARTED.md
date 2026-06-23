# Quick Start

## Prerequisites

- Python 3.10, 3.11, or 3.12
- Access to Azure OpenAI (endpoint + API key or Azure AD credentials)
- JIRA instance with API token (for JIRA workflows)

## Installation

```bash
# Install the released CLI
pip install agentic-qa-maestro

# Or install it with uv
uv tool install agentic-qa-maestro
```

Use `pip` if you want the package in your current Python environment. Use `uv tool`
if you want an isolated CLI installation.

## Configuration

```bash
# Scaffold local runtime files
qa-maestro init
```

This creates:

- `application.yaml`
- `.env`
- `app_flows/example-app.yaml`

Edit `.env` with your credentials:

```dotenv
# Azure OpenAI (mandatory)
DEFAULT_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
DEFAULT_OPENAI_DEPLOYMENT=your-deployment-name
AZURE_OPENAI_API_KEY=your-api-key-here
DEFAULT_OPENAI_API_VERSION=2024-12-01-preview

# JIRA (mandatory)
JIRA_BASE_URL=https://your-jira-instance.atlassian.net
JIRA_API_TOKEN=your-jira-api-token
```

All secrets are loaded via environment variables — never hardcode them in config files.

## Browser Setup

Install Playwright's Chromium binary once before running the full E2E pipeline:

```bash
playwright install chromium
```

## Run Tests

```bash
qa-maestro --help
```

## Run a JIRA Pipeline (Analysis Only)

Fetches the JIRA ticket, generates test cases, and posts them as a comment:

```bash
qa-maestro --ticket SACP-282967
```

## Run the Full E2E Pipeline

The E2E pipeline executes all 6 phases against a live application. The `--url`, `--username`, and `--password` flags are **mandatory**.

```bash
qa-maestro \
  --ticket YOUR-TICKET-ID \
  --url "https://your-app.example.com/login" \
  --username "your-username" \
  --password "your-password"
```

### E2E Pipeline Phases

| Phase | Name | Description |
|-------|------|-------------|
| 1 | **Requirement Analysis** | Fetch JIRA ticket, extract acceptance criteria |
| 2 | **App Discovery** | Launch browser, navigate to URL, discover UI elements and selectors |
| 3 | **Test Case Generation** | Generate test cases from requirements + discovered UI |
| 4 | **Test Execution** | Execute tests against the live app, take screenshots as evidence |
| 5 | **Bug Reporting** | Create JIRA bug tickets for failures, post summary comment |
| 6 | **Cleanup** | Close browser, output final status |

### Optional: Azure AD Authentication

For apps behind Azure AD, pass additional auth flags:

```bash
qa-maestro \
  --ticket YOUR-TICKET-ID \
  --url "https://your-app.example.com" \
  --username "your-username" \
  --password "your-password" \
  --tenant-id "your-tenant-id" \
  --client-id "your-client-id" \
  --client-secret "your-client-secret" \
  --scope "api://your-scope/.default"
```

## Start the Web UI

```bash
python -m uvicorn agentic_qa_maestro.web_ui.app:app --port 8000
```

Open http://localhost:8000 in your browser.

## CLI Usage

```bash
qa-maestro --help
```

## Development Setup

If you want to work from a local source checkout instead of the released package,
use the contributor workflow from [CONTRIBUTING.md](CONTRIBUTING.md).

## Next Steps

- Review `application.yaml` for agent/team/model configuration
- See [ARCHITECTURE.md](ARCHITECTURE.md) for system design details
- See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute
