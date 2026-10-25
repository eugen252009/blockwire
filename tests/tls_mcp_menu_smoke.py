#!/usr/bin/env python3
"""Read/navigate an explicitly configured isolated graphical instance over TLS + MCP.
No world creation/loading or destructive actions. Requires the MCP optional extra.
"""
import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    report = {}
    params = StdioServerParameters(command=str(ROOT / ".venv/bin/blockwire-mcp"), env=dict(os.environ))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 24

            async def call(name, **arguments):
                result = await session.call_tool(name, arguments)
                assert not result.isError, result
                data = result.structuredContent
                if data is None:
                    data = json.loads(next(c.text for c in result.content if c.type == "text"))
                report.setdefault("calls", []).append({"tool": name, "result": data})
                return data

            menu = await call("describe_menu")
            if menu.get("type") == "DisconnectedScreen":
                back = next(w for w in menu["widgets"] if w["label"] == "Back to Server List")
                await call("click_menu_widget", screen_id=menu["screen_id"], widget_id=back["widget_id"])
            for _ in range(5):
                menu = await call("describe_menu")
                if menu.get("type") == "TitleScreen":
                    break
                await call("press_menu_key", screen_id=menu["screen_id"], key="escape")
                await asyncio.sleep(.1)
            assert menu.get("type") == "TitleScreen"
            option = next(w for w in menu["widgets"] if w["label"] == "Options...")
            await call("click_menu_widget", screen_id=menu["screen_id"], widget_id=option["widget_id"])
            options = await call("describe_menu")
            assert options["type"] == "OptionsScreen"
            await call("press_menu_key", screen_id=options["screen_id"], key="escape")
            assert (await call("describe_menu"))["type"] == "TitleScreen"
    report["status"] = "PASS"
    (ROOT / "build/tls-verification/packaged-mcp-menu.json").write_text(json.dumps(report, indent=2)+"\n")
    print("PACKAGED_TLS_MCP_MENU_PASS")


if __name__ == "__main__":
    asyncio.run(main())
