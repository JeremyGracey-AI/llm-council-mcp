"""Boot the MCP server over stdio and confirm it lists the expected tools."""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=".venv/bin/python",
        args=["-m", "llm_council_mcp.server"],
        env={"OPENROUTER_API_KEY": "test-key-not-used", "PYTHONPATH": "."},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("Registered tools:", names)
            assert names == ["council_config", "council_deliberate", "council_jury"], names

            # council_config needs no API call — exercise a real round-trip.
            res = await session.call_tool("council_config", {})
            print("council_config output:\n", res.content[0].text)
            print("\nPASS: MCP server boots and tools are callable")


if __name__ == "__main__":
    asyncio.run(main())
