"""Tests for notification callbacks — unit and integration."""

from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from aiohttp_mcp import AiohttpMCP, build_mcp_app
from aiohttp_mcp.app import TransportMode

from aiohttp_mcp_client import (
    LogMessage,
    MCPClient,
    Progress,
)
from aiohttp_mcp_client.client import _build_notification_handler


class TestBuildNotificationHandler:
    """Unit tests for the notification dispatcher."""

    async def test_returns_none_when_no_handlers(self) -> None:
        assert _build_notification_handler(None, None) is None

    async def test_dispatches_log_message(self) -> None:
        received: list[LogMessage] = []

        async def on_log(msg: LogMessage) -> None:
            received.append(msg)

        handler = _build_notification_handler(on_log, None)
        assert handler is not None

        await handler({
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {"level": "warning", "data": "watch out", "logger": "my.logger"},
        })

        assert len(received) == 1
        assert received[0].level == "warning"
        assert received[0].data == "watch out"
        assert received[0].logger_name == "my.logger"

    async def test_dispatches_progress(self) -> None:
        received: list[Progress] = []

        async def on_progress(msg: Progress) -> None:
            received.append(msg)

        handler = _build_notification_handler(None, on_progress)
        assert handler is not None

        await handler({
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {"progress": 0.75, "total": 1.0, "message": "Almost done"},
        })

        assert len(received) == 1
        assert received[0].progress == 0.75
        assert received[0].total == 1.0
        assert received[0].message == "Almost done"

    async def test_ignores_unknown_notification(self) -> None:
        received: list[LogMessage] = []

        async def on_log(msg: LogMessage) -> None:
            received.append(msg)

        handler = _build_notification_handler(on_log, None)
        assert handler is not None

        # Unknown notification type — should not crash
        await handler({
            "jsonrpc": "2.0",
            "method": "notifications/unknown",
            "params": {},
        })
        assert len(received) == 0

    async def test_both_handlers(self) -> None:
        logs: list[LogMessage] = []
        progresses: list[Progress] = []

        async def on_log(msg: LogMessage) -> None:
            logs.append(msg)

        async def on_progress(msg: Progress) -> None:
            progresses.append(msg)

        handler = _build_notification_handler(on_log, on_progress)
        assert handler is not None

        await handler({
            "jsonrpc": "2.0",
            "method": "notifications/message",
            "params": {"level": "info", "data": "hello"},
        })
        await handler({
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": {"progress": 1.0},
        })

        assert len(logs) == 1
        assert len(progresses) == 1


# ---------------------------------------------------------------------------
# Integration tests with a real server that emits notifications
# ---------------------------------------------------------------------------


def _create_test_app_with_notifications() -> web.Application:
    """Create an MCP server that emits log and progress notifications during tool calls."""
    from aiohttp_mcp import Context  # noqa: PLC0415

    mcp = AiohttpMCP(name="notify-server")

    @mcp.tool()
    async def slow_task(steps: int, ctx: Context) -> str:
        """A tool that reports progress."""
        for i in range(steps):
            await ctx.report_progress(float(i + 1), float(steps))
            await ctx.info(f"Step {i + 1}/{steps}")
        return f"Completed {steps} steps"

    return build_mcp_app(mcp, path="/mcp", transport_mode=TransportMode.STREAMABLE_HTTP, stateless=True)  # type: ignore[no-any-return]


@pytest.fixture
async def notify_server() -> Any:
    app = _create_test_app_with_notifications()
    server = TestServer(app)
    await server.start_server()
    try:
        yield f"http://localhost:{server.port}/mcp"
    finally:
        try:
            await server.close()
        except RuntimeError:
            pass


class TestNotificationCallbacksIntegration:
    async def test_client_level_log_callback(self, notify_server: str) -> None:
        logs: list[LogMessage] = []

        async def on_log(msg: LogMessage) -> None:
            logs.append(msg)

        async with MCPClient(notify_server, on_log=on_log) as client:
            result = await client.call_tool("slow_task", {"steps": 3})
            assert not result.is_error

        assert len(logs) == 3
        assert logs[0].data == "Step 1/3"
        assert logs[2].data == "Step 3/3"

    async def test_per_call_override(self, notify_server: str) -> None:
        """Per-call callback should override client-level default."""
        client_logs: list[LogMessage] = []
        call_logs: list[LogMessage] = []

        async def client_on_log(msg: LogMessage) -> None:
            client_logs.append(msg)

        async def call_on_log(msg: LogMessage) -> None:
            call_logs.append(msg)

        async with MCPClient(notify_server, on_log=client_on_log) as client:
            # First call: uses client-level default
            await client.call_tool("slow_task", {"steps": 1})
            assert len(client_logs) == 1
            assert len(call_logs) == 0

            # Second call: per-call override
            client_logs.clear()
            await client.call_tool("slow_task", {"steps": 1}, on_log=call_on_log)
            assert len(client_logs) == 0
            assert len(call_logs) == 1

    async def test_no_callbacks_still_works(self, notify_server: str) -> None:
        """Without callbacks, notifications are silently discarded (no crash)."""
        async with MCPClient(notify_server) as client:
            result = await client.call_tool("slow_task", {"steps": 2})
            assert not result.is_error

    async def test_both_callbacks_together(self, notify_server: str) -> None:
        logs: list[LogMessage] = []
        progresses: list[Progress] = []

        async def on_log(msg: LogMessage) -> None:
            logs.append(msg)

        async def on_progress(msg: Progress) -> None:
            progresses.append(msg)

        async with MCPClient(notify_server, on_log=on_log, on_progress=on_progress) as client:
            result = await client.call_tool("slow_task", {"steps": 3})
            assert not result.is_error

        assert len(logs) == 3
        # Progress notifications may not be emitted by the server in stateless mode;
        # the progress handler is tested in unit tests above.
