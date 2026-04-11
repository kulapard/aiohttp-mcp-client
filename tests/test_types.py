"""Tests for _types module — exceptions and dataclasses."""

from aiohttp_mcp_client import (
    AudioContent,
    GetPromptResult,
    ImageContent,
    MCPError,
    MCPServerError,
    MCPTransportError,
    PaginatedResult,
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


class TestExceptions:
    def test_mcp_error_hierarchy(self) -> None:
        assert issubclass(MCPTransportError, MCPError)
        assert issubclass(MCPServerError, MCPError)

    def test_mcp_server_error_attributes(self) -> None:
        err = MCPServerError(code=-32601, message="Method not found", data={"detail": "foo"})
        assert err.code == -32601
        assert err.message == "Method not found"
        assert err.data == {"detail": "foo"}
        assert "[-32601]" in str(err)
        assert "Method not found" in str(err)

    def test_mcp_server_error_no_data(self) -> None:
        err = MCPServerError(code=-32600, message="Bad request")
        assert err.data is None

    def test_mcp_transport_error(self) -> None:
        err = MCPTransportError("HTTP 404")
        assert str(err) == "HTTP 404"


class TestDataclasses:
    def test_tool_frozen(self) -> None:
        tool = Tool(name="test", description="desc", input_schema={"type": "object"})
        assert tool.name == "test"
        assert tool.description == "desc"
        assert tool.input_schema == {"type": "object"}

    def test_tool_result(self) -> None:
        result = ToolResult(
            content=[TextContent(text="hello")],
            is_error=False,
        )
        assert len(result.content) == 1
        assert not result.is_error

    def test_text_content(self) -> None:
        tc = TextContent(text="hello")
        assert tc.type == "text"
        assert tc.text == "hello"

    def test_image_content(self) -> None:
        ic = ImageContent(data="base64data", mime_type="image/png")
        assert ic.type == "image"

    def test_audio_content(self) -> None:
        ac = AudioContent(data="base64data", mime_type="audio/wav")
        assert ac.type == "audio"

    def test_resource(self) -> None:
        r = Resource(name="test", uri="file:///test")
        assert r.name == "test"
        assert r.description is None
        assert r.mime_type is None

    def test_resource_template(self) -> None:
        rt = ResourceTemplate(name="test", uri_template="file:///{path}")
        assert rt.uri_template == "file:///{path}"

    def test_resource_contents(self) -> None:
        rc = ResourceContents(uri="file:///test", text="content")
        assert rc.text == "content"
        assert rc.blob is None

    def test_prompt(self) -> None:
        p = Prompt(
            name="test",
            description="desc",
            arguments=[PromptArgument(name="arg1", required=True)],
        )
        assert len(p.arguments) == 1
        assert p.arguments[0].required is True

    def test_prompt_message(self) -> None:
        pm = PromptMessage(role="user", content=TextContent(text="hi"))
        assert pm.role == "user"

    def test_get_prompt_result(self) -> None:
        gpr = GetPromptResult(
            messages=[PromptMessage(role="user", content=TextContent(text="hi"))],
            description="test prompt",
        )
        assert gpr.description == "test prompt"
        assert len(gpr.messages) == 1

    def test_server_info(self) -> None:
        si = ServerInfo(
            name="test-server",
            version="1.0.0",
            protocol_version="2025-11-25",
            capabilities=ServerCapabilities(tools=True, resources=True, prompts=False),
            instructions="Use wisely",
        )
        assert si.capabilities.tools is True
        assert si.capabilities.prompts is False
        assert si.instructions == "Use wisely"


class TestPaginatedResult:
    def test_acts_as_list(self) -> None:
        r: PaginatedResult[int] = PaginatedResult([1, 2, 3])
        assert len(r) == 3
        assert list(r) == [1, 2, 3]
        assert r[0] == 1

    def test_next_cursor_none_by_default(self) -> None:
        r: PaginatedResult[str] = PaginatedResult(["a", "b"])
        assert r.next_cursor is None

    def test_next_cursor_set(self) -> None:
        r: PaginatedResult[str] = PaginatedResult(["a"], next_cursor="cursor123")
        assert r.next_cursor == "cursor123"

    def test_iterable(self) -> None:
        r: PaginatedResult[int] = PaginatedResult([10, 20])
        collected = list(r)
        assert collected == [10, 20]

    def test_bool_empty(self) -> None:
        r: PaginatedResult[int] = PaginatedResult([])
        assert not r

    def test_bool_nonempty(self) -> None:
        r: PaginatedResult[int] = PaginatedResult([1])
        assert r
