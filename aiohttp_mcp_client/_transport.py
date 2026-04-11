"""Low-level HTTP transport for MCP Streamable HTTP protocol.

Handles POST with JSON/SSE response parsing, GET SSE streaming,
session header management, and session termination via DELETE.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import aiohttp

from ._types import (
    CONTENT_TYPE_JSON,
    CONTENT_TYPE_SSE,
    LAST_EVENT_ID_HEADER,
    LATEST_PROTOCOL_VERSION,
    MCP_PROTOCOL_VERSION_HEADER,
    MCP_SESSION_ID_HEADER,
    MCPServerError,
    MCPTransportError,
)

logger = logging.getLogger(__name__)

# Reconnection defaults for GET SSE stream
DEFAULT_RECONNECTION_DELAY: float = 1.0  # seconds
MAX_RECONNECTION_ATTEMPTS: int = 2


@dataclass
class SSEEvent:
    """A parsed SSE event with data and optional event ID."""

    data: dict[str, Any]
    event_id: str | None = None


def _parse_sse_data(data_lines: list[str]) -> dict[str, Any]:
    """Parse accumulated SSE data lines as JSON."""
    raw = "\n".join(data_lines)
    try:
        result: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPTransportError(f"Invalid JSON in SSE data: {raw!r}") from exc
    return result


async def _iter_sse_events(response: aiohttp.ClientResponse) -> AsyncGenerator[SSEEvent, None]:
    """Parse SSE stream from an aiohttp response, yielding parsed events.

    Only yields events with ``event: message`` and non-empty ``data:``.
    Tracks ``id:`` fields for resumability.
    Raises MCPTransportError on JSON parse failure.
    """
    event_type: str | None = None
    event_id: str | None = None
    data_lines: list[str] = []

    async for raw_line in response.content:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.startswith("id:"):
            event_id = line[3:].strip()
        elif line == "":
            # Blank line = end of event
            if event_type == "message" and data_lines:
                yield SSEEvent(data=_parse_sse_data(data_lines), event_id=event_id)
            event_type = None
            event_id = None
            data_lines = []

    # Flush any remaining event (stream closed without trailing blank line)
    if event_type == "message" and data_lines:
        yield SSEEvent(data=_parse_sse_data(data_lines), event_id=event_id)


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
    on_notification: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Send a JSON-RPC request and return (result_dict, session_id_from_response).

    Handles both ``application/json`` and ``text/event-stream`` responses.
    For SSE responses, notifications are routed to ``on_notification`` if
    provided, otherwise silently consumed. Only the final response is returned.

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
            # SSE stream: route notifications, return final response
            async for event in _iter_sse_events(response):
                msg = event.data
                if "result" in msg or "error" in msg:
                    return _extract_result(msg), new_session_id
                # Notification — route to callback or discard
                if on_notification is not None:
                    await on_notification(msg)
                else:
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


async def _consume_sse_stream(
    http_session: aiohttp.ClientSession,
    url: str,
    headers: dict[str, str],
    on_notification: Callable[[dict[str, Any]], Awaitable[None]] | None,
) -> str | None:
    """Open a single GET SSE connection, consume events, return the last event ID.

    Returns:
        The last event ID seen, or None.

    Raises:
        MCPTransportError: On HTTP errors that should not be retried.
    """
    async with http_session.get(url, headers=headers) as response:
        if response.status == 409:
            raise MCPTransportError("GET SSE stream conflict (409) — another stream already open")
        if response.status >= 400:
            raise MCPTransportError(f"GET SSE stream failed: HTTP {response.status}")

        logger.debug("GET SSE stream connected")
        last_event_id: str | None = None

        async for event in _iter_sse_events(response):
            if event.event_id:
                last_event_id = event.event_id
            msg = event.data
            if on_notification is not None:
                await on_notification(msg)
            else:
                logger.debug("GET SSE notification (discarded): %s", msg.get("method", "unknown"))

        return last_event_id


async def listen_sse(
    http_session: aiohttp.ClientSession,
    url: str,
    session_id: str,
    protocol_version: str = LATEST_PROTOCOL_VERSION,
    on_notification: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> None:
    """Open a persistent GET SSE stream for server-initiated notifications.

    Runs until the connection is closed or cancelled. Automatically reconnects
    on disconnection up to ``MAX_RECONNECTION_ATTEMPTS`` times.
    """
    last_event_id: str | None = None
    attempt = 0

    while attempt < MAX_RECONNECTION_ATTEMPTS:
        headers: dict[str, str] = {
            "Accept": CONTENT_TYPE_SSE,
            MCP_SESSION_ID_HEADER: session_id,
            MCP_PROTOCOL_VERSION_HEADER: protocol_version,
        }
        if last_event_id:
            headers[LAST_EVENT_ID_HEADER] = last_event_id

        try:
            new_last_id = await _consume_sse_stream(http_session, url, headers, on_notification)
            if new_last_id:
                last_event_id = new_last_id
            # Stream ended normally — reset attempt counter
            attempt = 0
        except asyncio.CancelledError:
            logger.debug("GET SSE stream cancelled")
            return
        except MCPTransportError:
            # Non-retryable HTTP errors (409, 4xx)
            return
        except Exception:
            logger.debug("GET SSE stream error", exc_info=True)
            attempt += 1

        if attempt >= MAX_RECONNECTION_ATTEMPTS:
            logger.debug("GET SSE stream max reconnection attempts (%s) exceeded", MAX_RECONNECTION_ATTEMPTS)
            return

        logger.info("GET SSE stream disconnected, reconnecting in %.1fs...", DEFAULT_RECONNECTION_DELAY)
        await asyncio.sleep(DEFAULT_RECONNECTION_DELAY)


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
