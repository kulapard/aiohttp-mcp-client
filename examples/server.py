"""Simple MCP server with a few demo tools.

Run:
    uv run examples/server.py

Then configure in Claude Desktop (claude_desktop_config.json):

    {
      "mcpServers": {
        "demo": {
          "url": "http://localhost:8080/mcp"
        }
      }
    }
"""

import ast
import datetime
import operator
import platform
import sys

from aiohttp import web
from aiohttp_mcp import AiohttpMCP, Context, build_mcp_app

# Workaround: aiohttp 3.13.x + Python 3.14 + macOS raises OSError
# in tcp_keepalive due to TransportSocket wrapper incompatibility.
# Patch the reference in web_protocol (where it's actually called).
if sys.version_info >= (3, 14):
    from aiohttp import web_protocol as _wp

    _orig_keepalive = _wp.tcp_keepalive

    def _safe_keepalive(transport: object) -> None:
        try:
            _orig_keepalive(transport)  # type: ignore[arg-type]
        except OSError:
            pass

    _wp.tcp_keepalive = _safe_keepalive  # type: ignore[assignment]

mcp = AiohttpMCP(name="demo-server")


@mcp.tool()
async def get_time() -> str:
    """Get the current date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
async def get_system_info() -> str:
    """Get basic system information."""
    return (
        f"System: {platform.system()} {platform.release()}\n"
        f"Machine: {platform.machine()}\n"
        f"Python: {platform.python_version()}\n"
        f"Node: {platform.node()}"
    )


# Safe math operators for calculate tool
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node with only arithmetic operations."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


@mcp.tool()
async def calculate(expression: str, ctx: Context) -> str:
    """Evaluate a math expression safely.

    Only supports basic arithmetic: +, -, *, /, **, (, ).
    """
    await ctx.info(f"Evaluating: {expression}")
    tree = ast.parse(expression, mode="eval")
    result = _safe_eval(tree)
    return str(result)


@mcp.tool()
async def process_data(items: int, ctx: Context) -> str:
    """Process N items with progress and log notifications.

    Demonstrates server notifications during a long-running tool call.
    """
    import asyncio as _asyncio

    await ctx.info(f"Starting to process {items} items...")

    for i in range(1, items + 1):
        await _asyncio.sleep(0.3)  # simulate work
        await ctx.report_progress(float(i), float(items), message=f"Processing item {i}")
        if i == items // 2:
            await ctx.warning(f"Halfway there — {i}/{items} items processed")

    await ctx.info(f"Done! Processed {items} items.")
    return f"Successfully processed {items} items"


@mcp.resource("info://server")
async def server_info() -> str:
    """Information about this demo server."""
    return "Demo MCP server for aiohttp-mcp-client examples."


@mcp.prompt()
async def summarize(text: str) -> str:
    """Create a prompt to summarize text."""
    return f"Please summarize the following text concisely:\n\n{text}"


app = build_mcp_app(mcp, path="/mcp")


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    # Quiet down noisy loggers
    logging.getLogger("aiohttp").setLevel(logging.WARNING)

    print("Starting MCP server on http://localhost:8080/mcp")
    web.run_app(app, host="localhost", port=8080)
