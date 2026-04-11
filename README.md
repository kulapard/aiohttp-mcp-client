# aiohttp-mcp-client

[![CI](https://github.com/kulapard/aiohttp-mcp-client/actions/workflows/ci.yml/badge.svg)](https://github.com/kulapard/aiohttp-mcp-client/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/aiohttp-mcp-client.svg)](https://pypi.org/project/aiohttp-mcp-client/)
[![Python](https://img.shields.io/pypi/pyversions/aiohttp-mcp-client.svg)](https://pypi.org/project/aiohttp-mcp-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP ([Model Context Protocol](https://modelcontextprotocol.io/)) client built on top of [aiohttp](https://github.com/aio-libs/aiohttp). Supports the [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http) transport.

## Features

- Async context manager with automatic initialize/terminate lifecycle
- Supports both JSON and SSE response modes
- Accepts an external `aiohttp.ClientSession` for integration into existing apps
- Typed result objects (frozen dataclasses)
- Only 1 runtime dependency: `aiohttp`

## Installation

```bash
pip install aiohttp-mcp-client
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add aiohttp-mcp-client
```

## Quick Start

```python
import asyncio
from aiohttp_mcp_client import MCPClient

async def main():
    async with MCPClient("http://localhost:8080/mcp") as client:
        # List available tools
        tools = await client.list_tools()
        for tool in tools:
            print(f"  {tool.name}: {tool.description}")

        # Call a tool
        result = await client.call_tool("my_tool", {"arg": "value"})
        for block in result.content:
            print(block.text)

asyncio.run(main())
```

### Notification callbacks

The server can send log messages and progress updates during tool calls. You can handle these with async callbacks — set defaults at client level, or override per call:

```python
from aiohttp_mcp_client import MCPClient, LogMessage, Progress

async def on_log(msg: LogMessage) -> None:
    print(f"[{msg.level}] {msg.data}")

async def on_progress(msg: Progress) -> None:
    pct = f"{msg.progress}/{msg.total}" if msg.total else f"{msg.progress}"
    print(f"Progress: {pct}")

async def main():
    # Client-level defaults
    async with MCPClient(url, on_log=on_log, on_progress=on_progress) as client:
        result = await client.call_tool("slow_task", {"steps": 10})

        # Per-call override
        result = await client.call_tool("other_task", on_log=my_other_handler)
```

### Using an existing aiohttp session

```python
import aiohttp
from aiohttp_mcp_client import MCPClient

async def main():
    async with aiohttp.ClientSession() as session:
        async with MCPClient("http://localhost:8080/mcp", session=session) as client:
            tools = await client.list_tools()
```

## API

### `MCPClient(url, *, session=None, client_info=None, on_log=None, on_progress=None)`

- `url` — MCP server endpoint URL
- `session` — Optional `aiohttp.ClientSession` (one is created if not provided)
- `client_info` — Optional `{"name": "...", "version": "..."}` dict
- `on_log` — Default async callback for `LogMessage` notifications
- `on_progress` — Default async callback for `Progress` notifications

### Methods

| Method | Description |
|--------|-------------|
| `list_tools()` | List available tools |
| `call_tool(name, arguments)` | Call a tool |
| `list_resources()` | List available resources |
| `read_resource(uri)` | Read a resource by URI |
| `list_resource_templates()` | List resource templates |
| `list_prompts()` | List available prompts |
| `get_prompt(name, arguments)` | Get a prompt by name |
| `ping()` | Send a ping |

All methods except `ping()` accept optional `on_log` and `on_progress` keyword arguments to override the client-level defaults for that call.

## Future Plans

- GET SSE stream for server-initiated notifications
- Pagination support for list methods
- SSE resumability with `Last-Event-ID`

## Requirements

- Python 3.11+
- aiohttp >= 3.9.0

## Development

```bash
uv venv && source .venv/bin/activate
uv sync --all-extras
make test
make lint
```

## License

[MIT](LICENSE)
