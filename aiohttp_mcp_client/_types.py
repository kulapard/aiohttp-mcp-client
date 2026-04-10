"""MCP client types — exceptions and result dataclasses.

All types are pure stdlib (dataclasses + typing). No external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------
LATEST_PROTOCOL_VERSION: str = "2025-11-25"
MCP_SESSION_ID_HEADER: str = "mcp-session-id"
MCP_PROTOCOL_VERSION_HEADER: str = "mcp-protocol-version"
CONTENT_TYPE_JSON: str = "application/json"
CONTENT_TYPE_SSE: str = "text/event-stream"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MCPError(Exception):
    """Base exception for all MCP client errors."""


class MCPTransportError(MCPError):
    """HTTP or network-level transport failure."""


class MCPServerError(MCPError):
    """JSON-RPC error response from the server.

    Attributes:
        code: JSON-RPC error code.
        message: Human-readable error message.
        data: Optional additional error data.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


# ---------------------------------------------------------------------------
# Content types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextContent:
    """Text content block."""

    text: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class ImageContent:
    """Image content block (base64-encoded)."""

    data: str
    mime_type: str
    type: Literal["image"] = "image"


@dataclass(frozen=True)
class AudioContent:
    """Audio content block (base64-encoded)."""

    data: str
    mime_type: str
    type: Literal["audio"] = "audio"


ContentBlock: TypeAlias = TextContent | ImageContent | AudioContent


# ---------------------------------------------------------------------------
# Tool types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    """MCP tool definition."""

    name: str
    description: str | None
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool call."""

    content: list[ContentBlock]
    is_error: bool = False


# ---------------------------------------------------------------------------
# Resource types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Resource:
    """MCP resource definition."""

    name: str
    uri: str
    description: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True)
class ResourceTemplate:
    """MCP resource template definition."""

    name: str
    uri_template: str
    description: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True)
class ResourceContents:
    """Contents of a resource read."""

    uri: str
    mime_type: str | None = None
    text: str | None = None
    blob: str | None = None


# ---------------------------------------------------------------------------
# Prompt types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromptArgument:
    """Argument definition for a prompt."""

    name: str
    description: str | None = None
    required: bool = False


@dataclass(frozen=True)
class Prompt:
    """MCP prompt definition."""

    name: str
    description: str | None = None
    arguments: list[PromptArgument] = field(default_factory=list)


@dataclass(frozen=True)
class PromptMessage:
    """A message within a prompt result."""

    role: str
    content: ContentBlock


@dataclass(frozen=True)
class GetPromptResult:
    """Result of a prompt/get call."""

    messages: list[PromptMessage]
    description: str | None = None


# ---------------------------------------------------------------------------
# Server info
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServerCapabilities:
    """Capabilities advertised by the server."""

    tools: bool = False
    resources: bool = False
    prompts: bool = False


@dataclass(frozen=True)
class ServerInfo:
    """Information about the connected MCP server."""

    name: str
    version: str
    protocol_version: str
    capabilities: ServerCapabilities
    instructions: str | None = None
