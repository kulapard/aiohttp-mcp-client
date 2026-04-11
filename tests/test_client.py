"""Integration tests for MCPClient against a real aiohttp-mcp server."""

from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from aiohttp_mcp import AiohttpMCP, build_mcp_app

from aiohttp_mcp_client import (
    MCPClient,
    MCPError,
    TextContent,
)


def _create_test_app() -> web.Application:
    """Create a minimal MCP server app for testing."""
    mcp = AiohttpMCP(name="test-server")

    @mcp.tool()
    async def add(a: int, b: int) -> str:
        """Add two numbers."""
        return str(a + b)

    @mcp.tool()
    async def greet(name: str) -> str:
        """Greet someone."""
        return f"Hello, {name}!"

    @mcp.resource("test://greeting")
    async def greeting_resource() -> str:
        """A greeting resource."""
        return "Hello from resource!"

    @mcp.resource("test://data/{key}")
    async def data_resource(key: str) -> str:
        """A parameterized resource."""
        return f"Data for {key}"

    @mcp.prompt()
    async def simple_prompt(topic: str) -> str:
        """A simple prompt."""
        return f"Tell me about {topic}"

    return build_mcp_app(mcp, path="/mcp")  # type: ignore[no-any-return]


@pytest.fixture
async def mcp_server() -> Any:
    """Start a test MCP server and yield its URL."""
    app = _create_test_app()
    server = TestServer(app)
    await server.start_server()
    try:
        yield f"http://localhost:{server.port}/mcp"
    finally:
        await server.close()


class TestMCPClientLifecycle:
    async def test_context_manager(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            # Should be initialized
            tools = await client.list_tools()
            assert len(tools) >= 1

    async def test_explicit_open_close(self, mcp_server: str) -> None:
        client = MCPClient(mcp_server)
        await client.open()
        try:
            tools = await client.list_tools()
            assert len(tools) >= 1
        finally:
            await client.close()

    async def test_not_initialized_raises(self, mcp_server: str) -> None:
        client = MCPClient(mcp_server)
        with pytest.raises(MCPError, match="not initialized"):
            await client.list_tools()

    async def test_custom_client_info(self, mcp_server: str) -> None:
        async with MCPClient(
            mcp_server, client_info={"name": "my-app", "version": "2.0.0"}
        ) as client:
            tools = await client.list_tools()
            assert isinstance(tools, list)


class TestPing:
    async def test_ping(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            await client.ping()  # Should not raise


class TestTools:
    async def test_list_tools(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert "add" in names
            assert "greet" in names

    async def test_tool_has_schema(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            tools = await client.list_tools()
            add_tool = next(t for t in tools if t.name == "add")
            assert add_tool.input_schema is not None
            assert "properties" in add_tool.input_schema

    async def test_call_tool(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            result = await client.call_tool("add", {"a": 2, "b": 3})
            assert not result.is_error
            assert len(result.content) >= 1
            assert isinstance(result.content[0], TextContent)
            assert result.content[0].text == "5"

    async def test_call_tool_greet(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            result = await client.call_tool("greet", {"name": "World"})
            assert not result.is_error
            assert isinstance(result.content[0], TextContent)
            assert result.content[0].text == "Hello, World!"

    async def test_call_nonexistent_tool(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            result = await client.call_tool("nonexistent_tool")
            assert result.is_error


class TestResources:
    async def test_list_resources(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            resources = await client.list_resources()
            uris = {r.uri for r in resources}
            assert "test://greeting" in uris

    async def test_read_resource(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            contents = await client.read_resource("test://greeting")
            assert len(contents) >= 1
            assert contents[0].text == "Hello from resource!"

    async def test_list_resource_templates(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            templates = await client.list_resource_templates()
            assert len(templates) >= 1
            template_uris = {t.uri_template for t in templates}
            assert "test://data/{key}" in template_uris


class TestPrompts:
    async def test_list_prompts(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            prompts = await client.list_prompts()
            names = {p.name for p in prompts}
            assert "simple_prompt" in names

    async def test_get_prompt(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            result = await client.get_prompt("simple_prompt", {"topic": "Python"})
            assert len(result.messages) >= 1
            assert result.messages[0].role == "user"


class TestPagination:
    async def test_list_tools_returns_paginated_result(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            tools = await client.list_tools()
            assert len(tools) >= 1
            assert tools.next_cursor is None  # server doesn't paginate in tests

    async def test_list_resources_returns_paginated_result(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            resources = await client.list_resources()
            assert len(resources) >= 1
            assert resources.next_cursor is None

    async def test_list_prompts_returns_paginated_result(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            prompts = await client.list_prompts()
            assert len(prompts) >= 1
            assert prompts.next_cursor is None

    async def test_list_resource_templates_returns_paginated_result(self, mcp_server: str) -> None:
        async with MCPClient(mcp_server) as client:
            templates = await client.list_resource_templates()
            assert len(templates) >= 1
            assert templates.next_cursor is None


class TestExternalSession:
    async def test_with_external_session(self, mcp_server: str) -> None:
        async with aiohttp.ClientSession() as session:
            async with MCPClient(mcp_server, session=session) as client:
                tools = await client.list_tools()
                assert len(tools) >= 1
            # Session should still be open after client closes
            assert not session.closed
