"""Simple MCP client example.

Start the server first:
    uv run examples/server.py

Then run this client:
    uv run examples/client.py
"""

import asyncio

from aiohttp_mcp_client import LogMessage, MCPClient, Progress, TextContent


async def main() -> None:
    url = "http://localhost:8080/mcp"

    # --- Notification callbacks ---
    async def on_log(msg: LogMessage) -> None:
        print(f"    LOG [{msg.level}] {msg.data}")

    async def on_progress(msg: Progress) -> None:
        bar = ""
        if msg.total and msg.total > 0:
            pct = int(msg.progress / msg.total * 100)
            filled = pct // 5
            bar = f" [{'#' * filled}{'.' * (20 - filled)}] {pct}%"
        print(f"    PROGRESS{bar} {msg.message or ''}")

    async with MCPClient(url, on_log=on_log, on_progress=on_progress) as client:
        info = client.server_info
        print(f"Connected to {info.name} v{info.version}" if info else "Connected")
        print()

        # List tools
        tools = await client.list_tools()
        print(f"Available tools: {', '.join(t.name for t in tools)}")
        print()

        # Simple tool call
        print("--- calculate('2 ** 10 + 1') ---")
        result = await client.call_tool("calculate", {"expression": "2 ** 10 + 1"})
        assert isinstance(result.content[0], TextContent)
        print(f"  Result: {result.content[0].text}")
        print()

        # Tool call with progress and log notifications
        print("--- process_data(items=6) ---")
        result = await client.call_tool("process_data", {"items": 6})
        assert isinstance(result.content[0], TextContent)
        print(f"  Result: {result.content[0].text}")
        print()

        # Resources
        resources = await client.list_resources()
        if resources:
            contents = await client.read_resource(resources[0].uri)
            print(f"Resource '{resources[0].name}': {contents[0].text}")
            print()

        # Prompts
        prompts = await client.list_prompts()
        if prompts:
            prompt_result = await client.get_prompt("summarize", {"text": "Hello world"})
            assert isinstance(prompt_result.messages[0].content, TextContent)
            print(f"Prompt '{prompts[0].name}': {prompt_result.messages[0].content.text[:80]}...")
            print()

        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
