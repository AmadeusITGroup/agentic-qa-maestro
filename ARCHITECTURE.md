# Architecture — Agentic QA Maestro

> Multi-agent QA automation powered by [Microsoft Agent Framework](https://github.com/microsoft/agent-framework).

---

## High-Level Overview

```mermaid
graph TD
    subgraph UI["User Interface"]
        CLI["CLI (main)"]
        WebUI["Web UI (FastAPI)"]
    end

    subgraph Core["QAMaestro (main.py)"]
        Entry["Entry point — loads config, creates model clients & agents,<br/>dispatches to chosen execution mode<br/><br/>Modes: chat | run | pipeline"]
    end

    subgraph Teams["Team Orchestration"]
        GC["GroupChat Team<br/>(group_chat_team.py)<br/>Dynamic orchestrator selects<br/>the next agent at each turn"]
        SEQ["Sequential Team<br/>(sequential_team.py)<br/>Deterministic pipeline runs<br/>agents in fixed order"]
    end

    subgraph Agents["Agent Layer"]
        direction LR
        Orch["Orchestrator"]
        JIRA["JIRA Agent"]
        Browser["Browser Agent"]
        API["API Agent"]
        Research["Research Agent"]
        TestRunner["Test Runner"]
    end

    subgraph Tools["Tool Layer"]
        direction LR
        BT["Browser Tools<br/>(Playwright)"]
        JT["JIRA Tools<br/>(REST/httpx)"]
        LT["Local Tools<br/>(pytest, …)"]
        MCP["MCP Servers<br/>(external tools)"]
    end

    CLI --> Entry
    WebUI --> Entry
    Entry --> GC
    Entry --> SEQ
    GC --> Orch
    SEQ --> Orch
    Orch --> BT
    Orch --> JT
    Orch --> LT
    Orch --> MCP
```

---

## Execution Modes

```mermaid
graph TD
    UR["User Request"] --> Chat["Chat<br/>(interactive loop)"]
    UR --> Run["Run<br/>(one-shot task)"]
    UR --> Pipeline["Pipeline<br/>(sequential steps)"]

    Chat --> GC["GroupChat Orchestrator<br/>(dynamic agent select)"]
    Run --> GC
    Pipeline --> ST["Sequential Team<br/>(fixed order)"]
```

| Mode | Orchestration | Use Case |
|------|---------------|----------|
| **Chat** | GroupChat (dynamic) | Exploratory QA — user types tasks interactively |
| **Run** | GroupChat (dynamic) | One-shot task execution |
| **Pipeline** | Sequential (fixed) | Reproducible E2E pipelines in defined order |

---

## Data Flow

```mermaid
graph TD
    YAML["application.yaml"] --> Config["AppConfig (config.py)<br/>• env var substitution<br/>• self-referencing templates"]

    Config --> Models["Model Clients<br/>(azure_openai.py)"]
    Config --> AgentDefs["Agent Defs<br/>(factory.py)"]
    Config --> TeamCfg["Team Config<br/>(teams/*.py)"]

    Models --> Agents["Agent Framework Agent instances"]
    AgentDefs --> Agents
    TeamCfg --> Agents

    Agents --> ToolFns["@tool functions<br/>(browser, jira, local, mcp)"]

    ToolFns --> PW["Playwright<br/>(browser)"]
    ToolFns --> JIRAAPI["JIRA API<br/>(httpx)"]
    ToolFns --> Pytest["pytest<br/>(subprocess)"]
```

---

## Agent Roles

```mermaid
graph TD
    Orch["Orchestrator<br/>Coordinates the full<br/>E2E pipeline phases"] --> JIRA["JIRA Agent<br/>• Fetch issues<br/>• Extract criteria<br/>• Create bugs<br/>• Comment<br/>• Transition"]
    Orch --> Browser["Browser Agent<br/>• Start browser<br/>• Nav, click, fill<br/>• Screenshots<br/>• AAD auth"]
    Orch --> API["API Agent<br/>• REST calls<br/>• Contract test"]
    Orch --> Research["Research Agent<br/>• Web search<br/>• Doc lookup"]
    Orch --> TestRunner["Test Runner<br/>• pytest execute<br/>• Collect results<br/>• Analyze output"]
```

---

## E2E Pipeline Phases

```mermaid
graph LR
    P1["Phase 1<br/>Requirement Analysis<br/><br/>JIRA Agent<br/>fetches story + criteria"] --> P2["Phase 2<br/>App Discovery<br/><br/>Browser Agent<br/>explores UI via Playwright"]
    P2 --> P3["Phase 3<br/>Test Case Generation<br/><br/>Orchestrator<br/>creates tests from criteria"]
    P3 --> P4["Phase 4<br/>Test Execution<br/><br/>Browser Agent + Test Runner<br/>run tests"]
    P4 --> P5["Phase 5<br/>Bug Reporting<br/><br/>JIRA Agent<br/>files bugs, posts summary"]
    P5 --> P6["Phase 6<br/>Cleanup<br/><br/>Browser Agent<br/>closes browser"]
```

---

## Component Details

### Configuration (`config.py`)

Loads `application.yaml` with two substitution passes:

1. **Environment variables**: `${env:AZURE_OPENAI_API_KEY}` → value from env
2. **Self-references**: `${this:models.default.endpoint}` → value from config

Exposes typed sections: `.models`, `.agents`, `.teams`, `.mcp_servers`, `.observability`, `.web_ui`

### Model Client Factory (`models/azure_openai.py`)

- Creates `OpenAIChatCompletionClient` instances for Azure OpenAI
- Supports API key or `DefaultAzureCredential` (Azure AD)
- Auto-detects SSL certificate bundles for corporate proxy environments

### Agent Factory (`agents/factory.py`)

- Maps YAML agent definitions → Agent Framework `Agent` objects
- Assigns tools and model clients per agent
- Provides default system prompts for each role

### Tool Layer

| Module | Tools | External Dependency |
|--------|-------|---------------------|
| `browser_tools.py` | `start_browser`, `open_url`, `click`, `fill`, `select_option`, `wait_for_selector`, `get_text`, `get_page_content`, `screenshot`, `check_browser`, `close_browser`, `authenticate_aad` | Playwright (Chromium) |
| `jira_tools.py` | `jira_get_issue`, `jira_add_comment`, `jira_get_comments`, `jira_search_issues`, `jira_create_issue`, `jira_create_bug`, `jira_transition_issue` | JIRA REST API (httpx) |
| `local_tools.py` | `get_current_time`, `run_pytest`, `collect_pytest_tests` | pytest (subprocess) |

### Observability (`observability/tracing.py`)

```mermaid
graph TD
    ST["setup_tracing()"] --> Console["Console Exporter"]
    ST --> OTLP["OTLP (gRPC)"]
    ST --> AzMon["Azure Monitor Exporter"]
```

- OpenTelemetry tracing with configurable exporters
- Structured Python logging with suppression of noisy libraries

### Web UI (`web_ui/app.py`)

```mermaid
graph LR
    Browser["Browser"] --> FastAPI["FastAPI + Jinja2"]
    FastAPI --> GET_root["GET / → Dashboard (HTML)"]
    FastAPI --> POST_chat["POST /api/chat → Run group chat"]
    FastAPI --> GET_status["GET /api/status → Agent status"]
    FastAPI --> GET_history["GET /api/history → Run history"]
```

---

## Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Factory** | `create_model_clients_from_config()`, `create_agents_from_config()`, `create_*_team()` | Decouple creation from config |
| **Singleton** | Browser state in `browser_tools.py` (module-level globals + single-thread executor) | One browser instance, thread-safe |
| **Strategy** | AAD auth methods (`header`, `token_url`, `easyauth`, `msal_cache`); orchestration modes | Swap behavior at runtime |
| **Decorator** | `@tool(approval_mode=...)` on all tool functions | Register functions as Agent Framework tools |
| **Template Method** | `AppConfig._apply_substitutions()` | Recursive config resolution |

---

## Directory Structure

```
agentic-qa-maestro/
├── ARCHITECTURE.md            ← You are here
├── application.yaml           # All config: models, agents, teams, observability
├── pyproject.toml             # Package metadata & dependencies
├── example.env                # Template for environment variables
│
├── agentic_qa_maestro/
│   ├── main.py                # QAMaestro class & CLI entry point
│   ├── config.py              # YAML loader with env/self-ref substitution
│   │
│   ├── agents/
│   │   └── factory.py         # Agent creation from config
│   │
│   ├── models/
│   │   └── azure_openai.py    # Azure OpenAI client factory
│   │
│   ├── teams/
│   │   ├── group_chat_team.py # GroupChatBuilder orchestration
│   │   └── sequential_team.py # SequentialBuilder pipelines
│   │
│   ├── tools/
│   │   ├── browser_tools.py   # Playwright browser automation
│   │   ├── jira_tools.py      # JIRA REST API client
│   │   └── local_tools.py     # pytest runner, time utilities
│   │
│   ├── observability/
│   │   └── tracing.py         # OpenTelemetry + logging setup
│   │
│   └── web_ui/
│       ├── app.py             # FastAPI dashboard
│       └── templates/
│           └── index.html     # Dark-theme chat UI
│
├── scripts/
│   ├── run_e2e_pipeline.py    # Full 6-phase E2E runner
│   └── run_jira_pipeline.py   # Lightweight JIRA-only runner
│
└── tests/
    └── unit/                  # Unit tests
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | Microsoft Agent Framework |
| LLM Provider | Azure OpenAI (GPT-4.1) |
| Browser Automation | Playwright (Chromium) |
| Issue Tracking | JIRA (REST API via httpx) |
| Test Execution | pytest (subprocess) |
| Web Framework | FastAPI + Uvicorn + Jinja2 |
| Observability | OpenTelemetry (console / OTLP / Azure Monitor) |
| Auth | Azure Identity (DefaultAzureCredential / API keys) |
| Config | YAML + python-dotenv |
| Language | Python 3.10+ |
