"""Bounded, local harvesting of observed vanilla logs through native input only."""
from __future__ import annotations

import math
from pydantic import Field
from .approaching import _reachable
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult, SkillStop
from .motion import FlatMotion, rotate_view_timed


LOGS = frozenset("minecraft:" + species + "_log" for species in
                 ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "mangrove", "cherry", "pale_oak"))


class GatherWood(SkillParameters):
    count: int = Field(default=1, ge=1, le=16, description="Additional vanilla logs that must appear in inventory, not merely blocks broken.")
    terrain: bool = False
    scan: bool = Field(default=True, description="Allow a bounded stopped camera scan for nearby exposed logs.")


def log_count(inventory):
    return sum(item.get("count", 0) for item in inventory.get("items", []) if item.get("item") in LOGS)


def observed_blocks(scene, allowed=LOGS):
    """Decode only explicitly sampled surfaces. Unknown space is never filled."""
    found = set()
    for key in ("target", "sight_target"):
        hit = scene.get(key) or {}
        if hit.get("id") in allowed and len(hit.get("position", [])) == 3:
            found.add((hit["id"], tuple(hit["position"])))
    blocks = scene.get("visible_blocks", {})
    if blocks.get("encoding") == "palette_x_runs_v1":
        origin, palette = blocks["origin"], blocks["palette"]
        for index, dx, dy, dz, length in blocks["runs"]:
            if palette[index] in allowed:
                for offset in range(length):
                    found.add((palette[index], (origin[0]+dx+offset, origin[1]+dy, origin[2]+dz)))
    return sorted(found)


def observed_logs(scene):
    return observed_blocks(scene, LOGS)


def _same(hit, target):
    return bool(hit and hit.get("id") == target[0] and tuple(hit.get("position", [])) == target[1])


def _standing(state, target, *, excavate=False):
    """Known same-level standing cells near the log, never its occupied column."""
    _, (tx, ty, tz) = target
    stepped = state.get("profile") == "stepped_full_blocks_v1"
    if not stepped and ty < math.floor(state["position"][1]):
        return None  # Never remove a support log below feet.
    if not stepped and ty > math.floor(state["position"][1])+1:
        return None  # An overhead drop can remain on the lower trunk, outside native pickup.
    eye_height = state["eye_position"][1]-state["position"][1]
    options = []
    if excavate and stepped and ty == round(state["position"][1])-1:
        cx,cy,cz = state["current_cell"]
        if abs(cx-tx)+abs(cz-tz)==1 and any(c["position"]==[cx,cy,cz] and not c["hazards"] for c in state["cells"]):
            return (cx+.5,cy,cz+.5)  # Mine from retained support; do not assume a landing floor.
    for (x, y, z), cost in _reachable(state, True).items():
        if stepped and not y <= ty <= y+1:
            continue
        if (x, z) == (tx, tz):
            continue
        center = (x+.5, y, z+.5)
        # A diagonal standing cell can reach the block but miss native item pickup.
        # Prefer a directly adjacent cardinal cell; pickup still needs observation.
        if (math.hypot(x-tx, z-tz) <= 1.
                and math.dist((center[0], y+eye_height, center[2]), (tx+.5, ty+.5, tz+.5)) <= 3.):
            options.append((cost, math.dist(center, state["position"]), center))
    return min(options)[2] if options else None


def _support_safe(state, target, excavate):
    tx,ty,tz = target[1]
    px,py,pz = state['position']
    overlap = abs(px-tx-.5)<.81 and abs(pz-tz-.5)<.81
    permitted = (excavate and state.get('profile')=='stepped_full_blocks_v1' and ty==round(py)-1
                 and abs(math.floor(px)-tx)+abs(math.floor(pz)-tz)==1 and not overlap)
    return (ty>=math.floor(py) or permitted) and (math.floor(px),math.floor(pz))!=(tx,tz)


def mine_observed_target(context, selected, session, navigation, observe, *, tools=None, excavate=False, collected=0):
    """Shared native mining motor. True means target no longer hit, NOT collection or goal success."""
    state, scene = navigation(), observe()
    # Aim while stopped; retain an already exact fresh hit (also supports thin plants).
    while not (_same(scene.get("target"), selected) and _same(scene.get("sight_target"), selected)):
        aim = [selected[1][0]+.5, selected[1][1]+.25, selected[1][2]+.5]
        delta = [aim[i]-scene["eye_position"][i] for i in range(3)]
        wanted = (math.degrees(math.atan2(-delta[0], delta[2])),
                  -math.degrees(math.atan2(delta[1], math.hypot(delta[0], delta[2]))))
        turning = rotate_view_timed(context, (scene["yaw"], scene["pitch"]), wanted, session)
        context.pause(.05)
        state, scene = navigation(), observe()
        if not turning:
            break
    for _ in range(5):
        if _same(scene.get("target"), selected) and _same(scene.get("sight_target"), selected):break
        context.pause(.05)
        state,scene=navigation(),observe()  # Permit bounded render-hit refresh, never retry an uncertain action.
    else:
        return False  # Do not attack occluding entities or a different block.
    mining_deadline = context.clock()+12.
    while _same(scene.get("target"), selected) and _same(scene.get("sight_target"), selected):
        state = navigation()
        scene = observe()
        if not (_same(scene.get("target"), selected) and _same(scene.get("sight_target"), selected)):
            break
        if tools is not None and (scene.get('holding', {}).get('item') not in tools or
                any(e.get('id') == 'minecraft:silk_touch' for e in scene.get('holding', {}).get('enchantments', []))):
            raise SkillStop('blocked', 'appropriate_equipped_tool_required')
        if not _support_safe(state,selected,excavate):
            raise SkillStop("blocked", "support_mining_prohibited")
        if scene["target"].get("kind") != "block":
            raise SkillStop("blocked", "native_block_target_required")
        if math.dist(scene["eye_position"], [v+.5 for v in selected[1]]) > 3.:
            raise SkillStop("blocked", "log_out_of_reach")
        if context.clock() >= mining_deadline:
            raise SkillStop("blocked", "mining_not_observed")
        context.publish({"phase": "mining", "target": selected, "collected": collected})
        context.check()
        context.player.drive(["attack"], 6, wait=False, actor_session=session)
        context.pause(.05)
        scene = observe()
    context.check()
    context.player.stop()
    navigation()
    return True


def _gather(context: SkillContext, goal, *, block_ids=LOGS, drop_ids=LOGS, tools=None, expected_session=None) -> SkillResult:
    from .crafting import ensure_gameplay
    ensure_gameplay(context)
    def count_items(value):
        return sum(i.get('count', 0) for i in value.get('items', []) if i.get('item') in drop_ids)

    session = health = origin = None

    def navigation():
        nonlocal session, health, origin
        context.check()
        state = context.player.navigation(terrain=True) if goal.terrain else context.player.navigation()
        context.check()
        if state.get("profile") != ("stepped_full_blocks_v1" if goal.terrain else "flat_full_blocks_v1") or not state.get("ready"):
            raise SkillStop("blocked", state.get("reason", "navigation_not_ready"))
        if expected_session is not None and state['actor_session'] != expected_session:
            raise SkillStop('blocked', 'actor_session_changed')
        if session is None:
            session, health, origin = state["actor_session"], state["health"], state["position"][:]
        if state["actor_session"] != session:
            raise SkillStop("blocked", "actor_session_changed")
        if state["health"] < health:
            raise SkillStop("blocked", "damage_observed")
        if state.get("on_fire") or state.get("nearby_hostiles"):
            raise SkillStop("blocked", "known_danger_nearby")
        current = next((c for c in state["cells"] if c["position"] == state["current_cell"]), None)
        if current is None or current["hazards"]:
            raise SkillStop("blocked", "unsupported_or_hazardous_ground")
        if not goal.terrain and abs(state["position"][1]-origin[1]) > .2:
            raise SkillStop("blocked", "vertical_route_unsupported")
        if math.dist(state["position"], origin) > 6.:
            raise SkillStop("blocked", "local_activity_radius_exceeded")
        return state

    def observe():
        context.check()
        scene = context.player.observe()
        context.check()
        if scene.get("actor_session") != session:
            raise SkillStop("blocked", "actor_session_changed")
        if not scene.get("in_world") or not scene.get("alive"):
            raise SkillStop("blocked", "not_in_world_or_dead")
        if scene.get("visibility", {}).get("profile") != "sampled_surfaces_v1":
            raise SkillStop("blocked", "visibility_observation_required")
        return scene

    def inventory():
        context.check()
        value = context.player.inventory()
        context.check()
        if value.get("container_open") or not value.get("carried", {"empty": True}).get("empty"):
            raise SkillStop("blocked", "close_container_and_clear_cursor")
        return value

    state = navigation()
    baseline = count_items(inventory())
    attempted = set()
    harvested = []
    while True:
        state = navigation()
        current = count_items(inventory())
        if current-baseline >= goal.count:
            return SkillResult(status="succeeded", reason="wood_collected",
                text="Observed additional vanilla logs in the player inventory.",
                details={"baseline_logs": baseline, "inventory_logs": current, "collected": current-baseline,
                         "requested": goal.count, "mining_targets": harvested})
        scene = observe()
        selected = destination = None
        seen = []  # Bounded diagnostic evidence from this stopped scan, not a world map.
        scan_steps=17 if goal.scan else 1
        scan_origin=scene['yaw']
        for scan in range(scan_steps):
            state = navigation()
            candidates = []
            sampled = observed_blocks(scene, block_ids)
            requested = getattr(goal,'position',None)
            if requested is not None:sampled=[target for target in sampled if target[1]==tuple(requested)]
            seen = sorted(set(seen).union(sampled),
                          key=lambda t: math.dist(state["eye_position"], [v+.5 for v in t[1]]))[:16]
            for target in sampled:
                if target in attempted or math.dist([v+.5 for v in target[1]], origin) > 6.:
                    continue
                standing = _standing(state, target, excavate=getattr(goal,'excavate',False))
                if standing is not None:
                    candidates.append((target[1][1], math.dist(state["position"], standing), target, standing))
            if candidates:
                _, _, selected, destination = min(candidates)
                break
            if not goal.scan or scan == scan_steps-1:
                break
            context.publish({"phase": "scanning", "collected": current-baseline, "scan_step": scan})
            # Four 200 ms native quarter-turns give observations throughout a full sweep
            # without recreating the former fixed eight-degree Python turn rate.
            target_yaw=(scan_origin+90.*(scan//4+1)+180)%360-180
            rotate_view_timed(context,(scene["yaw"],scene["pitch"]),
                              (target_yaw,55. if getattr(goal,"excavate",False) else 0.),session)
            scene = observe()
        if selected is None:
            return SkillResult(status="blocked", reason="no_reachable_exposed_logs",
                text="No exposed log has a supported local flat-ground approach. No unsupported movement attempted.",
                details={"collected": current-baseline, "requested": goal.count,
                         "observed_logs": [{"id": t[0], "position": list(t[1])} for t in seen],
                         "cause": "no_visible_candidate_with_reachable_adjacent_standing_cell",
                         "navigation_profile": state.get("profile"), "local_radius": 6,
                         "tool_substitution_will_not_fix_geometry": True})
        attempted.add(selected)
        motor = FlatMotion()
        while math.dist(state["position"], destination) > (.1 if getattr(goal,"excavate",False) else .25):
            context.publish({"phase": "approaching_log", "target": selected, "collected": current-baseline})
            result = motor.pulse(context, state, destination, "walk", view=(scene["yaw"], scene["pitch"]),
                                 continuous=True, precision_sneak=False, max_ticks=2)
            if result is not None:
                return result
            state, scene = navigation(), observe()
        motor.halt(context)
        context.pause(.2)
        state, scene = navigation(), observe()
        if not mine_observed_target(context,selected,session,navigation,observe,tools=tools,
                                    excavate=getattr(goal,"excavate",False),collected=current-baseline):
            continue
        harvested.append({"id": selected[0], "position": list(selected[1])})
        if getattr(goal,"excavate",False) and selected[1][1] == round(state["position"][1])-1:
            # Observe NEW collision geometry after removal. Never infer solid floor below the block.
            state = navigation()
            hole = tuple(selected[1])
            if hole in _reachable(state, True):
                destination = (hole[0]+.5,hole[1],hole[2]+.5)
                descent = FlatMotion()
                while math.dist(state["position"],destination)>.25:
                    scene=observe()
                    result=descent.pulse(context,state,destination,"walk",view=(scene["yaw"],scene["pitch"]),
                                         precision_sneak=False,max_ticks=1)
                    if result is not None:return result
                    state=navigation()
                descent.halt(context)
                context.pause(.15)
        # A disappeared crosshair target is not a drop or a collected item.
        # Terrain mode permits ONE pickup approach into newly observed safe
        # same-height geometry, never an inferred floor or unsupported descent.
        picked_up = False
        for pickup_pass in range(2 if goal.terrain else 1):
            pickup_deadline = context.clock()+2.
            while context.clock() < pickup_deadline:
                navigation()
                if count_items(inventory()) > current:
                    picked_up = True
                    break
                context.pause(.1)
            if picked_up:break
            if pickup_pass != 0 or not goal.terrain:break
            state = navigation()
            cell = (selected[1][0], round(state['position'][1]), selected[1][2])
            if cell not in _reachable(state, True):break
            from .walking import WalkTo, walk_to
            context.check()
            pickup_result = walk_to(context, WalkTo(x=cell[0]+.5, y=float(cell[1]), z=cell[2]+.5,
                terrain=True, timeout_seconds=goal.timeout_seconds), expected_session=session)
            if pickup_result.status != 'succeeded':return pickup_result
        if picked_up:
            attempted.clear()  # Actual inventory progress, not a movement receipt.
        else:
            after = count_items(inventory())
            return SkillResult(status="blocked", reason="wood_not_collected", text="Target is no longer hit, but expected inventory gain was not observed; no gameplay success claimed.",
                details={"baseline_logs":baseline,"inventory_logs":after,"collected":after-baseline,"requested":goal.count,
                         "mining_targets":harvested,"last_position":navigation()["position"],
                         "cause":"expected_drops_not_in_inventory; pickup access may differ from attack reach; inspect fresh geometry"})


def gather_wood(context: SkillContext, goal: GatherWood) -> SkillResult:
    return _gather(context, goal)


GATHER_WOOD = SkillDefinition("gather_wood",
    "Gather additional vanilla logs from initially observed exposed blocks within a six-block local radius. "
    "Known full-block routes; terrain=True enables observed one-block climbs/descents. No slabs/gaps, leaf clearing, hidden wood search or crafting. "
    "Use native mining and require inventory gain; crouching is not forced. Stops on danger, damage, "
    "replacement actor or uncollected drops. Target checks are best effort, not atomic block guards.",
    GatherWood, gather_wood)
