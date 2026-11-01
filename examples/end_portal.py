"""Minecraft completion campaign scaffold, NOT an autonomous playthrough bot.

Offline plan: python examples/end_portal.py --plan
Read-only preflight: python examples/end_portal.py --inspect
First implemented subgoal: python examples/end_portal.py --gather-wood 1
Explicit execution: python examples/end_portal.py --run --provider reviewed_survival

No survival provider ships with this example. The stock SDK reports BLOCKED,
without movement, mining, commands, world creation or automatic unpausing.
Installed providers execute trusted host Python, not sandboxed code.
The final goal is defeating the Ender Dragon and reaching the native credits,
without scripted game pauses. End-portal activation is only an intermediate goal.
Development attempts still pause on stop unless --no-pause is explicitly selected.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import threading
import time
from typing import Callable

from blockwire import Bridge, Player
from blockwire.statistics import capture_statistics, statistics_report
from blockwire.skills import default_registry, load_selected_plugins, run_skill


def counts(inventory):
    result = {}
    for item in inventory.get("items", []):
        identifier = item.get("item")
        if identifier and not item.get("empty", False):
            result[identifier] = result.get(identifier, 0) + item.get("count", 0)
    return result


def near_block(scene, identifier):
    """Native hit, not a text label, inventory receipt or far-away sight target."""
    target = scene.get("target") or {}
    eye = scene.get("eye_position")
    position = target.get("position")
    return bool(target.get("kind") == "block" and target.get("id") == identifier
                and eye and position and math.dist(eye, [v+.5 for v in position]) <= 4.5)


@dataclass(frozen=True)
class Stage:
    skill: str
    goal: str
    verify: Callable
    dimension_after: str | None = None
    dimension_before: str = "minecraft:overworld"


FINAL_GOAL = "defeat_dragon_and_reach_credits"

FOOD = ("minecraft:bread", "minecraft:cooked_beef", "minecraft:cooked_porkchop",
        "minecraft:cooked_chicken", "minecraft:cooked_mutton", "minecraft:baked_potato")
STAGES = (
    Stage("survival_prepare_overworld",
          "Gather wood/stone/iron, craft equipment, acquire food: iron pickaxe, iron sword, shield and 16 cooked food/bread.",
          lambda s, i: all(counts(i).get(k, 0) >= 1 for k in
                          ("minecraft:iron_pickaxe", "minecraft:iron_sword", "minecraft:shield"))
          and sum(counts(i).get(k, 0) for k in FOOD) >= 16,
          "minecraft:overworld"),
    Stage("survival_enter_nether", "Build, light and enter a Nether portal with native actions.",
          lambda s, i: s.get("dimension") == "minecraft:the_nether", "minecraft:the_nether"),
    Stage("survival_collect_blaze_rods", "Find a Nether fortress and obtain at least 8 blaze rods.",
          lambda s, i: counts(i).get("minecraft:blaze_rod", 0) >= 8,
          "minecraft:the_nether", dimension_before="minecraft:the_nether"),
    Stage("survival_collect_ender_pearls", "Obtain at least 16 ender pearls in the Nether without commands.",
          lambda s, i: counts(i).get("minecraft:ender_pearl", 0) >= 16,
          "minecraft:the_nether", dimension_before="minecraft:the_nether"),
    Stage("survival_return_overworld", "Return through the Nether portal.",
          lambda s, i: s.get("dimension") == "minecraft:overworld", "minecraft:overworld",
          dimension_before="minecraft:the_nether"),
    Stage("survival_craft_eyes", "After returning to the Overworld, craft at least 16 Eyes of Ender through native crafting.",
          lambda s, i: counts(i).get("minecraft:ender_eye", 0) >= 16, "minecraft:overworld"),
    Stage("survival_find_stronghold", "Follow thrown eyes, navigate/dig safely and reach the portal room.",
          lambda s, i: near_block(s, "minecraft:end_portal_frame"), "minecraft:overworld"),
    Stage("survival_activate_end_portal", "Insert missing eyes and observe an active End portal within native reach; do not enter.",
          lambda s, i: near_block(s, "minecraft:end_portal"), "minecraft:overworld"),
    Stage("survival_enter_end", "Enter the activated portal and observe arrival in the End.",
          lambda s, i: s.get("dimension") == "minecraft:the_end", "minecraft:the_end"),
    Stage("survival_defeat_dragon",
          "Defeat the Ender Dragon using native gameplay, then reach the active exit portal.",
          lambda s, i: near_block(s, "minecraft:end_portal"), "minecraft:the_end",
          dimension_before="minecraft:the_end"),
    Stage("survival_exit_end", "Enter the exit portal and observe the native credits screen.",
          lambda s, i: s.get("completion_screen_type") == "WinScreen", "minecraft:the_end",
          dimension_before="minecraft:the_end"),
)


def plan():
    return {"goal": FINAL_GOAL, "implementation": "scaffold_only",
            "final_pause_policy": "no_scripted_pause",
            "implemented_subgoals": ["gather_wood"],
            "not_implemented": [stage.skill for stage in STAGES],
            "stages": [{"skill": stage.skill, "goal": stage.goal,
                        "dimension_before": stage.dimension_before,
                        "dimension_after": stage.dimension_after} for stage in STAGES]}


def preflight(registry):
    available = {row["name"] for row in registry.describe()}
    missing = [stage.skill for stage in STAGES if stage.skill not in available]
    return {"goal": FINAL_GOAL, "status": "blocked" if missing else "ready_for_supervised_trial",
            "reason": "missing_survival_skills" if missing else "providers_present_not_gameplay_verified",
            "missing_skills": missing}


def run_campaign(player, registry, *, duration_seconds=120., pause_on_stop=True,
                 cancel=None, clock=time.monotonic):
    """One bounded supervised attempt. No automatic retries, respawn or reconnect.

    All stages must exist and validate BEFORE gameplay effects. Provider receipts
    are independently checked against native scene/inventory observations.
    No progress-file resume: a future resumable campaign needs explicit verified
    checkpoints, not cached success flags or assumptions about consumed resources.
    """
    if isinstance(duration_seconds, bool) or not math.isfinite(duration_seconds) or not .1 <= duration_seconds <= 600:
        raise ValueError("duration_seconds must be finite and between .1 and 600")
    if type(pause_on_stop) is not bool:
        raise ValueError("pause_on_stop must be a boolean")
    check = preflight(registry)
    if check["missing_skills"]:
        return {**check, "pause_on_stop": pause_on_stop, "completed": []}
    # Required provider schemas must accept this bounded common contract.
    for stage in STAGES:
        registry.prepare(stage.skill, {"timeout_seconds": min(120., duration_seconds)})
    cancel = cancel or threading.Event()
    deadline = clock()+duration_seconds
    completed = []
    result = {"goal": FINAL_GOAL, "status": "blocked", "reason": "not_started",
              "pause_on_stop": pause_on_stop, "completed": completed}
    owned = False

    def guard():
        if cancel.is_set():
            return "cancelled", "cancel_requested"
        if clock() >= deadline:
            return "timed_out", "deadline_exceeded"
        return None

    try:
        initial = player.observe()
        if not initial.get("in_world") or not initial.get("alive") or not initial.get("actor_session"):
            return {**result, "reason": "live_actor_required"}
        session = initial["actor_session"]
        dimension = initial.get("dimension")
        for stage in STAGES:
            stop = guard()
            if stop:
                result.update(status=stop[0], reason=stop[1])
                break
            if not pause_on_stop and player.menu().get("type") == "PauseScreen":
                result.update(reason="unexpected_pause_screen")
                break  # Never silently unpause or continue a no-pause attempt.
            before = player.observe()
            if before.get("actor_session") != session or not before.get("alive"):
                result.update(reason="actor_changed_or_dead")
                break
            if before.get("dimension") != stage.dimension_before:
                result.update(reason="stage_dimension_mismatch", stage=stage.skill,
                              expected_dimension=stage.dimension_before, observed_dimension=before.get("dimension"))
                break
            if not .1 <= deadline-clock():
                result.update(status="timed_out", reason="deadline_exceeded")
                break
            owned = True
            outcome = run_skill(registry, player, stage.skill,
                                {"timeout_seconds": min(120., deadline-clock())}, cancel_event=cancel)
            if outcome.status != "succeeded" or outcome.cleanup != "released":
                result.update(status=outcome.status if outcome.status != "succeeded" else "failed",
                              reason=outcome.reason if outcome.status != "succeeded" else "cleanup_not_confirmed",
                              stage=stage.skill)
                break
            stop = guard()
            if stop:
                result.update(status=stop[0], reason=stop[1])
                break
            scene, inventory = player.observe(), player.inventory()
            if stage.skill == "survival_exit_end":
                # Native screen type, never a game-supplied label or provider assertion.
                scene["completion_screen_type"] = player.menu().get("type")
            # Only explicit dimension-transition stages may change session.
            transition = (stage.skill in {"survival_enter_nether", "survival_return_overworld", "survival_enter_end"}
                          and dimension != stage.dimension_after
                          and scene.get("dimension") == stage.dimension_after)
            if (not scene.get("alive") or not scene.get("actor_session")
                    or (scene["actor_session"] != session and not transition)):
                result.update(reason="actor_changed_or_dead", stage=stage.skill)
                break
            if ((stage.dimension_after and scene.get("dimension") != stage.dimension_after)
                    or not stage.verify(scene, inventory)):
                result.update(reason="postcondition_not_observed", stage=stage.skill)
                break
            stop = guard()  # Reads and verification may have consumed the remaining budget.
            if stop:
                result.update(status=stop[0], reason=stop[1])
                break
            session, dimension = scene["actor_session"], scene.get("dimension")
            completed.append(stage.skill)
        else:
            result.update(status="succeeded", reason="native_credits_observed")
    except KeyboardInterrupt:
        cancel.set()
        result.update(status="cancelled", reason="keyboard_interrupt")
    except Exception as exc:
        result.update(status="failed", reason="execution_error", error_type=type(exc).__name__)
    finally:
        if owned:
            try:
                player.stop()
                result["cleanup"] = "released"
                if pause_on_stop and player.observe().get("in_world") and not player.menu().get("screen_open"):
                    player.open_pause()
            except Exception:
                result.update(status="failed", reason="cleanup_not_confirmed", cleanup="not_confirmed")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Offline roadmap (default)")
    mode.add_argument("--inspect", action="store_true", help="Read-only preflight on the selected client")
    mode.add_argument("--run", action="store_true", help="Explicit supervised activation; all required providers must exist")
    mode.add_argument("--gather-wood", type=int, metavar="COUNT", help="Run only the implemented local wood subgoal, not the full campaign")
    parser.add_argument("--provider", action="append", default=[], help="Explicit installed trusted skill provider; never auto-install")
    parser.add_argument("--duration", type=float, default=120., help="Cooperative attempt budget, .1–600 seconds; not a completion estimate")
    parser.add_argument("--no-pause", action="store_true",
                        help="Do not open the game pause menu on completion/failure; input release and F8 remain. Does not unpause Minecraft.")
    parser.add_argument("--stats-file", help="Explicit read-only vanilla player-statistics JSON; saved counters may lag live play")
    args = parser.parse_args(argv)
    if not args.inspect and not args.run and args.gather_wood is None:
        print(json.dumps(plan(), indent=2))
        return 0
    registry = default_registry()
    # Intentionally ignore environment provider selection: only explicit CLI opt-in.
    load_selected_plugins(registry, ",".join(args.provider))
    if args.gather_wood is not None:
        registry.prepare("gather_wood", {"count": args.gather_wood, "timeout_seconds": args.duration})
    baseline, baseline_report = capture_statistics(args.stats_file)

    def finish(result):
        snapshot, metrics = capture_statistics(args.stats_file)
        if snapshot is not None and baseline is not None:
            metrics = statistics_report(snapshot, baseline)
        elif args.stats_file:
            metrics["baseline_status"] = baseline_report["status"]
        print(json.dumps({**result, "statistics": metrics}, indent=2))
        return 0 if result["status"] == "succeeded" else 2

    if args.run and preflight(registry)["missing_skills"]:
        return finish(preflight(registry))
    try:
        with Bridge.from_env() as bridge:
            player = Player(bridge)
            if args.inspect:
                scene = player.observe()
                result = {**preflight(registry), "actor": {key: scene.get(key) for key in
                          ("in_world", "alive", "dimension", "position", "health", "hunger")},
                          "inventory_counts": counts(player.inventory()), "world_mutated": False}
            elif args.gather_wood is not None:
                try:
                    result = run_skill(registry, player, "gather_wood",
                        {"count": args.gather_wood, "timeout_seconds": args.duration}).model_dump(mode="json")
                finally:
                    # The example is a supervised one-shot, not an unattended Survival loop.
                    if not args.no_pause and player.observe().get("in_world") and not player.menu().get("screen_open"):
                        player.open_pause()
            else:
                result = run_campaign(player, registry, duration_seconds=args.duration, pause_on_stop=not args.no_pause)
    except Exception as exc:
        # Do not leak connection/config contents or automatically retry uncertain RPCs.
        result = {"status": "failed", "reason": "connection_or_configuration_error",
                  "error_type": type(exc).__name__}
    return finish(result)


if __name__ == "__main__":
    raise SystemExit(main())
