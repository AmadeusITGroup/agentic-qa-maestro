# Quick Start

## Prerequisites

- Python 3.10, 3.11, or 3.12
- Access to Azure OpenAI (endpoint + API key or Azure AD credentials)
- JIRA instance with API token (for JIRA workflows)

## Installation

```bash
# Clone the repository
git clone https://github.com/nickmab/agentic-qa-maestro.git
cd agentic-qa-maestro

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Configuration

```bash
# Copy the example environment file
cp example.env .env
```

Edit `.env` with your credentials:

```dotenv
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_API_VERSION=2024-12-01-preview
JIRA_BASE_URL=https://your-jira-instance.atlassian.net
JIRA_API_TOKEN=your-jira-api-token
```

All secrets are loaded via environment variables — never hardcode them in config files.

## Run Tests

```bash
pytest
```

## Run a JIRA Pipeline (Analysis Only)

Fetches the JIRA ticket, generates test cases, and posts them as a comment:

```bash
python scripts/run_jira_pipeline.py --ticket SACP-282967
```

## Run the Full E2E Pipeline

The E2E pipeline executes all 6 phases against a live application. The `--url`, `--username`, and `--password` flags are **mandatory**.

```bash
python scripts/run_e2e_pipeline.py \
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
python scripts/run_e2e_pipeline.py \
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
uvicorn qa_maestro_maf.web_ui.app:app --port 8000
```

Open http://localhost:8000 in your browser.

## CLI Usage

```bash
qa-maestro --help
```

## Next Steps

- Review `application.yaml` for agent/team/model configuration
- See [ARCHITECTURE.md](ARCHITECTURE.md) for system design details
- See [CONTRIBUTING.md](CONTRIBUTING.md) to contribute
