"""Ping MCP server -- validates MCP connection health.

Implements REFS-02: responds to the MCP protocol ping method, validating
container liveness and MCP transport connectivity. The MCP ping is a
protocol-level request handled automatically by the underlying mcp SDK --
no application tool code is required.

Transport: MCP Streamable HTTP on port 8000 (internal Docker network only).
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP("ping")

# No @mcp.tool definitions needed.
# The MCP protocol ping (session.send_ping()) is handled at the SDK/transport
# layer automatically. Any FastMCP server responds to ping -- no app code needed.

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
