"""Simple MCP client example.

Start the server first:
    uv run examples/server.py

Then run this client:
    uv run examples/client.py
"""

import asyncio

from aiohttp_mcp_client import LogMessage, MCPClient, Progress


async def main() -> None:
    url = "http://localhost:8080/mcp"

    # Notification callbacks
    async def on_log(msg: LogMessage) -> None:
        print(f"  [{msg.level}] {msg.data}")

    async def on_progress(msg: Progress) -> None:
        pct = f"{msg.progress}/{msg.total}" if msg.total else f"{msg.progress}"
        print(f"  Progress: {pct}")

    async with MCPClient(url, on_log=on_log, on_progress=on_progress) as client:
        print(f"Connected to: {client.server_info}")
        print()

        # List tools
        tools = await client.list_tools()
        print(f"Tools ({len(tools)}):")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")
        print()

        # Call tools
        print("get_time:")
        result = await client.call_tool("get_time")
        print(f"  {result.content[0].text}")  # type: ignore[union-attr]
        print()

        print("get_system_info:")
        result = await client.call_tool("get_system_info")
        print(f"  {result.content[0].text}")  # type: ignore[union-attr]
        print()

        print("calculate('2 ** 10 + 1'):")
        result = await client.call_tool("calculate", {"expression": "2 ** 10 + 1"})
        print(f"  = {result.content[0].text}")  # type: ignore[union-attr]
        print()

        # List resources
        resources = await client.list_resources()
        print(f"Resources ({len(resources)}):")
        for r in resources:
            print(f"  - {r.uri}: {r.name}")

        if resources:
            contents = await client.read_resource(resources[0].uri)
            print(f"  Content: {contents[0].text}")
        print()

        # List prompts
        prompts = await client.list_prompts()
        print(f"Prompts ({len(prompts)}):")
        for p in prompts:
            print(f"  - {p.name}: {p.description}")

        if prompts:
            prompt_result = await client.get_prompt("summarize", {"text": "Hello world"})
            print(f"  Message: {prompt_result.messages[0].content}")
        print()

        # Ping
        await client.ping()
        print("Ping: OK")


if __name__ == "__main__":
    asyncio.run(main())
