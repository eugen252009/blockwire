"""Opt-in deterministic controller. No model, wandering, pursuit or terrain shortcuts."""
from __future__ import annotations

import math
from typing import Literal
from pydantic import BaseModel, Field
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult
from .motion import FlatMotion


class Destination(BaseModel):
    model_config = SkillParameters.model_config
    x: float = Field(ge=-29_999_984, le=29_999_984)
    y: float = Field(ge=-2048, le=2048)
    z: float = Field(ge=-29_999_984, le=29_999_984)


class Autopilot(SkillParameters):
    destination: Destination | None = None
    movement: Literal["walk", "run", "sneak"] = "walk"
    combat: Literal["off", "defend"] = "off"
    evade_creepers: bool = False
    duration_seconds: float = Field(default=20, ge=.1, le=120,
        description="Maximum active period. No destination means stationary monitoring, except selected reactions.")


def _blocked(reason):
    return SkillResult(status="blocked", reason=reason, text="Autopilot stopped: " + reason.replace("_", " "))


def escape_target(state, threats):
    """One reachable cardinal neighbor that increases distance from EVERY known threat.

    Conservative: no optimistic detours through danger or arbitrary 'backward' input.
    """
    cells = state["cells"]
    current = next((i for i, c in enumerate(cells) if c["position"] == state["current_cell"]), None)
    if current is None:
        return None
    neighbors = set()
    for a, b in state["edges"]:
        if a == current:
            neighbors.add(b)
        if b == current:
            neighbors.add(a)
    position = state["position"]
    def distances(x, z):
        return [math.hypot(x-t["position"][0], z-t["position"][2]) for t in threats]
    baseline = distances(position[0], position[2])
    candidates = []
    for i in sorted(neighbors):
        cell = cells[i]
        if cell["hazards"]:
            continue
        x, y, z = cell["position"]
        ds = distances(x+.5, z+.5)
        if all(d > old+.05 for d, old in zip(ds, baseline)):
            candidates.append((min(ds), (x+.5, y, z+.5)))
    return max(candidates, default=(None, None))[1]


def autopilot(context: SkillContext, goal: Autopilot) -> SkillResult:
    started = context.clock()
    session = initial = health = None
    motion = FlatMotion()
    last_behavior = None
    last_position = None
    stationary = 0
    next_attack = 0.
    target = None if goal.destination is None else (goal.destination.x, goal.destination.y, goal.destination.z)

    while True:
        context.check()
        state = context.player.navigation()
        context.check()
        if state.get("profile") != "flat_full_blocks_v1":
            return _blocked("unsupported_navigation_profile")
        if not state.get("ready"):
            return _blocked(state.get("reason", "navigation_not_ready"))
        if state.get("threat_profile") != "nearby_hostiles_v1":
            return _blocked("autopilot_observation_required")
        if session is None:
            session, initial, health = state["actor_session"], state["position"][:], state["health"]
            if target and math.hypot(initial[0]-target[0], initial[2]-target[2]) > 64:
                return _blocked("target_out_of_range_64_blocks")
        if state["actor_session"] != session:
            return _blocked("actor_session_changed")
        position = state["position"]
        if abs(position[1] - initial[1]) > .2 or (target and abs(position[1]-target[1]) > .2):
            return _blocked("vertical_route_unsupported")
        if math.hypot(position[0]-initial[0], position[2]-initial[2]) > 64:
            return _blocked("activity_radius_exceeded")
        if state["on_fire"] or state["health"] < health:
            return _blocked("damage_observed")
        current = next((c for c in state["cells"] if c["position"] == state["current_cell"]), None)
        if current is None or current["hazards"]:
            return _blocked("unsafe_current_cell")
        if context.clock()-started >= goal.duration_seconds:
            if target:
                return SkillResult(status="timed_out", reason="active_period_elapsed", text="Destination not observed before active period ended.")
            return SkillResult(status="succeeded", reason="monitoring_completed", text="Selected monitoring period completed; safety is not guaranteed.")

        threats = state["nearby_hostiles"]
        creepers = [t for t in threats if t["type"] == "minecraft:creeper"]
        behavior, destination = "idle", None
        enemy = None
        if creepers and goal.evade_creepers:
            behavior = "evade_creeper"
            destination = escape_target(state, threats)
            if destination is None:
                return _blocked("no_known_escape_route")
        elif threats:
            # Proximity defense, NOT attribution of an actual attack. Never pursue or attack players.
            eligible = [t for t in threats if t["type"] != "minecraft:creeper"
                        and t["distance"] <= 3 and t["visible"]]
            if goal.combat == "defend" and eligible:
                behavior = "defend"
                enemy = min(eligible, key=lambda t: t["distance"])
            else:
                return _blocked("known_danger_nearby")
        elif target:
            if math.hypot(position[0]-target[0], position[2]-target[2]) <= .3:
                if motion.holding:
                    motion.halt(context)
                    context.pause(.1)
                    continue  # Re-observe after releasing W before claiming arrival.
                return SkillResult(status="succeeded", reason="arrived", text="Observed arrival at the requested destination.", details={"position": position})
            behavior, destination = "travel", target

        if behavior != last_behavior:
            context.check()
            context.player.stop()
            motion = FlatMotion()
            stationary = 0
            last_position = None
            last_behavior = behavior
        context.publish({"behavior": behavior, "position": position, "destination": target,
                         "movement": goal.movement, "combat": goal.combat,
                         "evade_creepers": goal.evade_creepers, "control_mode": motion.mode,
                         "owned_input_lease": motion.holding})
        if destination:
            if last_position is not None and math.dist(position, last_position) < .015:
                stationary += 1
            else:
                stationary = 0
                last_position = position[:]  # Accumulate small advances across faster feedback samples.
            if stationary >= 12:
                return _blocked("stuck")
            view = None
            if behavior == "travel":
                context.check()
                scene = context.player.observe()
                context.check()
                if not scene.get("in_world") or not scene.get("alive"):
                    return _blocked("not_in_world_or_dead")
                view = (scene["yaw"], scene["pitch"])
            result = motion.pulse(context, state, destination,
                                  "run" if behavior == "evade_creeper" else goal.movement,
                                  threats if behavior == "evade_creeper" else (),
                                  view=view, continuous=behavior == "travel")
            if result:
                return result
            if motion.turning:
                last_position = None
                stationary = 0
        elif enemy:
            eye, aim = state["eye_position"], enemy["eye_position"]
            dx, dy, dz = (aim[i]-eye[i] for i in range(3))
            context.check()
            context.player.look(math.degrees(math.atan2(-dx, dz)),
                                -math.degrees(math.atan2(dy, math.hypot(dx, dz))), actor_session=session)
            context.pause(.08)  # Native crosshair refreshes on a rendered frame, not on look receipt.
            scene = context.player.observe()
            context.check()
            hit = scene.get("target", {})
            if hit.get("kind") == "entity" and hit.get("id") == enemy["entity_id"] and context.clock() >= next_attack:
                context.player.action("attack", actor_session=session, target_entity_id=enemy["entity_id"])
                next_attack = context.clock()+.6
            context.pause(.13)
        else:
            context.pause(.13)


AUTOPILOT = SkillDefinition("autopilot",
    "Explicitly activate bounded algorithmic flat-ground travel or stationary monitoring. "
    "Optional nearby-hostile defense (no pursuit/players) and creeper evasion interrupt travel. "
    "No model, jumping, swimming or safety guarantee. Cancel and await cleanup to disable.",
    Autopilot, autopilot)
