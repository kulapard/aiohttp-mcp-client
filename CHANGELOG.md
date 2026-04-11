# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `MCPClient` — async MCP client with context manager and auto initialize/terminate lifecycle.
- Streamable HTTP transport with SSE and JSON response support.
- Core protocol methods: `list_tools`, `call_tool`, `list_resources`, `read_resource`, `list_resource_templates`, `list_prompts`, `get_prompt`, `ping`.
- Typed result objects: `Tool`, `ToolResult`, `Resource`, `ResourceContents`, `ResourceTemplate`, `Prompt`, `GetPromptResult`, content blocks.
- Exception hierarchy: `MCPError`, `MCPTransportError`, `MCPServerError`.
- Accepts optional external `aiohttp.ClientSession`.
- Notification callbacks (`on_log`, `on_progress`) for log messages and progress updates during tool calls. Configurable at client level and per-call.
- Pagination support via `cursor` parameter on all list methods. Returns `PaginatedResult` (a list subclass with `next_cursor` attribute).
- GET SSE stream for server-initiated notifications in stateful mode. Background task auto-starts when a session ID is present, with auto-reconnect.
- SSE resumability via `Last-Event-ID` header tracking for both POST and GET streams.
- Client-side request cancellation: cancelling an `asyncio.Task` running `call_tool` (or any method) sends `notifications/cancelled` to the server per MCP spec.

### Changed

- Removed `pydantic` from runtime dependencies. Only `aiohttp` is required.

## [0.0.1] - 2026-04-10

### Added

- Initial release to register the package name on PyPI.
- Project scaffolding with CI/CD, linting, and type checking.
