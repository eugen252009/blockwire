#!/usr/bin/env python3
"""Live skill jobs on an explicitly prepared flat, peaceful test world. No world/item seeding."""
import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def main():
    report = {}
    parameters = StdioServerParameters(command=str(ROOT / ".venv/bin/blockwire-mcp"), env=dict(os.environ))
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 24

            async def call(name, error=None, **arguments):
                reply = await session.call_tool(name, arguments)
                if error:
                    assert reply.isError and error in str(reply), reply
                    return {"expected_error": error}
                assert not reply.isError, reply
                result = reply.structuredContent
                if result is None:
                    result = json.loads(next(c.text for c in reply.content if c.type == "text"))
                report.setdefault("calls", []).append({"tool": name, "result": result})
                return result

            descriptors = await call("list_skills")
            if isinstance(descriptors, dict):
                descriptors = descriptors["result"]
            assert any(item["name"] == "walk_to" for item in descriptors)
            before = await call("describe_surroundings")
            x, y, z = before["position"]
            started = await call("walk_to", x=x+2, y=y, z=z, avoid_damage=True, timeout_seconds=20.)
            for _ in range(200):
                status = await call("skill_status", job_id=started["id"])
                if status["status"] != "running":
                    break
                await asyncio.sleep(.05)
            assert status["status"] == "succeeded"
            assert status["result"]["cleanup"] == "released"
            current = await call("describe_surroundings")
            x, y, z = current["position"]
            long_job = await call("walk_to", x=x+30, y=y, z=z, timeout_seconds=30.)
            await call("look", error="skill owns player control", yaw=0., pitch=0.)
            # Read observations and status while the worker owns movement.
            await call("describe_surroundings")
            await asyncio.sleep(.2)
            await call("cancel_skill", job_id=long_job["id"])
            for _ in range(100):
                status = await call("skill_status", job_id=long_job["id"])
                if status["status"] != "running":
                    break
                await asyncio.sleep(.02)
            assert status["status"] == "cancelled", status
            assert status["result"]["cleanup"] == "released"
            await asyncio.sleep(.5)
            stopped_a = await call("describe_surroundings")
            await asyncio.sleep(.3)
            stopped_b = await call("describe_surroundings")
            assert sum((a-b)**2 for a, b in zip(stopped_a["position"], stopped_b["position"])) < .0025
    report["status"] = "PASS"
    (ROOT / "build/skills-verification/mcp-skills-live.json").write_text(json.dumps(report, indent=2)+"\n")
    print("MCP_SKILL_ARRIVAL_CANCELLATION_AND_EXCLUSION_PASS")


if __name__ == "__main__":
    asyncio.run(main())
