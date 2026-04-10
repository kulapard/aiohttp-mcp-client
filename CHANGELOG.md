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

### Changed

- Removed `pydantic` from runtime dependencies. Only `aiohttp` is required.

## [0.0.1] - 2026-04-10

### Added

- Initial release to register the package name on PyPI.
- Project scaffolding with CI/CD, linting, and type checking.
