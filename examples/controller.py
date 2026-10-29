"""Explicit one-batch walking/eating demo. Requires SDK a7 + alpha.4 mod.
Run only in an authorized, supervised flat-ground fixture. See docs/controller.md.
"""
import argparse
import asyncio
from dataclasses import asdict
import json
import sys

from blockwire import run_controller

options = None
outcomes = []


async def setup(bot):
    bot.on("health_changed", lambda bot, event: print("Health change (cause unknown):", event.data))
    bot.on("death", lambda bot, event: print("Death observed; no automatic respawn.", event.data))


async def loop(bot):
    async with asyncio.TaskGroup() as tasks:
        walk = tasks.create_task(bot.walk_to(*options.target))
        eat = tasks.create_task(bot.eat(hotbar_slot=options.food_slot))
    outcomes.extend([walk.result(), eat.result()])
    for result in outcomes:
        print(json.dumps(result))
    bot.stop()  # This demo runs ONE batch, not endless movement/food retries.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs=3, type=float, metavar="COORD", help="Target X Y Z on known flat ground")
    parser.add_argument("--food-slot", required=True, type=int, choices=range(9), help="Hotbar index 0–8, ordinary supported food")
    parser.add_argument("--duration", default=30., type=float)
    options = parser.parse_args()
    result = asyncio.run(run_controller(sys.modules[__name__], duration_seconds=options.duration))
    print(json.dumps(asdict(result)))
    raise SystemExit(0 if result.status == "stopped" and outcomes and
                     all(goal["status"] == "succeeded" for goal in outcomes) else 2)
