#!/usr/bin/env python3
"""Explicit live smoke: moves one already-acquired dirt stack through the native GUI.
Run only in an isolated test world with the bridge enabled. Does not spawn items.
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
            report["tools"] = [tool.name for tool in tools.tools]

            async def call(name, arguments=None):
                result = await session.call_tool(name, arguments or {})
                if result.isError:
                    raise AssertionError(result)
                data = result.structuredContent
                if data is None:
                    data = json.loads(next(c.text for c in result.content if c.type == "text"))
                report.setdefault("calls", []).append({"tool": name, "result": data})
                return data

            await call("describe_surroundings")
            inventory = await call("show_inventory")
            assert any(item["item"] == "minecraft:dirt" for item in inventory["items"])
            opened = await call("open_inventory")
            source = next(slot["slot"] for slot in opened["slots"] if slot.get("item") == "minecraft:dirt")
            destination = next(slot["slot"] for slot in opened["slots"] if slot["slot"] == 37 and slot["empty"])
            await call("click_inventory_slot", dict(menu_id=opened["menu_id"], state_id=opened["state_id"], slot=source))
            await asyncio.sleep(.2)
            carried = await call("show_inventory")
            assert carried["carried"]["item"] == "minecraft:dirt"
            await call("click_inventory_slot", dict(menu_id=carried["menu_id"], state_id=carried["state_id"], slot=destination))
            await asyncio.sleep(.2)
            moved = await call("show_inventory")
            assert moved["carried"]["empty"]
            assert any(item.get("item") == "minecraft:dirt" and item["inventory_index"] == 1 for item in moved["items"])
            await call("close_inventory")
            await call("stop_inputs")
    report["status"] = "PASS"
    (ROOT / "build/verification/mcp-live.json").write_text(json.dumps(report, indent=2) + "\n")
    print("MCP_STDIO_NATIVE_INVENTORY_PASS")


if __name__ == "__main__":
    asyncio.run(main())
