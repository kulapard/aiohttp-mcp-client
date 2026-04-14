"""Tests for client-side request cancellation."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from aiohttp_mcp import AiohttpMCP, build_mcp_app

from aiohttp_mcp_client import MCPClient


def _create_slow_server_app() -> web.Application:
    """Create an MCP server with a slow tool for cancellation testing."""
    from aiohttp_mcp import Context  # noqa: PLC0415

    mcp = AiohttpMCP(name="cancel-test-server")

    @mcp.tool()
    async def slow_tool(duration: float, ctx: Context) -> str:
        """A tool that sleeps and can be cancelled."""
        await ctx.info("Starting slow operation...")
        await asyncio.sleep(duration)
        await ctx.info("Finished!")
        return "done"

    return build_mcp_app(mcp, path="/mcp", stateless=True)


@pytest.fixture
async def slow_server() -> Any:
    app = _create_slow_server_app()
    server = TestServer(app)
    await server.start_server()
    try:
        yield f"http://localhost:{server.port}/mcp"
    finally:
        await server.close()


class TestCancellation:
    async def test_cancelled_task_raises(self, slow_server: str) -> None:
        """Cancelling the asyncio task should raise CancelledError."""
        async with MCPClient(slow_server) as client:
            task = asyncio.create_task(client.call_tool("slow_tool", {"duration": 60.0}))
            # Give the request time to start
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def test_cancelled_task_sends_notification(self, slow_server: str) -> None:
        """Cancellation should send notifications/cancelled to the server."""
        sent_notifications: list[dict[str, Any]] = []

        # Patch send_notification to capture what's sent
        from aiohttp_mcp_client import _transport  # noqa: PLC0415

        original_send_notification = _transport.send_notification

        async def capture_notification(**kwargs: Any) -> None:
            if kwargs.get("method") == "notifications/cancelled":
                sent_notifications.append(kwargs.get("params", {}))
            await original_send_notification(**kwargs)

        async with MCPClient(slow_server) as client:
            # Monkey-patch _send_cancel to capture the notification
            original_send_cancel = client._send_cancel

            async def patched_send_cancel(request_id: int) -> None:
                sent_notifications.append({"requestId": request_id})
                await original_send_cancel(request_id)

            client._send_cancel = patched_send_cancel  # type: ignore[method-assign]

            task = asyncio.create_task(client.call_tool("slow_tool", {"duration": 60.0}))
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert len(sent_notifications) == 1
        assert "requestId" in sent_notifications[0]

    async def test_client_usable_after_cancellation(self, slow_server: str) -> None:
        """Client should remain usable after a cancelled call."""
        async with MCPClient(slow_server) as client:
            # Cancel a slow call
            task = asyncio.create_task(client.call_tool("slow_tool", {"duration": 60.0}))
            await asyncio.sleep(0.2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            # Client should still work for subsequent calls
            tools = await client.list_tools()
            assert len(tools) >= 1


class TestCancellationUnit:
    """Unit tests for _send_cancel."""

    async def test_send_cancel_best_effort(self) -> None:
        """_send_cancel should not raise even if the notification fails."""
        client = MCPClient("http://localhost:9999")
        client._initialized = True
        client._session = MagicMock()
        client._session_id = "test-session"

        # Make send_notification raise
        from aiohttp_mcp_client import _transport  # noqa: PLC0415

        original = _transport.send_notification
        _transport.send_notification = AsyncMock(side_effect=Exception("connection lost"))
        try:
            await client._send_cancel(42)  # should not raise
        finally:
            _transport.send_notification = original
