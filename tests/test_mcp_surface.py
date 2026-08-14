"""Assert the full MCP surface the server advertises: tools, prompts, resources.

This is the regression guard for dependency breaks. v0.1.0 declared an uncapped
`mcp>=1.2.0`; when mcp 2.0.0 removed `mcp.server.fastmcp`, every clean install
died at import and the server advertised nothing at all. A boot test that only
checks tool names would still have caught that, but this test also pins the
prompt and resource surface so a partial regression cannot pass silently.

Runs with no API key and makes no network calls.
"""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = [
    "council_config",
    "council_deliberate",
    "council_deliberate_streaming",
    "council_jury",
]
EXPECTED_PROMPTS = ["compare_options", "deliberate", "jury"]
EXPECTED_RESOURCES = ["council://methodology", "council://roster"]


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "llm_council_mcp.server"],
        # Deliberately no OPENROUTER_API_KEY: the server must start and be
        # introspectable without credentials, or registry scanners that install
        # and probe it (LobeHub, MCP directories) will mark it broken.
        env={"PYTHONPATH": "."},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = sorted(t.name for t in (await session.list_tools()).tools)
            assert tools == EXPECTED_TOOLS, f"tools: {tools}"

            prompts = sorted(p.name for p in (await session.list_prompts()).prompts)
            assert prompts == EXPECTED_PROMPTS, f"prompts: {prompts}"

            resources = sorted(str(r.uri) for r in (await session.list_resources()).resources)
            assert resources == EXPECTED_RESOURCES, f"resources: {resources}"

            # Every advertised item must actually be readable/renderable.
            for uri in EXPECTED_RESOURCES:
                body = (await session.read_resource(uri)).contents[0].text
                assert body.strip(), f"empty resource: {uri}"

            for name, args in (
                ("deliberate", {"question": "Ship v0.2 today?"}),
                ("jury", {"question": "Ship v0.2 today?"}),
                ("compare_options", {"options": "SQLite, Redis"}),
            ):
                msgs = (await session.get_prompt(name, args)).messages
                assert msgs and msgs[0].content.text.strip(), f"empty prompt: {name}"

            # council_config needs no API call — exercise a real tool round-trip.
            res = await session.call_tool("council_config", {})
            assert "council_models" in res.content[0].text

    print(f"tools     : {tools}")
    print(f"prompts   : {prompts}")
    print(f"resources : {resources}")
    print("\nPASS: full MCP surface advertised and callable without an API key")


if __name__ == "__main__":
    asyncio.run(main())
