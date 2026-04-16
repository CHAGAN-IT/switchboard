"""Echo MCP server -- returns input unchanged.

Implements REFS-01: an MCP tool that echoes its input argument back to the
caller without modification. Used as a test target for end-to-end gateway
routing validation.

Transport: MCP Streamable HTTP on port 8000 (internal Docker network only).
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("echo")


@mcp.tool
def echo(message: str) -> str:
    """Return the input message unchanged.

    Args:
        message: The string to echo back.

    Returns:
        The input message, unchanged.

    Example:
        >>> echo("hello world")
        'hello world'
    """
    return message


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
