"""Tests for _transport module — SSE parsing and HTTP transport."""

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from aiohttp_mcp_client._transport import (
    _extract_result,
    _iter_sse_events,
    send_request,
)
from aiohttp_mcp_client._types import MCPServerError, MCPTransportError


class _MockContent:
    """Mock for aiohttp.ClientResponse.content that supports async iteration."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[bytes]:
        for line in self._lines:
            yield line


def _make_mock_response(
    lines: list[bytes],
    *,
    status: int = 200,
    content_type: str = "text/event-stream",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Create a mock aiohttp.ClientResponse with an async content iterator."""
    response = MagicMock()
    response.status = status
    response.content_type = content_type
    response.headers = headers or {}
    response.content = _MockContent(lines)
    response.json = AsyncMock(return_value={})
    response.text = AsyncMock(return_value="")

    return response


class TestIterSseEvents:
    async def test_single_message(self) -> None:
        data = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        lines = [
            b"event: message\n",
            b"data: " + json.dumps(data).encode() + b"\n",
            b"\n",
        ]
        response = _make_mock_response(lines)
        events = [e async for e in _iter_sse_events(response)]
        assert len(events) == 1
        assert events[0] == data

    async def test_notification_then_response(self) -> None:
        notification = {"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info"}}
        response_msg = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        lines = [
            b"event: message\n",
            b"data: " + json.dumps(notification).encode() + b"\n",
            b"\n",
            b"event: message\n",
            b"data: " + json.dumps(response_msg).encode() + b"\n",
            b"\n",
        ]
        response = _make_mock_response(lines)
        events = [e async for e in _iter_sse_events(response)]
        assert len(events) == 2
        assert events[0] == notification
        assert events[1] == response_msg

    async def test_skips_comments_and_ids(self) -> None:
        data = {"jsonrpc": "2.0", "id": 1, "result": {}}
        lines = [
            b": this is a comment\n",
            b"event: message\n",
            b"id: some-event-id\n",
            b"data: " + json.dumps(data).encode() + b"\n",
            b"\n",
        ]
        response = _make_mock_response(lines)
        events = [e async for e in _iter_sse_events(response)]
        assert len(events) == 1

    async def test_skips_non_message_events(self) -> None:
        lines = [
            b"event: endpoint\n",
            b"data: something\n",
            b"\n",
        ]
        response = _make_mock_response(lines)
        events = [e async for e in _iter_sse_events(response)]
        assert len(events) == 0

    async def test_invalid_json_raises(self) -> None:
        lines = [
            b"event: message\n",
            b"data: {invalid json}\n",
            b"\n",
        ]
        response = _make_mock_response(lines)
        with pytest.raises(MCPTransportError, match="Invalid JSON"):
            async for _ in _iter_sse_events(response):
                pass

    async def test_multiline_data(self) -> None:
        data = {"jsonrpc": "2.0", "id": 1, "result": {"key": "value"}}
        json_str = json.dumps(data)
        lines = [
            b"event: message\n",
            b"data: " + json_str.encode() + b"\n",
            b"\n",
        ]
        response = _make_mock_response(lines)
        events = [e async for e in _iter_sse_events(response)]
        assert events[0]["result"]["key"] == "value"

    async def test_flush_on_stream_end_without_blank(self) -> None:
        """Stream ends without trailing blank line — should still yield the event."""
        data = {"jsonrpc": "2.0", "id": 1, "result": {}}
        lines = [
            b"event: message\n",
            b"data: " + json.dumps(data).encode() + b"\n",
        ]
        response = _make_mock_response(lines)
        events = [e async for e in _iter_sse_events(response)]
        assert len(events) == 1


class TestExtractResult:
    def test_success(self) -> None:
        msg = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        assert _extract_result(msg) == {"tools": []}

    def test_error_raises(self) -> None:
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        with pytest.raises(MCPServerError) as exc_info:
            _extract_result(msg)
        assert exc_info.value.code == -32601

    def test_missing_both_raises(self) -> None:
        msg = {"jsonrpc": "2.0", "id": 1}
        with pytest.raises(MCPTransportError, match="neither 'result' nor 'error'"):
            _extract_result(msg)


class TestSendRequest:
    async def test_json_response(self) -> None:
        result_data = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content_type = "application/json"
        mock_response.headers = {"mcp-session-id": "test-session"}
        mock_response.json = AsyncMock(return_value=result_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)

        result, session_id = await send_request(
            http_session=mock_session,
            url="http://test/mcp",
            method="tools/list",
            params=None,
            request_id=1,
            session_id=None,
        )
        assert result == {"tools": []}
        assert session_id == "test-session"

    async def test_http_error_raises(self) -> None:
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.text = AsyncMock(return_value="Not Found")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)

        with pytest.raises(MCPTransportError, match="HTTP 404"):
            await send_request(
                http_session=mock_session,
                url="http://test/mcp",
                method="tools/list",
                params=None,
                request_id=1,
                session_id=None,
            )

    async def test_sse_response_with_notification(self) -> None:
        notification = {"jsonrpc": "2.0", "method": "notifications/message", "params": {"level": "info"}}
        response_msg = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}

        lines = [
            b"event: message\n",
            b"data: " + json.dumps(notification).encode() + b"\n",
            b"\n",
            b"event: message\n",
            b"data: " + json.dumps(response_msg).encode() + b"\n",
            b"\n",
        ]

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.content_type = "text/event-stream"
        mock_response.headers = {}
        mock_response.content = _MockContent(lines)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_response)

        result, session_id = await send_request(
            http_session=mock_session,
            url="http://test/mcp",
            method="tools/list",
            params=None,
            request_id=1,
            session_id=None,
        )
        assert result == {"tools": []}
        assert session_id is None
