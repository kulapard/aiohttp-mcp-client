"""Minimal MCP server for testing the client.

uv run examples/server.py
"""

from aiohttp import web
from aiohttp_mcp import AiohttpMCP, build_mcp_app

mcp = AiohttpMCP(name="example-server")


@mcp.tool()
async def greet(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}!"


app = build_mcp_app(mcp, path="/mcp")

if __name__ == "__main__":
    web.run_app(app, host="localhost", port=8080)
