# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-05-18

### Added

- Initial release of Agentic QA Maestro
- Multi-agent orchestration via Microsoft Agent Framework
- JIRA integration: fetch stories, extract acceptance criteria, report defects
- Browser testing via Playwright MCP server
- REST API contract testing
- Sequential and group-chat team execution modes
- Azure OpenAI model client with `DefaultAzureCredential` fallback
- OpenTelemetry tracing integration
- FastAPI web UI dashboard
- CLI entry point (`qa-maestro`)
- Configuration via `application.yaml` with `${env:VAR}` substitution
- GitHub Actions CI pipeline (ruff + pytest, Python 3.10–3.12)
