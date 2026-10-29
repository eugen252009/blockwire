"""Small opt-in combat policy. Native Minecraft owns hits, cooldowns, damage and collision."""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Literal
from pydantic import BaseModel, Field
from .core import SkillContext, SkillDefinition, SkillParameters, SkillResult, SkillStop
from .autopilot import escape_target
from .motion import FlatMotion

Response = Literal["fight", "evade", "ignore"]
MOB_KEYS = {"minecraft:zombie": "zombies", "minecraft:skeleton": "skeletons",
            "minecraft:spider": "spiders", "minecraft:creeper": "creeper"}
WEAPONS = {f"minecraft:{material}_{kind}": (.7 if kind == "sword" else 1.3)
           for material in ["wooden", "stone", "copper", "iron", "golden", "diamond", "netherite"]
           for kind in ["sword", "axe"]}


AIM_REFRESH_SECONDS = .08


class Reactions(BaseModel):
    model_config = SkillParameters.model_config
    zombies: Response = "fight"
    skeletons: Response = "fight"
    spiders: Response = "fight"
    creeper: Response = "evade"


class Fight(SkillParameters):
    reactions: Reactions = Field(default_factory=Reactions)
    duration_seconds: float = Field(default=20., ge=.1, le=120)
    min_health: float = Field(default=8., ge=1., le=20., description="Stop attacking at/below this observed HP.")
    radius: float = Field(default=8., ge=1., le=8., description="Observed activation displacement and target radius.")
    pursue: bool = True
    allow_unarmed: bool = False
    melee_wait_seconds: float = Field(default=3., ge=0., le=5.,
        description="Bounded stationary wait for melee reach, target level or visibility; zero keeps immediate blocking.")


def fight(context: SkillContext, goal: Fight) -> SkillResult:
    started, session, initial = context.clock(), None, None
    # The same deadline also reaches nested motor look/drive checks, not just this loop.
    context = replace(context, deadline=min(context.deadline, started+goal.duration_seconds))
    motion, behavior, air_since = FlatMotion(), None, None
    last_attack, previous_interval, attacks = -math.inf, 0., 0
    back_off = False
    cooldown, reach_wait_started = None, None

    def blocked(reason):
        return SkillResult(status="blocked", reason=reason, text="Fight stopped: "+reason.replace("_", " "),
                           details={"attacks_submitted": attacks, "kills_confirmed": None})

    def sample():
        nonlocal session, initial
        context.check()
        state = context.player.navigation()
        context.check()
        if state.get("profile") != "flat_full_blocks_v1":
            raise SkillStop("blocked", "unsupported_navigation_profile")
        if not state.get("ready") and state.get("reason") != "not_grounded":
            raise SkillStop("blocked", state.get("reason", "navigation_not_ready"))
        if session is None:
            session = state["actor_session"]
            initial = state.get("position")
        if state["actor_session"] != session:
            raise SkillStop("blocked", "actor_session_changed")
        if state.get("position") is not None and initial is not None:
            if math.hypot(state["position"][0]-initial[0], state["position"][2]-initial[2]) > goal.radius:
                raise SkillStop("blocked", "activity_radius_exceeded")
        if state.get("on_fire"):
            raise SkillStop("blocked", "on_fire")
        if not state.get("ready"):
            if state.get("reason") != "not_grounded":
                raise SkillStop("blocked", state.get("reason", "navigation_not_ready"))
            return state
        if state.get("threat_profile") != "nearby_hostiles_v1":
            raise SkillStop("blocked", "fight_observation_required")
        if initial is None:
            raise SkillStop("blocked", "navigation_not_ready")
        if abs(state["position"][1]-initial[1]) > .2:
            raise SkillStop("blocked", "vertical_route_unsupported")
        current = next((c for c in state["cells"] if c["position"] == state["current_cell"]), None)
        if current is None or current["hazards"]:
            raise SkillStop("blocked", "unsafe_current_cell")
        return state

    def selected(state):
        threats = state["nearby_hostiles"]
        if any(t["type"] not in MOB_KEYS for t in threats):
            raise SkillStop("blocked", "unsupported_hostile_nearby")
        relevant = [t for t in threats if t["distance"] <= goal.radius and
                    getattr(goal.reactions, MOB_KEYS[t["type"]]) != "ignore"]
        return threats, relevant

    def transition(next_behavior):
        nonlocal behavior, motion
        if behavior != next_behavior:
            context.check()
            context.player.stop()
            motion, behavior = FlatMotion(), next_behavior

    def report(state, enemy, reason, **extra):
        context.publish({"behavior": behavior, "entity_id": enemy["entity_id"], "type": enemy["type"],
                         "health": state["health"], "attacks_submitted": attacks,
                         "attack_wait_reason": reason, **extra})

    def wait_for_melee(state, enemy, reason):
        nonlocal reach_wait_started
        transition("wait_for_melee")  # Release motion; never project an unsupported vertical route.
        if reach_wait_started is None:
            reach_wait_started = context.clock()
        remaining = goal.melee_wait_seconds-(context.clock()-reach_wait_started)
        if remaining <= 0:
            return False
        report(state, enemy, reason, melee_wait_remaining=remaining)
        context.pause(min(.1, max(.01, remaining)))  # Avoid sub-ULP waits on injected clocks.
        return True

    def retreat(state, threats):
        nonlocal reach_wait_started
        reach_wait_started = None
        target = escape_target(state, threats)
        if target is None:
            return blocked("no_known_escape_route")
        if math.hypot(target[0]-initial[0], target[2]-initial[2]) > goal.radius:
            return blocked("activity_radius_exceeded")
        transition("evade")
        context.publish({"behavior": "evade", "position": state["position"], "health": state["health"],
                         "attacks_submitted": attacks})
        return motion.pulse(context, state, target, "run", threats)

    def interval():
        context.check()
        inventory = context.player.inventory()
        context.check()
        held = next((i for i in inventory["items"] if i["inventory_index"] == inventory["selected_hotbar"]), None)
        if held is None:
            return .5 if goal.allow_unarmed else None
        item = held["item"]
        if item not in WEAPONS or held.get("damage", 0) >= held.get("max_damage", math.inf)-1:
            return None
        return WEAPONS[item]

    while True:
        context.check()
        state = sample()
        if state.get("on_fire"):
            return blocked("on_fire")
        low_health = state.get("health", 0.) <= goal.min_health
        if not state.get("ready"):
            if low_health:
                return blocked("low_health")
            transition("recover_grounding")
            air_since = context.clock() if air_since is None else air_since
            if context.clock()-air_since >= 1.5:
                return blocked("not_grounded")
            if context.clock()-started >= goal.duration_seconds:
                return SkillResult(status="timed_out", reason="active_period_elapsed", text="Fight period elapsed; no kill claimed.")
            context.publish({"behavior": "recover_grounding", "health": state["health"],
                             "attacks_submitted": attacks, "attack_wait_reason": "not_grounded"})
            context.pause(.05)
            continue
        air_since = None
        threats, relevant = selected(state)
        if context.clock()-started >= goal.duration_seconds:
            return SkillResult(status="timed_out", reason="active_period_elapsed", text="Fight period elapsed; no kill claimed.",
                               details={"attacks_submitted": attacks, "kills_confirmed": None})
        if low_health:
            if threats:
                result = retreat(state, threats)  # One bounded, known escape pulse, then terminate.
                if result:
                    return result
            return blocked("low_health")
        if not relevant:
            return SkillResult(status="succeeded", reason="no_selected_enemies_observed",
                text="Selected enemies are absent from bounded observations; kills are not established.",
                details={"attacks_submitted": attacks, "kills_confirmed": None})
        evaders = [t for t in relevant if getattr(goal.reactions, MOB_KEYS[t["type"]]) == "evade"]
        creepers = [t for t in relevant if t["type"] == "minecraft:creeper"]
        if back_off and not any(t["distance"] < 4. for t in creepers):
            back_off = False
        if evaders or (back_off and creepers) or any(t["distance"] < 1.5 for t in creepers):
            result = retreat(state, threats)
            if result:
                return result
            continue
        enemies = [t for t in relevant if t["visible"] and getattr(goal.reactions, MOB_KEYS[t["type"]]) == "fight"]
        if not enemies:
            # Still client-known and policy-selected, but not currently visible: no aim, move or attack.
            hidden = min(relevant, key=lambda t: t["distance"])
            if wait_for_melee(state, hidden, "no_visible_selected_enemy"):
                continue
            return blocked("no_visible_selected_enemy")
        enemy = min(enemies, key=lambda t: (0 if t["type"] == "minecraft:creeper" and t["distance"] <= 4 else 1, t["distance"]))
        # Initial gate is retained. Only cache scheduling information, never attack authorization.
        if cooldown is None or enemy["type"] == "minecraft:creeper":
            cooldown = interval()
            if cooldown is None:
                return blocked("select_usable_hotbar_weapon")
        if enemy["distance"] > 2.8:
            if enemy["type"] == "minecraft:creeper":
                transition("creeper_standoff")  # Never deliberately chase a creeper.
                reach_wait_started = None
                report(state, enemy, "creeper_standoff")
                context.pause(.1)
                continue
            wait_reason = ("enemy_out_of_reach" if not goal.pursue else
                           "enemy_on_other_level" if abs(enemy["position"][1]-state["position"][1]) > .2 else None)
            if wait_reason:
                if wait_for_melee(state, enemy, wait_reason):
                    continue
                return blocked(wait_reason)
            reach_wait_started = None
            transition("approach_enemy")
            cooldown = interval()  # Fresh equipment check before every movement pulse.
            if cooldown is None:
                return blocked("select_usable_hotbar_weapon")
            context.publish({"behavior": "approach_enemy", "entity_id": enemy["entity_id"],
                             "type": enemy["type"], "health": state["health"], "attacks_submitted": attacks})
            result = motion.pulse(context, state, enemy["position"], "walk")
            if result:
                return result
            continue
        reach_wait_started = None
        if enemy["type"] == "minecraft:creeper" and context.clock()-last_attack < max(cooldown, previous_interval):
            result = retreat(state, threats)
            if result:
                return result
            continue
        if enemy["type"] == "minecraft:creeper" and escape_target(state, threats) is None:
            return blocked("no_known_escape_route")
        transition("attack")
        # Prepare the rendered aim near cooldown end, but authorize only with the final fresh interval.
        # A 5 ms margin avoids sub-ULP boundary retries on deterministic clocks.
        cooldown_remaining = max(cooldown, previous_interval)-(context.clock()-last_attack)
        remaining = cooldown_remaining-(AIM_REFRESH_SECONDS-.005)
        if remaining > 0:
            report(state, enemy, "cooldown", cooldown_remaining=cooldown_remaining)
            context.pause(min(.1, max(.01, remaining)))
            continue  # Still sample health/policy/session, but don't re-aim/read inventory while cooling down.
        report(state, enemy, "aim_refresh")
        eye, aim = state["eye_position"], enemy["eye_position"]
        dx, dy, dz = (aim[i]-eye[i] for i in range(3))
        context.check()
        context.player.look(math.degrees(math.atan2(-dx, dz)),
                            -math.degrees(math.atan2(dy, math.hypot(dx, dz))), actor_session=session)
        context.pause(AIM_REFRESH_SECONDS)
        fresh = sample()
        if not fresh.get("ready"):
            continue
        if fresh["health"] <= goal.min_health:
            continue
        _, current = selected(fresh)
        target = next((t for t in current if t["entity_id"] == enemy["entity_id"] and t["type"] == enemy["type"]
                       and t["visible"] and t["distance"] <= 3), None)
        if any(getattr(goal.reactions, MOB_KEYS[t["type"]]) == "evade" or
               (t["type"] == "minecraft:creeper" and t["distance"] < 1.5) for t in current):
            continue
        context.check()
        scene = context.player.observe()
        context.check()
        if not scene.get("in_world") or not scene.get("alive") or scene.get("health", fresh["health"]) <= goal.min_health:
            continue
        hit = scene.get("target") or {}
        cooldown = interval()
        if cooldown is None:
            return blocked("select_usable_hotbar_weapon")
        remaining = max(cooldown, previous_interval)-(context.clock()-last_attack)
        if (target is not None and hit.get("kind") == "entity" and hit.get("id") == target["entity_id"]
                and remaining <= 0):
            if context.clock()-started >= goal.duration_seconds:
                continue
            context.check()
            context.player.action("attack", actor_session=session, target_entity_id=target["entity_id"])
            last_attack, previous_interval = context.clock(), cooldown
            attacks += 1  # Receipt count, NOT damage/kill count.
            if target["type"] == "minecraft:creeper":
                back_off = True
            report(fresh, enemy, "submitted")  # Preserve receipt count even if the next pause is cancelled.
        else:
            reason = "target_not_confirmed" if target is None else (
                "crosshair_mismatch" if hit.get("kind") != "entity" or hit.get("id") != target["entity_id"] else "cooldown")
            report(fresh, enemy, reason, crosshair_entity_id=hit.get("id") if hit.get("kind") == "entity" else None,
                   cooldown_remaining=max(0., remaining))
        context.pause(.1)


FIGHT = SkillDefinition("fight",
    "Explicit bounded combat against zombies, skeletons, spiders and creepers with per-mob fight/evade/ignore policies. "
    "Evade wins. Uses selected vanilla sword/axe (unarmed only by opt-in), guarded native attacks and short flat-ground pursuit. "
    "Bounded stationary waits retain the job/cooldown after knockback, target height or temporary visibility loss; no blind attacks or vertical movement. "
    "Low health terminates after at most one safe retreat pulse. Creeper fighting hits then backs off; no fuse prediction or immunity. "
    "Success means selected enemies absent from bounded observations, NEVER confirmed kills. Cancel releases controls.", Fight, fight)
