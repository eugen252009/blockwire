#!/usr/bin/env python3
"""Real MCP -> WebSocket -> native menus, in the isolated Blockwire dev instance.
Never run against an unrelated profile: joins only the existing 'Blockwire Smo' smoke-test world.
"""
import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    report = {"scope": "isolated native menu traversal over MCP stdio"}
    params = StdioServerParameters(command=str(ROOT / ".venv/bin/blockwire-mcp"), env=dict(os.environ))
    try:
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) == 24
                report["tools"] = [tool.name for tool in tools.tools]

                async def call(name, arguments=None, expected_error=None):
                    result = await session.call_tool(name, arguments or {})
                    if expected_error:
                        assert result.isError and expected_error in str(result), result
                        report.setdefault("checks", []).append(expected_error)
                        return None
                    assert not result.isError, result
                    data = result.structuredContent
                    if data is None:
                        data = json.loads(next(c.text for c in result.content if c.type == "text"))
                    report.setdefault("calls", []).append({"tool": name, "result": data})
                    return data

                async def menu():
                    return await call("describe_menu")

                async def click(snapshot, label):
                    widget = next(w for w in snapshot["widgets"] if w["label"] == label)
                    await call("click_menu_widget", dict(screen_id=snapshot["screen_id"], widget_id=widget["widget_id"]))
                    await asyncio.sleep(.15)

                initial = await menu()
                assert initial["type"] == "TitleScreen"
                await click(initial, "Options...")
                options = await menu()
                assert options["type"] != "TitleScreen"
                await call("click_menu_widget", dict(screen_id=initial["screen_id"], widget_id=0), "stale_screen")
                await call("press_menu_key", dict(screen_id=options["screen_id"], key="escape"))
                title = await menu()
                await click(title, "Singleplayer")
                selected = await menu()
                field = next(w for w in selected["widgets"] if "character_count" in w)
                await call("click_menu_widget", dict(screen_id=selected["screen_id"], widget_id=field["widget_id"]))
                focused = await menu()
                text = "No matching world 3827"
                await call("type_menu_text", dict(screen_id=focused["screen_id"], text=text, replace=True))
                filtered = await menu()
                assert any(w.get("character_count") == len(text) for w in filtered["widgets"])
                assert text not in str(filtered)  # Values are not echoed, even to the MCP host.
                assert not any("Blockwire Smo" in w["label"] for w in filtered["widgets"])
                await call("type_menu_text", dict(screen_id=filtered["screen_id"], text="", replace=True))
                restored = await menu()
                assert any(w.get("character_count") == 0 for w in restored["widgets"])
                entry = next(w for w in restored["widgets"] if "Blockwire Smo" in w["label"])
                await call("click_menu_widget", dict(screen_id=restored["screen_id"], widget_id=entry["widget_id"]))
                ready = await menu()
                play = next(w for w in ready["widgets"] if "Play Selected World" == w["label"])
                assert play["active"]
                await call("click_menu_widget", dict(screen_id=ready["screen_id"], widget_id=play["widget_id"]))
                for _ in range(100):
                    await asyncio.sleep(.25)
                    scene = await call("describe_surroundings")
                    if scene.get("in_world"):
                        break
                assert scene.get("in_world")
                # Wait for loading screens to finish, not merely the first client player object.
                for _ in range(100):
                    current = await menu()
                    scene = await call("describe_surroundings")
                    if scene.get("in_world") and not scene["alive"]:
                        await call("respawn")
                        await asyncio.sleep(.3)
                        continue
                    if not current["screen_open"]:
                        break
                    await asyncio.sleep(.1)
                assert not current["screen_open"]
                # This is a menu test, not an AFK Survival/combat test. A previously
                # saved death is handled through the ordinary native respawn request.
                scene = await call("describe_surroundings")
                if not scene["alive"]:
                    await call("respawn")
                    await asyncio.sleep(.3)
                pause = await call("open_pause_menu")
                assert pause["screen_open"]
                quit_button = next(w for w in pause["widgets"] if "Save and Quit" in w["label"])
                await call("click_menu_widget", dict(screen_id=pause["screen_id"], widget_id=quit_button["widget_id"]))
                for _ in range(100):
                    await asyncio.sleep(.2)
                    current = await menu()
                    if current.get("type") == "TitleScreen":
                        break
                assert current.get("type") == "TitleScreen"
        report["status"] = "PASS"
        print("MCP_NATIVE_MENU_STARTUP_TRAVERSAL_PASS")
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        raise
    finally:
        (ROOT / "build/verification/mcp-menu-live.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
