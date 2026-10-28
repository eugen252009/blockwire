"""Approach a discovered interactable, never use/open it or query arbitrary coordinates."""
from __future__ import annotations

from collections import deque
import math
from pydantic import Field, field_validator
from .motion import FlatMotion, turn_view_step
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult, SkillStop


class Approach(SkillParameters):
    target: str = Field(default="minecraft:chest", min_length=1, max_length=128,
        pattern=r"^(?:[a-z0-9_.-]+:)?[a-z0-9_./-]+$",
        description="Exact block registry ID; unqualified 'chest' means minecraft:chest, not a translated name.")
    position: list[int] | None = Field(default=None, min_length=3, max_length=3,
        description="Optional exact [x,y,z] BLOCK position, which must already be in the visible interactable list.")
    sneak: bool = False
    avoid_damage: bool = True

    @field_validator("position")
    @classmethod
    def bounded_position(cls, value):
        if value is not None and (abs(value[0]) > 29_999_984 or not -2048 <= value[1] <= 2048 or abs(value[2]) > 29_999_984):
            raise ValueError("Block position outside supported world bounds")
        return value


def _matches(hit, selected):
    return (hit.get("kind") == "block" and hit.get("id") == selected["id"]
            and hit.get("position") == selected["position"])


def _sighted(hit, selected):
    # sight_target is an on-demand outline ray, unlike the cached render crosshair target.
    return (hit.get("id"), hit.get("position")) == (selected["id"], selected["position"])


TARGET_CHECK_PULSES = 8
TARGET_CHECK_SECONDS = 3.


def _target_in_view(scene, selected):
    """Conservative central 45-degree cone, not pixel visibility or a new world query."""
    yaw, pitch = math.radians(scene["yaw"]), math.radians(scene["pitch"])
    view = (-math.sin(yaw)*math.cos(pitch), -math.sin(pitch), math.cos(yaw)*math.cos(pitch))
    delta = [selected["aim_position"][i]-scene["eye_position"][i] for i in range(3)]
    length = math.sqrt(sum(d*d for d in delta))
    return length == 0 or sum(delta[i]*view[i] for i in range(3))/length >= math.cos(math.pi/4)


def _reachable(state, avoid_damage):
    cells = state["cells"]
    allowed = {i for i, c in enumerate(cells) if not (avoid_damage and c["hazards"])}
    start = next((i for i in allowed if cells[i]["position"] == state["current_cell"]), None)
    if start is None:
        return {}
    adjacency = {i: [] for i in allowed}
    for a, b in state["edges"]:
        if a in allowed and b in allowed:
            adjacency[a].append(b)
            adjacency[b].append(a)
    distance, queue = {start: 0}, deque([start])
    while queue:
        i = queue.popleft()
        for j in adjacency[i]:
            if j not in distance:
                distance[j] = distance[i]+1
                queue.append(j)
    return {tuple(cells[i]["position"]): cost for i, cost in distance.items()}


def _plan(state, selected, reachable):
    """Only known reachable mesh cells are destinations; never stand inside the target.

    Distant targets may have a known closer frontier, not a globally proven route.
    """
    tx, _, tz = selected["position"]
    aim = selected["aim_position"]
    eye_height = state["eye_position"][1]-state["position"][1]
    standing = []
    for (x, y, z), cost in reachable.items():
        if (x, z) == (tx, tz):
            continue
        center = (x+.5, y, z+.5)
        if math.dist((center[0], y+eye_height, center[2]), aim) <= 3.0:
            standing.append((cost, math.dist(center, state["position"]), center))
    if standing:
        return min(standing)[2], True
    # Once the target's local neighborhood is known, do not improvise a standing position.
    if max(abs(tx-state["current_cell"][0]), abs(tz-state["current_cell"][2])) <= 4:
        return None
    def distance(cell):
        return math.hypot(cell[0]+.5-tx-.5, cell[2]+.5-tz-.5)
    if not reachable:
        return None
    frontier = min(reachable, key=lambda cell: (distance(cell), reachable[cell], cell))
    if reachable[frontier] == 0 or distance(frontier) >= distance(tuple(state["current_cell"])):
        return None
    return (frontier[0]+.5, frontier[1], frontier[2]+.5), False


def approach(context: SkillContext, goal: Approach) -> SkillResult:
    block_id = goal.target if ":" in goal.target else "minecraft:"+goal.target
    session = initial = health = None

    def navigation():
        nonlocal session, initial, health
        context.check()
        state = context.player.navigation()
        context.check()
        if state.get("profile") != "flat_full_blocks_v1":
            raise SkillStop("blocked", "unsupported_navigation_profile")
        if not state.get("ready"):
            raise SkillStop("blocked", state.get("reason", "navigation_not_ready"))
        if session is None:
            session, initial, health = state["actor_session"], state["position"][:], state["health"]
        if state["actor_session"] != session:
            raise SkillStop("blocked", "actor_session_changed")
        if abs(state["position"][1]-initial[1]) > .2:
            raise SkillStop("blocked", "vertical_route_unsupported")
        if math.hypot(state["position"][0]-initial[0], state["position"][2]-initial[2]) > 64:
            raise SkillStop("blocked", "activity_radius_exceeded")
        if goal.avoid_damage:
            if state["health"] < health:
                raise SkillStop("blocked", "damage_observed")
            current = next((c for c in state["cells"] if c["position"] == state["current_cell"]), None)
            if state.get("on_fire") or state.get("nearby_hostiles") or (current and current["hazards"]):
                raise SkillStop("blocked", "known_danger_nearby")
        health = state["health"]
        if not state.get("current_center_access"):
            raise SkillStop("blocked", "current_cell_center_obstructed")
        return state

    def observe():
        context.check()
        scene = context.player.observe()
        context.check()
        if not scene.get("in_world") or not scene.get("alive"):
            raise SkillStop("blocked", "not_in_world_or_dead")
        if scene.get("visibility", {}).get("profile") != "sampled_surfaces_v1":
            raise SkillStop("blocked", "visibility_observation_required")
        return scene

    def bearing(state, selected):
        eye, aim = state["eye_position"], selected["aim_position"]
        dx, dy, dz = (aim[i]-eye[i] for i in range(3))
        return math.degrees(math.atan2(-dx, dz)), -math.degrees(math.atan2(dy, math.hypot(dx, dz)))

    def aim_at(state, selected, scene):
        while True:
            if not turn_view_step(context, (scene["yaw"], scene["pitch"]), bearing(state, selected), session):
                context.pause(.1)
                scene = observe()
                state = navigation()
                return state, scene
            scene = observe()
            state = navigation()  # No drive while turning; keep actor/readiness/deadline checks responsive.

    state = navigation()
    scene = observe()
    state = navigation()  # Bracket scene reads with the actor fence; snapshots are still not atomic.
    candidates = [dict(row) for row in scene["visible_interactables"] if row["id"] == block_id
                  and (goal.position is None or row["position"] == goal.position)]
    candidates.sort(key=lambda row: (math.dist(state["eye_position"], row["aim_position"]), row["position"]))
    if not candidates:
        raise SkillStop("blocked", "target_not_visible")
    reachable = _reachable(state, goal.avoid_damage)
    selected = next((row for row in candidates if _plan(state, row, reachable) is not None), None)
    if selected is None:
        raise SkillStop("blocked", "no_known_approach_route")
    if math.hypot(selected["position"][0]+.5-initial[0], selected["position"][2]+.5-initial[2]) > 64:
        raise SkillStop("blocked", "target_out_of_range_64_blocks")
    motion = FlatMotion()
    previous = None
    stationary = steps = unconfirmed_pulses = 0
    confirmed_at = context.clock()
    while True:
        context.check()
        updated = next((row for row in scene["visible_interactables"] if row["id"] == selected["id"]
                        and row["position"] == selected["position"]), None)
        if updated is None and not _sighted(scene.get("sight_target", {}), selected):
            if _target_in_view(scene, selected) or any(row["position"] == selected["position"] for row in scene["visible_interactables"]):
                raise SkillStop("blocked", "target_lost")
            # Looking along a route can legitimately put the selected chest outside the view.
            # Memory is bounded: stop and confirm it before another pulse when either budget expires.
            if unconfirmed_pulses >= TARGET_CHECK_PULSES or context.clock()-confirmed_at >= TARGET_CHECK_SECONDS:
                context.publish({"phase": "checking_target", "target": {"id": selected["id"],
                    "position": selected["position"]}, "position": state["position"], "steps": steps})
                context.check()
                motion.halt(context)
                state, scene = aim_at(state, selected, scene)
                if not any(row["id"] == selected["id"] and row["position"] == selected["position"]
                           for row in scene["visible_interactables"]) and not _sighted(scene.get("sight_target", {}), selected):
                    raise SkillStop("blocked", "target_lost")
                unconfirmed_pulses, confirmed_at = 0, context.clock()
                previous = None
                stationary = 0
                continue
        else:
            unconfirmed_pulses, confirmed_at = 0, context.clock()
        if updated:
            selected = dict(updated)
        plan = _plan(state, selected, _reachable(state, goal.avoid_damage))
        if plan is None:
            raise SkillStop("blocked", "no_known_approach_route")
        destination, standing = plan
        position = state["position"]
        close = standing and math.hypot(position[0]-destination[0], position[2]-destination[2]) <= .3
        context.publish({"phase": "aiming" if close else "turning" if motion.turning else "walking", "target": {"id": selected["id"],
            "position": selected["position"]}, "position": position, "standing_destination": destination,
            "route_is_partial": not standing, "steps": steps,
            "control_mode": motion.mode, "owned_input_lease": motion.holding})
        if close:
            context.check()
            motion.halt(context)
            state, scene = aim_at(state, selected, scene)
            for _ in range(5):
                scene = observe()
                state = navigation()
                if (_matches(scene.get("target", {}), selected)
                        and (_sighted(scene.get("sight_target", {}), selected) or any(
                            row["id"] == selected["id"] and row["position"] == selected["position"] for row in scene["visible_interactables"]))
                        and math.hypot(state["position"][0]-destination[0], state["position"][2]-destination[2]) <= .3):
                    return SkillResult(status="succeeded", reason="ready_to_interact",
                        text="Observed the selected block in native interaction reach. It was not opened or used.",
                        details={"target": {"id": selected["id"], "position": selected["position"]},
                            "position": state["position"], "native_target": scene["target"], "steps": steps})
                context.pause(.1)
            raise SkillStop("blocked", "native_target_not_acquired")
        if previous is not None and math.dist(position, previous) < .015:
            stationary += 1
        else:
            stationary = 0
            previous = position[:]  # Accumulate small advances across faster feedback samples.
        if stationary >= 12:
            raise SkillStop("blocked", "stuck")
        result = motion.pulse(context, state, destination,
            "sneak" if goal.sneak or goal.avoid_damage else "walk", avoid_damage=goal.avoid_damage, max_ticks=3,
            view=(scene["yaw"], scene["pitch"]), continuous=True)
        if result:
            result.text = "Approach stopped: " + result.reason.replace("_", " ")
            return result
        if motion.turning:
            previous = None
            stationary = 0  # A bounded turn without movement is not a failed walking pulse.
        else:
            steps += 1
            unconfirmed_pulses += 1
        context.check()
        # Rolling leases deliberately remain held during observation and small steering updates.
        scene = observe()  # Keep the travel heading; a bounded checkpoint can recheck an out-of-view target.
        state = navigation()


APPROACH = SkillDefinition("approach",
    "Approach an initially visible interactable by exact block ID (chest means minecraft:chest). "
    "Choose the nearest candidate with a supported local route; optional exact visible block position. "
    "Face the route and primarily walk forward on flat full-block terrain, with tiny lateral corrections. "
    "Recheck out-of-view targets at bounded stopped checkpoints; aim and confirm the exact native target. "
    "Never opens/uses it. Partial visibility/routes, at most 64 blocks; damage avoidance is best effort.",
    Approach, approach)
