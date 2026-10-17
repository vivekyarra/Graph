"""Real MCP stdio client for bounded graph tools; failure stops investigation."""
import asyncio
import json
import os
import sys


async def _invoke(name, arguments):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "maelin.mcp_server"],
                                   env=dict(os.environ))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            reply = await session.call_tool(name, arguments)
            if reply.isError:
                raise RuntimeError("MCP graph tool failed: " + name)
            data = getattr(reply, "structuredContent", None)
            if data is None:
                texts = [block.text for block in reply.content if hasattr(block, "text")]
                if len(texts) != 1:
                    raise RuntimeError("MCP tool returned an unexpected result")
                data = json.loads(texts[0])
            if isinstance(data, dict) and set(data) == {"result"}:
                data = data["result"]
            if not isinstance(data, dict):
                raise RuntimeError("MCP tool must return a structured object")
            return data


def call_tool(name, arguments):
    return asyncio.run(_invoke(name, arguments))
