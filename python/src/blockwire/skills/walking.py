"""Receding-horizon flat walking using explicit client-known native collision edges."""
from __future__ import annotations

from collections import deque
import math
from pydantic import Field
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult


class WalkTo(SkillParameters):
    x: float = Field(ge=-29_999_984, le=29_999_984, description="World X, not a relative offset.")
    y: float = Field(ge=-2048, le=2048, description="Feet Y. First version supports the current flat full-block level only.")
    z: float = Field(ge=-29_999_984, le=29_999_984, description="World Z, not a relative offset.")
    sneak: bool = False
    avoid_damage: bool = Field(default=True, description="Conservative known-hazard avoidance and crouching, NOT immunity.")


def route(mesh: dict, target: tuple[float, float, float], avoid_damage: bool):
    """Shortest cardinal path to target cell or a strictly closer visible frontier."""
    cells = mesh["cells"]
    positions = [tuple(cell["position"]) for cell in cells]
    allowed = {i for i, cell in enumerate(cells) if not (avoid_damage and cell["hazards"])}
    source = tuple(mesh["current_cell"])
    if source not in positions or positions.index(source) not in allowed:
        return None
    start = positions.index(source)
    destination = (math.floor(target[0]), source[1], math.floor(target[2]))
    adjacency = {i: [] for i in allowed}
    for a, b in mesh["edges"]:
        if a in allowed and b in allowed:
            adjacency[a].append(b)
            adjacency[b].append(a)
    previous = {start: None}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in previous:
                previous[neighbor] = current
                queue.append(neighbor)
    def distance(index):
        p = positions[index]
        return math.hypot(p[0] + .5 - target[0], p[2] + .5 - target[2])
    if destination in positions:
        end = positions.index(destination)
        if end not in previous:
            return None
    else:
        end = min(previous, key=distance)
        if end == start or distance(end) >= distance(start):
            return None
    path = [end]
    while previous[path[-1]] is not None:
        path.append(previous[path[-1]])
    return [positions[index] for index in reversed(path)]


def walk_to(context: SkillContext, goal: WalkTo) -> SkillResult:
    target = (goal.x, goal.y, goal.z)
    session, health, initial = None, None, None
    previous_position = None
    stationary = 0
    steps = 0
    pending_cell = departed_cell = None
    effective_sneak = goal.sneak or goal.avoid_damage

    def blocked(reason, state):
        return SkillResult(status="blocked", reason=reason, text="Walk stopped: " + reason.replace("_", " "),
                           details={"target": target, "last_observation": state, "steps": steps})

    while True:
        context.check()
        state = context.player.navigation()
        context.check()
        if state.get("profile") != "flat_full_blocks_v1":
            return blocked("unsupported_navigation_profile", state)
        if not state.get("ready"):
            return blocked(state.get("reason", "navigation_not_ready"), state)
        if session is None:
            session, health, initial = state["actor_session"], state["health"], state["position"]
            if math.dist((initial[0], initial[2]), (goal.x, goal.z)) > 64:
                return blocked("target_out_of_range_64_blocks", state)
        if session != state["actor_session"]:
            return blocked("actor_session_changed", state)
        if abs(state["position"][1] - goal.y) > .2:
            return blocked("vertical_route_unsupported", state)
        if goal.avoid_damage:
            if state["health"] < health:
                return blocked("damage_observed", state)
            current_hazards = next((c["hazards"] for c in state["cells"]
                                    if c["position"] == state["current_cell"]), [])
            if state.get("on_fire") or state.get("nearby_hostiles") or current_hazards:
                return blocked("known_danger_nearby", state)
        position = state["position"]
        distance = math.hypot(position[0] - goal.x, position[2] - goal.z)
        if distance <= .3:
            return SkillResult(status="succeeded", reason="arrived", text="Reached the requested walking radius.",
                details={"position": position, "target": target, "distance": distance, "steps": steps,
                         "effective_sneak": effective_sneak, "avoid_damage_is_best_effort": True})
        if previous_position is not None and math.dist(position, previous_position) < .015:
            stationary += 1
        else:
            stationary = 0
        if stationary >= 12:
            return blocked("stuck", state)
        previous_position = position[:]
        path = route(state, target, goal.avoid_damage)
        if path is None:
            return blocked("no_known_safe_route", state)
        if not state.get("current_center_access"):
            return blocked("current_cell_center_obstructed", state)
        center = (path[0][0]+.5, path[0][2]+.5)
        # Retain a cardinal crossing while inside its source cell; otherwise repeatedly
        # recentering would reverse each short pulse. Revalidate that edge on every sample.
        cell = tuple(state["current_cell"])
        if pending_cell is not None:
            continuing = (cell == departed_cell and len(path) > 1 and path[1] == pending_cell)
            centering_destination = cell == pending_cell and math.hypot(
                position[0]-(pending_cell[0]+.5), position[2]-(pending_cell[2]+.5)) > .12
            if not (continuing or centering_destination):
                pending_cell = departed_cell = None
        if cell == (math.floor(goal.x), cell[1], math.floor(goal.z)):
            waypoint = (goal.x, goal.z)
        elif pending_cell is not None:
            waypoint = (pending_cell[0]+.5, pending_cell[2]+.5)
        elif math.hypot(position[0]-center[0], position[2]-center[1]) > .12:
            waypoint = center
        elif len(path) > 1:
            departed_cell, pending_cell = cell, path[1]
            waypoint = (pending_cell[0]+.5, pending_cell[2]+.5)
        else:
            waypoint = (goal.x, goal.z)
        delta_x, delta_z = waypoint[0]-position[0], waypoint[1]-position[2]
        waypoint_distance = math.hypot(delta_x, delta_z)
        context.publish({"position": position, "target": target, "distance": distance, "steps": steps,
                         "effective_sneak": effective_sneak})
        context.check()
        context.player.look(math.degrees(math.atan2(-delta_x, delta_z)), 0, actor_session=session)
        context.check()
        # A conservative short hold; no jumping, sprinting, digging, placement or teleportation.
        ticks = min(3, max(1, math.floor(waypoint_distance / (.065 if effective_sneak else .22))))
        buttons = ["forward", "sneak"] if effective_sneak else ["forward"]
        context.player.drive(buttons, ticks, wait=False, actor_session=session)
        context.pause(ticks*.05 + .08)
        steps += 1


WALK_TO = SkillDefinition(
    "walk_to",
    "Reach a world position on known loaded flat full-block ground. Detours around native collision "
    "obstacles; no stairs, jumping, fluids or chunk generation. avoid_damage crouches and avoids known "
    "hazards/nearby hostiles and stops on health loss; never guarantees no damage. At most 64 blocks per goal.",
    WalkTo, walk_to,
)
