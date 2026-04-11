# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

- **Run tests**: `uv run pytest` (with coverage reporting configured)
- **Lint code**: `make lint` (runs pre-commit hooks, mypy, and ty)
- **Type checking**: `uv run mypy .`
- **Build package**: `uv build`
- **Clean artifacts**: `make clean`
- **Install dependencies**: `uv sync --all-extras`

**Before every commit**, run `make lint` to ensure code passes ruff and mypy strict checks. Do not commit code that fails linting.

## Architecture Overview

This is a Python library (requires Python 3.11+) that provides an MCP client for Streamable HTTP servers, built on top of aiohttp.

### Runtime Dependencies

Only 1 runtime dependency: `aiohttp`

### Key Components

- **MCPClient** (`aiohttp_mcp_client/client.py`): High-level async client with context manager. Handles initialize/terminate lifecycle, request ID generation, and result parsing.
- **Transport** (`aiohttp_mcp_client/_transport.py`): Low-level HTTP POST/DELETE with SSE stream parsing. Stateless functions that accept an `aiohttp.ClientSession`.
- **Types** (`aiohttp_mcp_client/_types.py`): All exceptions and frozen dataclasses. Zero external dependencies.

### Design Decisions

- No pydantic — uses stdlib `dataclasses` and `typing` only
- No `mcp` SDK dependency — implements the wire protocol directly
- Transport layer is stateless (functions, not a class) — session state lives in `MCPClient`
- SSE parsing uses `response.content` line-by-line iteration (no buffering the full response)

## Testing

- Tests are located in the `tests/` directory
- Uses pytest-asyncio with `asyncio_mode = "auto"` (configured in pyproject.toml)
- Coverage reporting configured for branch coverage
- Integration tests use `aiohttp-mcp` (dev dependency) to spin up a real MCP server
- Run individual test files: `uv run pytest tests/test_<module>.py`

## Documentation Policy

When making meaningful code changes (new features, API changes, bug fixes, dependency changes, removed/added modules), you **must** update the relevant documentation in the same commit or PR:

- **`CHANGELOG.md`** -- Add an entry under `[Unreleased]` describing the change
- **`README.md`** -- Update if the change affects public API, usage examples, installation, or requirements
- **`CLAUDE.md`** -- Update if the change affects development workflow, architecture, or project conventions

Do not defer documentation to a follow-up task. Code and docs ship together.
