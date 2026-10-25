"""Deterministic skill contracts, NOT Minecraft gameplay evidence."""
import math
import threading
import time
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from blockwire.skills import (SkillDefinition, SkillManager, SkillParameters, SkillRegistry,
                                SkillResult, default_registry, load_selected_plugins, run_skill)
from blockwire.skills.walking import route


class FlatPlayer:
    def __init__(self):
        self.position = [.5, 64., .5]
        self.cells = {(x, 64, z) for x in range(-8, 13) for z in range(-8, 9)}
        self.hazards = set()
        self.session = "actor-a"
        self.health = 20.
        self.now = 0.
        self.calls = []
        self.trace = []
        self.samples = 0
        self.speed = 1.
        self.transform = lambda state: state

    def clock(self): return self.now
    def sleep(self, seconds): self.now += seconds

    def navigation(self):
        self.samples += 1
        current = (math.floor(self.position[0]), 64, math.floor(self.position[2]))
        nodes = sorted(p for p in self.cells if abs(p[0]-current[0]) <= 4 and abs(p[2]-current[2]) <= 4)
        indices = {p: i for i, p in enumerate(nodes)}
        edges = []
        for p, index in indices.items():
            for dx, dz in [(1, 0), (0, 1)]:
                other = (p[0]+dx, 64, p[2]+dz)
                if other in indices:
                    edges.append([index, indices[other]])
        state = dict(profile="flat_full_blocks_v1", ready=True, actor_session=self.session,
                     position=self.position[:], current_cell=list(current), health=self.health,
                     alive=True, on_fire=False, nearby_hostiles=[], current_center_access=True,
                     cells=[{"position": list(p), "hazards": ["known_hazard"] if p in self.hazards else []} for p in nodes],
                     edges=edges)
        return self.transform(state)

    def look(self, yaw, pitch, *, actor_session):
        assert actor_session == self.session
        self.yaw = yaw
        self.calls.append(("look", yaw))

    def drive(self, buttons, ticks, *, wait, actor_session):
        assert actor_session == self.session
        assert ticks <= 3 and not wait
        self.calls.append(("drive", buttons, ticks))
        speed = .065 if "sneak" in buttons else .215
        distance = speed*ticks*self.speed
        candidate = [self.position[0]-math.sin(math.radians(self.yaw))*distance, 64.,
                     self.position[2]+math.cos(math.radians(self.yaw))*distance]
        cell = (math.floor(candidate[0]), 64, math.floor(candidate[2]))
        if cell in self.cells:
            self.position = candidate
        self.trace.append(cell)

    def stop(self): self.calls.append(("stop",))


class SkillContracts(unittest.TestCase):
    def execute(self, player, **arguments):
        parameters = {"x": 3.5, "y": 64., "z": .5, "timeout_seconds": 20., **arguments}
        return run_skill(default_registry(), player, "walk_to", parameters,
                         clock=player.clock, sleeper=player.sleep)

    def test_flat_arrival_is_observed_and_releases(self):
        player = FlatPlayer()
        result = self.execute(player)
        self.assertEqual(result.status, "succeeded")
        self.assertLessEqual(math.dist(player.position, [3.5, 64, .5]), .3)
        self.assertEqual(player.calls[-1], ("stop",))
        self.assertEqual(result.cleanup, "released")
        self.assertTrue(all("sneak" in call[1] for call in player.calls if call[0] == "drive"))

    def test_non_center_initial_position_and_non_center_goal(self):
        player = FlatPlayer()
        player.position = [.15, 64., .2]
        result = self.execute(player, x=3.15, z=.25)
        self.assertEqual(result.status, "succeeded")

    def test_detour_around_collision_obstacle_without_corner_cutting(self):
        player = FlatPlayer()
        blocked = (1, 64, 0)
        player.cells.remove(blocked)
        result = self.execute(player)
        self.assertEqual(result.status, "succeeded")
        self.assertNotIn(blocked, player.trace)
        self.assertTrue(any(cell[2] != 0 for cell in player.trace))

    def test_hazard_detour_and_opt_out(self):
        player = FlatPlayer()
        hazard = (1, 64, 0)
        player.hazards.add(hazard)
        self.assertEqual(self.execute(player).status, "succeeded")
        self.assertNotIn(hazard, player.trace)
        opt_out = FlatPlayer()
        opt_out.hazards.add(hazard)
        self.assertEqual(self.execute(opt_out, avoid_damage=False).status, "succeeded")
        self.assertIn(hazard, opt_out.trace)

    def test_current_hazard_does_not_claim_arrival(self):
        player = FlatPlayer()
        player.hazards.add((0, 64, 0))
        result = self.execute(player, x=.5)
        self.assertEqual(result.reason, "known_danger_nearby")
        self.assertFalse(any(call[0] == "drive" for call in player.calls))

    def test_hole_and_unknown_ground_are_not_invented(self):
        player = FlatPlayer()
        player.cells = {(0, 64, 0), (2, 64, 0)}
        result = self.execute(player, x=2.5)
        self.assertEqual(result.reason, "no_known_safe_route")
        self.assertFalse(player.trace)

    def test_stuck_and_timeout(self):
        player = FlatPlayer()
        player.speed = 0
        self.assertEqual(self.execute(player).reason, "stuck")
        limited = FlatPlayer()
        limited.speed = 0
        self.assertEqual(self.execute(limited, timeout_seconds=.1).status, "timed_out")

    def test_session_replacement_stops_before_new_actor_input(self):
        player = FlatPlayer()
        def replace(state):
            if player.samples == 2:
                player.session = state["actor_session"] = "actor-b"
            return state
        player.transform = replace
        result = self.execute(player)
        self.assertEqual(result.reason, "actor_session_changed")
        self.assertEqual(len([c for c in player.calls if c[0] == "drive"]), 1)

    def test_damage_hostile_screen_vertical_and_range_guards(self):
        for reason, transform in [
            ("damage_observed", lambda s, p: dict(s, health=18. if p.samples > 1 else 20.)),
            ("known_danger_nearby", lambda s, p: dict(s, nearby_hostiles=[{"entity_id": 1}])),
            ("screen_or_pause", lambda s, p: dict(s, ready=False, reason="screen_or_pause")),
        ]:
            player = FlatPlayer()
            player.transform = lambda s, p=player, f=transform: f(s, p)
            with self.subTest(reason=reason):
                self.assertEqual(self.execute(player).reason, reason)
                self.assertEqual(player.calls[-1], ("stop",))
        self.assertEqual(self.execute(FlatPlayer(), y=65.).reason, "vertical_route_unsupported")
        self.assertEqual(self.execute(FlatPlayer(), x=65.5).reason, "target_out_of_range_64_blocks")

    def test_strict_invalid_parameters_have_no_actions_or_cleanup(self):
        for invalid in [dict(x=math.nan), dict(x=True), dict(sneak=1), dict(avoid_damage="true"),
                        dict(timeout_seconds=121.), dict(typo=True)]:
            player = FlatPlayer()
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.execute(player, **invalid)
            self.assertEqual(player.calls, [])

    def test_pre_cancel_and_unexpected_failure_release(self):
        player = FlatPlayer()
        event = threading.Event()
        event.set()
        result = run_skill(default_registry(), player, "walk_to", dict(x=1., y=64., z=1.), cancel_event=event)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(player.calls, [("stop",)])
        broken = FlatPlayer()
        broken.navigation = lambda: (_ for _ in ()).throw(RuntimeError("fixture"))
        self.assertEqual(self.execute(broken).status, "failed")
        self.assertEqual(broken.calls[-1], ("stop",))

    def test_registry_descriptor_duplicates_and_explicit_plugin_loading(self):
        registry = default_registry()
        descriptor = registry.describe()[0]
        self.assertEqual(descriptor["name"], "walk_to")
        self.assertFalse(descriptor["parameters"]["additionalProperties"])
        with self.assertRaises(ValueError):
            registry.register(next(iter(registry._definitions.values())))
        with patch("blockwire.skills.core.entry_points") as installed:
            installed.return_value = []
            load_selected_plugins(registry, "")
            with self.assertRaises(ValueError):
                load_selected_plugins(registry, "not_installed")
        self.assertEqual(len(registry.describe()), 1)

    def test_read_only_extension_contract(self):
        registry = SkillRegistry()
        registry.register(SkillDefinition("fixture", "Read-only test", SkillParameters,
            lambda ctx, args: SkillResult(status="succeeded", reason="read", text="observed"), controls_player=False))
        player = FlatPlayer()
        self.assertEqual(run_skill(registry, player, "fixture", {}).cleanup, "not_required")
        self.assertEqual(player.calls, [])

    def test_background_job_status_cancel_and_exclusive_control(self):
        def loop(context, parameters):
            while True:
                context.publish({"waiting": True})
                context.pause(.05)
        registry = SkillRegistry()
        registry.register(SkillDefinition("waiting", "Cancellation fixture", SkillParameters, loop))
        player = FlatPlayer()
        manager = SkillManager(registry, player)
        started = manager.start("waiting", {})
        self.assertEqual(manager.status(started["id"])["status"], "running")
        with self.assertRaises(RuntimeError):
            manager.start("waiting", {})
        manager.cancel(started["id"])
        for _ in range(100):
            result = manager.status(started["id"])
            if result["status"] != "running":
                break
            time.sleep(.01)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["result"]["cleanup"], "released")
        manager.ensure_idle()


if __name__ == "__main__":
    unittest.main()
