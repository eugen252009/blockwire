#!/usr/bin/env python3
"""Packaged rename compatibility in the existing owned superflat fixture only."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/rename-verification"


async def main():
    report = {}
    args = StdioServerParameters(command=str(ROOT / ".venv/bin/blockwire-mcp"), env=dict(os.environ))
    async with stdio_client(args) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.name == "Blockwire"
            assert len((await session.list_tools()).tools) == 24

            async def call(name, **arguments):
                response = await session.call_tool(name, arguments)
                assert not response.isError, response
                data = response.structuredContent
                if data is None:
                    data = json.loads(next(item.text for item in response.content if item.type == "text"))
                report.setdefault("calls", []).append({"tool": name, "result": data})
                return data

            async def menu():
                return await call("describe_menu")

            async def click(snapshot, label):
                widget = next(w for w in snapshot["widgets"] if w["label"] == label)
                await call("click_menu_widget", screen_id=snapshot["screen_id"], widget_id=widget["widget_id"])
                await asyncio.sleep(.15)

            current = await menu()
            if current.get("type") == "DisconnectedScreen":
                await click(current, "Back to Server List")
            for _ in range(5):
                current = await menu()
                if current.get("type") == "TitleScreen":
                    break
                await call("press_menu_key", screen_id=current["screen_id"], key="escape")
            assert current.get("type") == "TitleScreen"
            await click(current, "Singleplayer")
            current = await menu()
            world = next(w for w in current["widgets"] if "Bridge Skill Flat" in w["label"])
            await call("click_menu_widget", screen_id=current["screen_id"], widget_id=world["widget_id"])
            await click(await menu(), "Play Selected World")
            for _ in range(100):
                await asyncio.sleep(.15)
                before = await call("describe_surroundings")
                if before.get("in_world") and before.get("on_ground") and not (await menu())["screen_open"]:
                    break
            assert before.get("in_world") and before["alive"]
            x, y, z = before["position"]
            job = await call("walk_to", x=x+2, y=y, z=z, timeout_seconds=15.)
            for _ in range(150):
                status = await call("skill_status", job_id=job["id"])
                if status["status"] != "running":
                    break
                await asyncio.sleep(.1)
            assert status["status"] == "succeeded", status
            assert status["result"]["cleanup"] == "released"
            pause = await call("open_pause_menu")
            quit_world = next(w for w in pause["widgets"] if "Save and Quit" in w["label"])
            await call("click_menu_widget", screen_id=pause["screen_id"], widget_id=quit_world["widget_id"])
            for _ in range(100):
                await asyncio.sleep(.1)
                current = await menu()
                if current.get("type") == "TitleScreen":
                    break
            assert current.get("type") == "TitleScreen"
    report["status"] = "PASS"
    report["server_name"] = "Blockwire"
    report["legacy_environment_used"] = bool(os.environ.get("BLOCK_BRIDGE_CONFIG") and not os.environ.get("BLOCKWIRE_CONFIG"))
    (OUT / "packaged-live.json").write_text(json.dumps(report, indent=2)+"\n")
    print("BLOCKWIRE_PACKAGED_RENAME_WALK_PASS")


if __name__ == "__main__":
    asyncio.run(main())
