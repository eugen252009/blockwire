"""Receding-horizon flat walking using explicit client-known native collision edges."""
from __future__ import annotations

from typing import Literal
import heapq
import math
from pydantic import Field
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult


class WalkTo(SkillParameters):
    x: float = Field(ge=-29_999_984, le=29_999_984, description="World X, not a relative offset.")
    y: float = Field(ge=-2048, le=2048, description="Feet Y. Different levels require terrain=True and observed one-block step edges.")
    z: float = Field(ge=-29_999_984, le=29_999_984, description="World Z, not a relative offset.")
    terrain: bool = Field(default=False, description='Opt in to bounded full-block one-block climbs/descents; no slabs, fluids or gaps.')
    arrival_radius: float = Field(default=.3,ge=.08,le=.3,description='Observed horizontal arrival radius. Native placement adapters may request tighter centering; ordinary walking retains 0.3 blocks.')
    sneak: bool = False
    movement: Literal['walk','run','sneak'] = 'walk'
    avoid_damage: bool = Field(default=True, description="Conservative known-hazard avoidance, NOT immunity. Sneaking is controlled separately.")


def route(mesh: dict, target: tuple[float, float, float], avoid_damage: bool):
    """Shortest cardinal path to target cell or a strictly closer visible frontier."""
    cells = mesh["cells"]
    positions = [tuple(cell["position"]) for cell in cells]
    allowed = {i for i, cell in enumerate(cells) if not (avoid_damage and cell["hazards"])}
    source = tuple(mesh["current_cell"])
    if source not in positions or positions.index(source) not in allowed:
        return None
    start = positions.index(source)
    stepped = mesh.get("profile") == "stepped_full_blocks_v1"
    destination = (math.floor(target[0]), round(target[1]) if stepped else source[1], math.floor(target[2]))
    adjacency = {i: [] for i in allowed}
    for a, b in mesh["edges"]:
        if a in allowed and b in allowed:
            adjacency[a].append(b)
            adjacency[b].append(a)
    previous = {start: None}
    costs = {start: 0.}
    serial = 0
    queue = [(0., serial, start)]
    while queue:
        cost, _, current = heapq.heappop(queue)
        if cost > costs[current]:
            continue
        a = positions[current]
        for neighbor in adjacency[current]:
            b = positions[neighbor]
            edge_cost = math.sqrt((a[0]-b[0])**2+(a[1]-b[1])**2+(a[2]-b[2])**2)
            candidate = cost+edge_cost
            if candidate < costs.get(neighbor, math.inf)-1e-9:
                costs[neighbor] = candidate
                previous[neighbor] = current
                serial += 1  # Preserve native edge discovery order for equal-cost paths.
                heapq.heappush(queue, (candidate, serial, neighbor))
    def distance(index):
        p = positions[index]
        return math.sqrt((p[0]+.5-target[0])**2+(p[2]+.5-target[2])**2+((p[1]-target[1])**2 if stepped else 0))
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


def walk_to(context: SkillContext, goal: WalkTo, *, expected_session=None) -> SkillResult:
    from .crafting import ensure_gameplay
    ensure_gameplay(context)
    target = (goal.x, goal.y, goal.z)
    session, health, initial = None, None, None
    previous_position = None
    arrival_sample = None
    stationary = 0
    steps = 0
    from .motion import FlatMotion  # Local import: the motor also consumes route().
    motion = FlatMotion()
    effective_sneak = goal.sneak or goal.movement=='sneak'

    def blocked(reason, state):
        return SkillResult(status="blocked", reason=reason, text="Walk stopped: " + reason.replace("_", " "),
                           details={"target": target, "last_observation": state, "steps": steps})

    while True:
        context.check()
        state = context.player.navigation(terrain=True) if goal.terrain else context.player.navigation()
        context.check()
        if state.get("profile") != ("stepped_full_blocks_v1" if goal.terrain else "flat_full_blocks_v1"):
            return blocked("unsupported_navigation_profile", state)
        if not state.get("ready"):
            return blocked(state.get("reason", "navigation_not_ready"), state)
        if expected_session is not None and state.get("actor_session") != expected_session:
            return blocked("actor_session_changed", state)
        if session is None:
            session, health, initial = state["actor_session"], state["health"], state["position"]
            if math.dist((initial[0], initial[2]), (goal.x, goal.z)) > 64:
                return blocked("target_out_of_range_64_blocks", state)
        if session != state["actor_session"]:
            return blocked("actor_session_changed", state)
        if not goal.terrain and abs(state["position"][1] - goal.y) > .2:
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
        if distance <= goal.arrival_radius and abs(position[1]-goal.y) <= .2:
            if motion.holding:
                motion.halt(context)
                context.pause(.2)
                continue  # Observe arrival again after releasing native forward input.
            # A released input lease is not zero native velocity. Every radius, including
            # ordinary 0.3-block walking, requires observed settling before success.
            if float(state.get("horizontal_speed",0.)) > .004:
                context.pause(.1)
                continue
            if arrival_sample is None or math.dist(position,arrival_sample) > .005:
                arrival_sample = position[:]
                context.pause(.2)
                continue
            return SkillResult(status="succeeded", reason="arrived", text="Reached the requested walking radius.",
                details={"position": position, "target": target, "distance": distance, "steps": steps,
                         "effective_sneak": effective_sneak, "avoid_damage_is_best_effort": True})
        arrival_sample = None
        if previous_position is not None and math.dist(position, previous_position) < .015:
            stationary += 1
        else:
            stationary = 0
            previous_position = position[:]  # Accumulate small feedback advances.
        if stationary >= 12:
            return blocked("stuck", state)
        context.check()
        scene = context.player.observe()
        context.check()
        if not scene.get("in_world") or not scene.get("alive"):
            return blocked("scene_not_ready", state)
        context.publish({"position": position, "target": target, "distance": distance, "steps": steps,
                         "effective_sneak": effective_sneak, "control_mode": motion.mode,
                         "owned_input_lease": motion.holding})
        result = motion.pulse(context, state, target, "sneak" if effective_sneak else goal.movement,
                              avoid_damage=goal.avoid_damage, max_ticks=3,
                              view=(scene["yaw"], scene["pitch"]), continuous=True, precision_sneak=False,
                              arrival_radius=goal.arrival_radius)
        if result is not None:
            return result
        if motion.turning:
            previous_position = None
            stationary = 0
            continue
        steps += 1


WALK_TO = SkillDefinition(
    "walk_to",
    "Reach a world position on known loaded flat full-block ground. Detours around native collision "
    "obstacles. Flat by default; terrain=True permits bounded one-block full-cube jumps/descents, not slabs/gaps/fluids. No chunk generation. Sneak only when requested. avoid_damage avoids known "
    "hazards/nearby hostiles and stops on health loss; never guarantees no damage. At most 64 blocks per goal.",
    WalkTo, walk_to,
)
