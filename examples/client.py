"""Minimal MCP client example.

    uv run examples/server.py   # in another terminal
    uv run examples/client.py
"""

import asyncio

from aiohttp_mcp_client import MCPClient, TextContent


async def main() -> None:
    async with MCPClient("http://localhost:8080/mcp") as client:
        tools = await client.list_tools()
        print("Tools:", [t.name for t in tools])

        result = await client.call_tool("greet", {"name": "World"})
        assert isinstance(result.content[0], TextContent)
        print("Result:", result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
