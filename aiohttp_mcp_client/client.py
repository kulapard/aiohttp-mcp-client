"""MCPClient — high-level async MCP client for Streamable HTTP servers."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from . import _transport
from ._types import (
    LATEST_PROTOCOL_VERSION,
    AudioContent,
    ContentBlock,
    GetPromptResult,
    ImageContent,
    MCPError,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    ResourceContents,
    ResourceTemplate,
    ServerCapabilities,
    ServerInfo,
    TextContent,
    Tool,
    ToolResult,
)

logger = logging.getLogger(__name__)


class MCPClient:
    """Async MCP client for Streamable HTTP servers.

    Usage as a context manager (recommended)::

        async with MCPClient("http://localhost:8080/mcp") as client:
            tools = await client.list_tools()
            result = await client.call_tool("my_tool", {"arg": "value"})

    Or with explicit lifecycle management::

        client = MCPClient("http://localhost:8080/mcp")
        await client.open()
        try:
            tools = await client.list_tools()
        finally:
            await client.close()
    """

    def __init__(
        self,
        url: str,
        *,
        session: aiohttp.ClientSession | None = None,
        client_info: dict[str, str] | None = None,
    ) -> None:
        """Initialize the MCP client.

        Args:
            url: MCP server endpoint URL (e.g. ``http://localhost:8080/mcp``).
            session: Optional pre-existing aiohttp session. If not provided,
                one will be created and managed by the client.
            client_info: Optional dict with ``name`` and ``version`` keys
                identifying this client to the server.
        """
        self._url = url
        self._external_session = session
        self._session: aiohttp.ClientSession | None = None
        self._owns_session = session is None
        self._client_info = client_info or {
            "name": "aiohttp-mcp-client",
            "version": "0.1.0",
        }
        self._session_id: str | None = None
        self._protocol_version: str = LATEST_PROTOCOL_VERSION
        self._request_id: int = 0
        self._initialized = False
        self._server_info: ServerInfo | None = None

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise MCPError("Client is not open. Use 'async with MCPClient(...)' or call open() first.")
        return self._session

    @property
    def server_info(self) -> ServerInfo | None:
        """Server information from the initialize handshake. None if not yet initialized."""
        return self._server_info

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """Open the client: create HTTP session and initialize the MCP connection."""
        if self._external_session is not None:
            self._session = self._external_session
        else:
            self._session = aiohttp.ClientSession()
        await self._initialize()

    async def close(self) -> None:
        """Close the client: terminate MCP session and clean up HTTP session."""
        if self._session is not None and self._session_id is not None:
            await _transport.terminate_session(
                self._session,
                self._url,
                self._session_id,
                self._protocol_version,
            )
            self._session_id = None

        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

        self._initialized = False

    async def __aenter__(self) -> MCPClient:
        await self.open()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    async def _initialize(self) -> ServerInfo:
        """Perform the MCP initialize handshake."""
        session = self._get_session()

        result, new_session_id = await _transport.send_request(
            http_session=session,
            url=self._url,
            method="initialize",
            params={
                "protocolVersion": self._protocol_version,
                "capabilities": {},
                "clientInfo": self._client_info,
            },
            request_id=self._next_id(),
            session_id=None,  # No session ID on initialize
            protocol_version=self._protocol_version,
        )

        if new_session_id:
            self._session_id = new_session_id

        # Extract negotiated version
        negotiated = result.get("protocolVersion", self._protocol_version)
        self._protocol_version = negotiated

        server_info = _parse_server_info(result)
        self._server_info = server_info
        self._initialized = True

        # Send initialized notification
        await _transport.send_notification(
            http_session=session,
            url=self._url,
            method="notifications/initialized",
            params=None,
            session_id=self._session_id,
            protocol_version=self._protocol_version,
        )

        return server_info

    async def ping(self) -> None:
        """Send a ping to the server."""
        await self._send("ping", None)

    async def list_tools(self) -> list[Tool]:
        """List available tools on the server."""
        result = await self._send("tools/list", None)
        return [_parse_tool(t) for t in result.get("tools", [])]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Call a tool on the server.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            ToolResult with content blocks and is_error flag.
        """
        result = await self._send("tools/call", {"name": name, "arguments": arguments or {}})
        content = [_parse_content_block(c) for c in result.get("content", [])]
        return ToolResult(content=content, is_error=result.get("isError", False))

    async def list_resources(self) -> list[Resource]:
        """List available resources on the server."""
        result = await self._send("resources/list", None)
        return [_parse_resource(r) for r in result.get("resources", [])]

    async def read_resource(self, uri: str) -> list[ResourceContents]:
        """Read a resource by URI.

        Args:
            uri: Resource URI.
        """
        result = await self._send("resources/read", {"uri": uri})
        return [_parse_resource_contents(c) for c in result.get("contents", [])]

    async def list_resource_templates(self) -> list[ResourceTemplate]:
        """List available resource templates on the server."""
        result = await self._send("resources/templates/list", None)
        return [_parse_resource_template(t) for t in result.get("resourceTemplates", [])]

    async def list_prompts(self) -> list[Prompt]:
        """List available prompts on the server."""
        result = await self._send("prompts/list", None)
        return [_parse_prompt(p) for p in result.get("prompts", [])]

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None = None,
    ) -> GetPromptResult:
        """Get a prompt by name.

        Args:
            name: Prompt name.
            arguments: Optional prompt arguments.
        """
        params: dict[str, Any] = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        result = await self._send("prompts/get", params)
        return _parse_get_prompt_result(result)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        """Send a JSON-RPC request and return the result dict."""
        if not self._initialized:
            raise MCPError("Client is not initialized. Use 'async with MCPClient(...)' or call open() first.")

        session = self._get_session()
        result, new_session_id = await _transport.send_request(
            http_session=session,
            url=self._url,
            method=method,
            params=params,
            request_id=self._next_id(),
            session_id=self._session_id,
            protocol_version=self._protocol_version,
        )
        if new_session_id:
            self._session_id = new_session_id
        return result


# ------------------------------------------------------------------
# Response parsers (module-level, stateless)
# ------------------------------------------------------------------


def _parse_server_info(result: dict[str, Any]) -> ServerInfo:
    si = result.get("serverInfo", {})
    caps_raw = result.get("capabilities", {})
    capabilities = ServerCapabilities(
        tools=caps_raw.get("tools") is not None,
        resources=caps_raw.get("resources") is not None,
        prompts=caps_raw.get("prompts") is not None,
    )
    return ServerInfo(
        name=si.get("name", "unknown"),
        version=si.get("version", "unknown"),
        protocol_version=result.get("protocolVersion", LATEST_PROTOCOL_VERSION),
        capabilities=capabilities,
        instructions=result.get("instructions"),
    )


def _parse_tool(raw: dict[str, Any]) -> Tool:
    return Tool(
        name=raw["name"],
        description=raw.get("description"),
        input_schema=raw.get("inputSchema", {}),
    )


def _parse_content_block(raw: dict[str, Any]) -> ContentBlock:
    block_type = raw.get("type", "text")
    if block_type == "text":
        return TextContent(text=raw.get("text", ""))
    if block_type == "image":
        return ImageContent(data=raw.get("data", ""), mime_type=raw.get("mimeType", ""))
    if block_type == "audio":
        return AudioContent(data=raw.get("data", ""), mime_type=raw.get("mimeType", ""))
    # Fallback: treat unknown types as text with JSON representation
    import json  # noqa: PLC0415

    return TextContent(text=json.dumps(raw))


def _parse_resource(raw: dict[str, Any]) -> Resource:
    return Resource(
        name=raw["name"],
        uri=str(raw["uri"]),
        description=raw.get("description"),
        mime_type=raw.get("mimeType"),
    )


def _parse_resource_template(raw: dict[str, Any]) -> ResourceTemplate:
    return ResourceTemplate(
        name=raw["name"],
        uri_template=raw["uriTemplate"],
        description=raw.get("description"),
        mime_type=raw.get("mimeType"),
    )


def _parse_resource_contents(raw: dict[str, Any]) -> ResourceContents:
    return ResourceContents(
        uri=str(raw["uri"]),
        mime_type=raw.get("mimeType"),
        text=raw.get("text"),
        blob=raw.get("blob"),
    )


def _parse_prompt(raw: dict[str, Any]) -> Prompt:
    arguments = [
        PromptArgument(
            name=a["name"],
            description=a.get("description"),
            required=a.get("required", False),
        )
        for a in raw.get("arguments", [])
    ]
    return Prompt(
        name=raw["name"],
        description=raw.get("description"),
        arguments=arguments,
    )


def _parse_prompt_message(raw: dict[str, Any]) -> PromptMessage:
    return PromptMessage(
        role=raw["role"],
        content=_parse_content_block(raw.get("content", {})),
    )


def _parse_get_prompt_result(result: dict[str, Any]) -> GetPromptResult:
    messages = [_parse_prompt_message(m) for m in result.get("messages", [])]
    return GetPromptResult(
        description=result.get("description"),
        messages=messages,
    )
