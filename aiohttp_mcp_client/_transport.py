"""Low-level HTTP transport for MCP Streamable HTTP protocol.

Handles POST with JSON/SSE response parsing, session header management,
and session termination via DELETE.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp

from ._types import (
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_SSE,
    LATEST_PROTOCOL_VERSION,
    MCP_PROTOCOL_VERSION_HEADER,
    MCP_SESSION_ID_HEADER,
    MCPServerError,
    MCPTransportError,
)

logger = logging.getLogger(__name__)


def _parse_sse_data(data_lines: list[str]) -> dict[str, Any]:
    """Parse accumulated SSE data lines as JSON."""
    raw = "\n".join(data_lines)
    try:
        result: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPTransportError(f"Invalid JSON in SSE data: {raw!r}") from exc
    return result


async def _iter_sse_events(response: aiohttp.ClientResponse) -> AsyncGenerator[dict[str, Any], None]:
    """Parse SSE stream from an aiohttp response, yielding JSON-parsed messages.

    Only yields events with ``event: message`` and non-empty ``data:``.
    Raises MCPTransportError on JSON parse failure.
    """
    event_type: str | None = None
    data_lines: list[str] = []

    async for raw_line in response.content:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line == "":
            # Blank line = end of event
            if event_type == "message" and data_lines:
                yield _parse_sse_data(data_lines)
            event_type = None
            data_lines = []

    # Flush any remaining event (stream closed without trailing blank line)
    if event_type == "message" and data_lines:
        yield _parse_sse_data(data_lines)


def _extract_result(msg: dict[str, Any]) -> dict[str, Any]:
    """Extract the result from a JSON-RPC response, or raise on error."""
    if "error" in msg:
        err = msg["error"]
        raise MCPServerError(
            code=err.get("code", -1),
            message=err.get("message", "Unknown error"),
            data=err.get("data"),
        )
    if "result" in msg:
        result: dict[str, Any] = msg["result"]
        return result
    raise MCPTransportError(f"JSON-RPC response has neither 'result' nor 'error': {msg}")


def _build_headers(
    session_id: str | None,
    protocol_version: str,
) -> dict[str, str]:
    """Build MCP request headers."""
    headers: dict[str, str] = {
        "Content-Type": CONTENT_TYPE_JSON,
        "Accept": f"{CONTENT_TYPE_JSON}, {CONTENT_TYPE_SSE}",
    }
    if session_id:
        headers[MCP_SESSION_ID_HEADER] = session_id
    headers[MCP_PROTOCOL_VERSION_HEADER] = protocol_version
    return headers


async def send_request(
    http_session: aiohttp.ClientSession,
    url: str,
    method: str,
    params: dict[str, Any] | None,
    request_id: int,
    session_id: str | None,
    protocol_version: str = LATEST_PROTOCOL_VERSION,
) -> tuple[dict[str, Any], str | None]:
    """Send a JSON-RPC request and return (result_dict, session_id_from_response).

    Handles both ``application/json`` and ``text/event-stream`` responses.
    For SSE responses, notifications are silently consumed and only the
    final response is returned.

    Raises:
        MCPTransportError: On HTTP errors or unexpected response formats.
        MCPServerError: On JSON-RPC error responses.
    """
    headers = _build_headers(session_id, protocol_version)
    body = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        body["params"] = params

    async with http_session.post(url, json=body, headers=headers) as response:
        if response.status >= 400:
            text = await response.text()
            raise MCPTransportError(f"HTTP {response.status}: {text}")

        # Capture session ID from response headers
        new_session_id = response.headers.get(MCP_SESSION_ID_HEADER)

        content_type = response.content_type or ""

        if content_type.startswith(CONTENT_TYPE_SSE):
            # SSE stream: consume notifications, return final response
            async for msg in _iter_sse_events(response):
                if "result" in msg or "error" in msg:
                    return _extract_result(msg), new_session_id
                # Notification or other non-response message — skip
                logger.debug("SSE notification (discarded): %s", msg.get("method", "unknown"))
            raise MCPTransportError(f"SSE stream ended without a response for request {request_id}")

        # JSON response
        data: dict[str, Any] = await response.json()
        return _extract_result(data), new_session_id


async def send_notification(
    http_session: aiohttp.ClientSession,
    url: str,
    method: str,
    params: dict[str, Any] | None,
    session_id: str | None,
    protocol_version: str = LATEST_PROTOCOL_VERSION,
) -> None:
    """Send a JSON-RPC notification (no response expected).

    Raises:
        MCPTransportError: On HTTP errors.
    """
    headers = _build_headers(session_id, protocol_version)
    body: dict[str, Any] = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if params is not None:
        body["params"] = params

    async with http_session.post(url, json=body, headers=headers) as response:
        if response.status >= 400:
            text = await response.text()
            raise MCPTransportError(f"HTTP {response.status}: {text}")
        # 202 Accepted expected — no body to read


async def terminate_session(
    http_session: aiohttp.ClientSession,
    url: str,
    session_id: str,
    protocol_version: str = LATEST_PROTOCOL_VERSION,
) -> None:
    """Send DELETE to terminate the MCP session. Best-effort — errors are logged, not raised."""
    headers = _build_headers(session_id, protocol_version)
    try:
        async with http_session.delete(url, headers=headers) as response:
            if response.status == 405:
                logger.debug("Server does not support session termination (405)")
            elif response.status >= 400:
                logger.warning("Session termination failed: HTTP %s", response.status)
    except Exception:
        logger.warning("Session termination failed", exc_info=True)
