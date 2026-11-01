"""AP contracts: deterministic planners, NOT live Minecraft acceptance."""
import math
import threading
import unittest
import time
from unittest.mock import patch
from pydantic import ValidationError
from blockwire import BridgeError, CallableBackend, Player
from blockwire.skills import default_registry, run_skill, SkillManager
from blockwire.skills.autopilot import escape_target
from test_approach import ApproachPlayer


class AutoPlayer(ApproachPlayer):
    def __init__(self):
        super().__init__([])
        self.threats = []
        self.hit = None

    def navigation(self):
        state = super().navigation()
        state.update(threat_profile="nearby_hostiles_v1", eye_position=[self.position[0], 65.62, self.position[2]])
        state["nearby_hostiles"] = [dict(t, distance=math.dist(self.position, t["position"]))
                                    for t in self.threats if math.dist(self.position, t["position"]) <= 8]
        return state

    def observe(self):
        scene = super().observe()
        if self.hit:
            scene["target"] = self.hit
        return scene

    def action(self, name, *, actor_session, target_entity_id):
        assert actor_session == self.session
        self.calls.append(("action", name, target_entity_id, self.now))


def threat(kind="minecraft:creeper", position=(2.5, 64., .5), entity_id=1):
    return dict(entity_id=entity_id, type=kind, position=list(position),
                eye_position=[position[0], position[1]+1.6, position[2]], visible=True)


class AutopilotContracts(unittest.TestCase):
    def execute(self, player, **parameters):
        return run_skill(default_registry(), player, "autopilot",
                         {"duration_seconds": 15., "timeout_seconds": 20., **parameters},
                         clock=player.clock, sleeper=player.sleep)

    def test_AP01_explicit_idle_has_no_motion_or_attack_and_finishes_observed_period(self):
        player = AutoPlayer()
        result = self.execute(player)
        self.assertEqual(result.reason, "monitoring_completed")
        self.assertGreaterEqual(player.now, 15)
        self.assertTrue(all(c[0] == "stop" for c in player.calls))
        self.assertEqual(result.cleanup, "released")

    def test_AP02_goal_walk_run_sneak_arrival_and_hole_detour(self):
        for mode, button in [("walk", None), ("run", "sprint"), ("sneak", "sneak")]:
            player = AutoPlayer()
            player.cells.remove((1, 64, 0))
            result = self.execute(player, destination={"x": 3.5, "y": 64., "z": .5}, movement=mode)
            with self.subTest(mode=mode):
                self.assertEqual(result.reason, "arrived")
                self.assertLessEqual(math.dist(player.position, [3.5, 64., .5]), .3)
                drives = [c[1] for c in player.calls if c[0] == "drive"]
                self.assertTrue(drives)
                if button:
                    self.assertTrue(any(button in buttons for buttons in drives))
                else:
                    self.assertTrue(all("sprint" not in buttons for buttons in drives))
                self.assertNotIn((1, 64, 0), player.trace)
                self.assertEqual(player.calls[-1], ("stop",))

    def test_AP03_creeper_opt_in_priority_and_goal_resume(self):
        player = AutoPlayer()
        player.threats = [threat(), threat("minecraft:zombie", position=(2.5, 64., 1.5), entity_id=2)]
        def disappear(state):
            if player.samples >= 8:
                player.threats = []
            return state
        player.transform = disappear
        progress = []
        result = run_skill(default_registry(), player, "autopilot", dict(
            destination={"x": 3.5, "y": 64., "z": .5}, evade_creepers=True, combat="defend",
            duration_seconds=15.), clock=player.clock, sleeper=player.sleep,
            publish=lambda p: progress.append(p["behavior"]))
        self.assertEqual(result.reason, "arrived")
        self.assertEqual(progress[0], "evade_creeper")
        self.assertIn("travel", progress)
        self.assertLess(player.trace[0][0], 1)  # Away from the eastern creeper, not toward the goal.
        self.assertFalse(any(c[0] == "action" for c in player.calls))
        disabled = AutoPlayer()
        disabled.threats = [threat()]
        self.assertEqual(self.execute(disabled).reason, "known_danger_nearby")
        self.assertFalse(disabled.trace)

    def test_AP04_escape_requires_increasing_distance_valid_edge_and_no_hazard(self):
        player = AutoPlayer()
        t = threat()
        state = player.navigation()
        target = escape_target(state, [t])
        self.assertIsNotNone(target)
        self.assertGreater(math.dist(target, t["position"]), math.dist(player.position, t["position"]))
        state["edges"] = []
        self.assertIsNone(escape_target(state, [t]))
        player.hazards = set(player.cells)-{(0, 64, 0)}
        self.assertIsNone(escape_target(player.navigation(), [t]))
        player.threats = [t]
        player.cells = {(0, 64, 0)}
        result = self.execute(player, evade_creepers=True)
        self.assertEqual(result.reason, "no_known_escape_route")
        self.assertFalse(player.trace)

    def test_AP05_defense_only_attacks_selected_native_target_without_pursuit(self):
        player = AutoPlayer()
        player.threats = [threat("minecraft:zombie")]
        player.hit = {"kind": "entity", "id": 1}
        result = self.execute(player)
        self.assertEqual(result.reason, "known_danger_nearby")
        self.assertFalse(any(c[0] == "action" for c in player.calls))
        result = self.execute(player, combat="defend")
        self.assertEqual(result.reason, "monitoring_completed")
        attacks = [c for c in player.calls if c[0] == "action"]
        self.assertTrue(attacks)
        self.assertTrue(all(c[1:3] == ("attack", 1) for c in attacks))
        self.assertTrue(all(b[3]-a[3] >= .6 for a, b in zip(attacks, attacks[1:])))
        self.assertFalse(player.trace)
        for hit in [None, {"kind": "block", "id": 1}, {"kind": "entity", "id": 2}]:
            other = AutoPlayer()
            other.threats, other.hit = player.threats, hit
            self.execute(other, combat="defend")
            self.assertFalse(any(c[0] == "action" for c in other.calls))
        for mob in [threat(), threat("minecraft:zombie", position=(4.5, 64., .5)),
                    dict(threat("minecraft:zombie"), visible=False)]:
            other = AutoPlayer()
            other.threats = [mob]
            self.assertEqual(self.execute(other, combat="defend").status, "blocked")
            self.assertFalse(any(c[0] == "action" for c in other.calls))

    def test_AP06_strict_validation_precedes_all_effects(self):
        for invalid in [dict(evade_creepers=1), dict(combat="attack_all"), dict(movement="fly"),
                        dict(duration_seconds=0.), dict(duration_seconds=math.inf), dict(typo=True),
                        dict(destination={"x": math.nan, "y": 64., "z": .5}),
                        dict(destination={"x": True, "y": 64., "z": .5}),
                        dict(destination={"x": 1., "z": 1.})]:
            player = AutoPlayer()
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.execute(player, **invalid)
            self.assertEqual(player.calls, [])

    def test_AP07_lifecycle_damage_deadline_stuck_cleanup(self):
        def replace_actor(state, player):
            if player.samples > 1:
                player.session = "other"  # Replace the actual fixture actor, not just its reported token.
            return dict(state, actor_session=player.session)
        for expected, transform in [
            ("actor_session_changed", replace_actor),
            ("damage_observed", lambda s, p: dict(s, health=18. if p.samples > 1 else 20.)),
            ("screen_or_pause", lambda s, p: dict(s, ready=False, reason="screen_or_pause")),
            ("unsupported_navigation_profile", lambda s, p: dict(s, profile="other")),
        ]:
            player = AutoPlayer()
            player.transform = lambda s, p=player, f=transform: f(s, p)
            result = self.execute(player, destination={"x": 3.5, "y": 64., "z": .5})
            self.assertEqual(result.reason, expected)
            self.assertEqual(player.calls[-1], ("stop",))
        # The job fence must also protect non-motor behavior; a motor-only fence is insufficient.
        player = AutoPlayer()
        def replace_defender(state, actor):
            state = replace_actor(state, actor)
            if actor.samples > 1:
                actor.threats = [threat("minecraft:zombie")]
                actor.hit = {"kind": "entity", "id": 1}
            return state
        player.transform = lambda state: replace_defender(state, player)
        self.assertEqual(self.execute(player, combat="defend").reason, "actor_session_changed")
        self.assertFalse(any(c[0] == "action" for c in player.calls))
        player = AutoPlayer()
        player.speed = 0
        self.assertEqual(self.execute(player, destination={"x": 3.5, "y": 64., "z": .5}).reason, "stuck")
        self.assertEqual(self.execute(AutoPlayer(), timeout_seconds=.1).status, "timed_out")
        self.assertEqual(self.execute(AutoPlayer(), destination={"x": 3.5, "y": 65., "z": .5}).reason, "vertical_route_unsupported")
        self.assertEqual(self.execute(AutoPlayer(), destination={"x": 65.5, "y": 64., "z": .5}).reason, "target_out_of_range_64_blocks")
        player = AutoPlayer()
        def fail_final_stop():
            player.calls.append(("stop",))
            if len(player.calls) > 1:
                raise BridgeError("fixture")
        player.stop = fail_final_stop
        result = self.execute(player)
        self.assertEqual(result.cleanup, "not_confirmed")
        self.assertEqual(result.reason, "stop_not_confirmed")
        self.assertEqual(result.status, "failed")

    def test_AP08_cancellation_and_no_automatic_reactivation(self):
        player = AutoPlayer()
        event = threading.Event()
        def sleep(seconds):
            player.sleep(seconds)
            event.set()
        result = run_skill(default_registry(), player, "autopilot", {"evade_creepers": True},
                           clock=player.clock, sleeper=sleep, cancel_event=event)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(player.calls[-1], ("stop",))
        manager = SkillManager(default_registry(), player)
        self.assertEqual(manager.cancel(), {"status": "idle"})
        manager.ensure_idle()

    def test_AP10_mcp_background_exclusive_control_status_and_cancel(self):
        try:
            import mcp  # Optional dependency; run in the MCP-enabled host environment.
        except ImportError:
            self.skipTest("MCP not installed")
        from blockwire.mcp_server import create_server
        player = AutoPlayer()
        with patch("blockwire.mcp_server.Bridge.from_env"), patch("blockwire.mcp_server.Player", return_value=player):
            server = create_server()
        def call(name, **arguments):
            return server._tool_manager.get_tool(name).fn(**arguments)
        job = call("autopilot", duration_seconds=10.)
        try:
            self.assertEqual(call("skill_status", job_id=job["id"])["status"], "running")
            with self.assertRaises(RuntimeError):
                call("look", yaw=0., pitch=0.)
            self.assertEqual(call("cancel_skill", job_id=job["id"])["cancellation_requested"], True)
            for _ in range(100):
                status = call("skill_status", job_id=job["id"])
                if status["status"] != "running":
                    break
                time.sleep(.01)
            self.assertEqual(status["status"], "cancelled")
            self.assertEqual(status["result"]["cleanup"], "released")
        finally:
            call("cancel_skill", job_id=job["id"])

    def test_AP11_unknown_threat_profile_fails_closed_and_offcenter_escape_never_approaches(self):
        player = AutoPlayer()
        nav = player.navigation
        player.navigation = lambda: dict(nav(), threat_profile="old")
        self.assertEqual(self.execute(player).reason, "autopilot_observation_required")
        self.assertFalse(player.trace)
        player = AutoPlayer()
        player.position[0] = .2
        player.threats = [threat()]
        result=self.execute(player, evade_creepers=True)
        self.assertEqual(result.reason,"monitoring_completed")
        initial=2.3
        self.assertTrue(player.trace)
        self.assertTrue(all(math.dist([x+.5,64.,z+.5],[2.5,64.,.5])>=initial for x,_,z in player.trace))

    def test_AP12_late_native_session_or_target_rejection_stops_without_retry(self):
        for reason in ["actor_session_changed", "target_entity_changed"]:
            player = AutoPlayer()
            player.threats = [threat("minecraft:zombie")]
            player.hit = {"kind": "entity", "id": 1}
            attempts = []
            def reject(*args, **kwargs):
                attempts.append(kwargs)
                raise BridgeError(reason)
            player.action = reject
            result = self.execute(player, combat="defend")
            self.assertEqual(result.reason, reason)
            self.assertEqual(result.status, "blocked")
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0], {"actor_session": player.session, "target_entity_id": 1})
            self.assertEqual(player.calls[-1], ("stop",))

    def test_AP09_guard_arguments_and_python_convenience(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or {}))
        player.action("attack", actor_session="a", target_entity_id=7)
        self.assertEqual(calls, [{"op": "action", "name": "attack", "actor_session": "a", "target_entity_id": 7}])
        # No world: explicit invocation returns blocked, never implicitly enables anything.
        player = Player(CallableBackend(lambda q: {"profile": "flat_full_blocks_v1", "ready": False,
                                                   "reason": "not_in_world"}))
        self.assertEqual(player.autopilot()["reason"], "not_in_world")


if __name__ == "__main__":
    unittest.main()
