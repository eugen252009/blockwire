"""AR contracts on deterministic fixtures. NOT native Minecraft gameplay acceptance."""
import contextlib
import io
import math
import sys
import threading
import time
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from blockwire import BridgeError, CallableBackend, Player
from blockwire.skills import Approach, SkillContext, default_registry, run_skill
from blockwire.skills.motion import travel_inputs,rotate_view_timed,_yaw_delta
from test_skills import FlatPlayer


def target(x=7, y=64, z=0, block_id="minecraft:chest"):
    return {"id": block_id, "position": [x, y, z], "aim_position": [x+.5, y+.5, z+.5], "kind": "container"}


class ApproachPlayer(FlatPlayer):
    def __init__(self, targets=None):
        super().__init__()
        self.targets = [target()] if targets is None else targets
        for row in self.targets:
            self.cells.discard(tuple(row["position"]))
        self.yaw, self.pitch = -90., 0.
        self.scene_transform = lambda s: s
        self.on_drive = lambda: None
        self.native_override = False
        self.observations = 0
        self.view_trace = []
        self.rotation_request_trace = []
        self.drive_trace = []
        self.scene_records = []
        self.events = []
        self.held = ()
        self.lease_until = 0.
        self.button_deadlines = {}
        self._lease_session = self.session
        self._physics_time = self.now
        self.rpc_latency = 0.

    def _advance(self):
        # Time/lease-based fixture: a renewal does NOT instantly move for its whole duration.
        while self._physics_time < self.now-1e-10:
            if self._lease_session != self.session or self.health <= 0:
                self.held = ()
            self.held=tuple(key for key in self.held if self._physics_time<self.button_deadlines.get(key,self.lease_until)-1e-10)
            if not self.held or self._physics_time >= self.lease_until-1e-10:
                if self.held:
                    self.events.append({"kind": "expiry", "time": self.lease_until})
                self.held = ()
                self._physics_time = self.now
                break
            end = min(self.now, self.lease_until, self._physics_time+.05,
                      min(self.button_deadlines.get(key,self.lease_until) for key in self.held))
            self._update_rotation(end)
            forward = int("forward" in self.held)-int("back" in self.held)
            right = int("right" in self.held)-int("left" in self.held)
            length = max(1., math.hypot(forward, right))
            forward, right = forward/length, right/length
            yaw = math.radians(self.yaw)
            speed = .065 if "sneak" in self.held else .215*(1.3 if "sprint" in self.held else 1.)
            distance = speed*(end-self._physics_time)/.05*self.speed
            candidate = [self.position[0]+(-math.sin(yaw)*forward-math.cos(yaw)*right)*distance, self.position[1],
                         self.position[2]+(math.cos(yaw)*forward-math.sin(yaw)*right)*distance]
            cell = tuple(math.floor(v) for v in candidate)
            if cell in self.cells:
                self.position = candidate
            self.trace.append(cell)
            self._physics_time = end
        if self.held and self.now >= self.lease_until-1e-10:
            self.events.append({"kind": "expiry", "time": self.lease_until})
            self.held = ()

    def sleep(self, seconds):
        self.now += seconds
        self._advance();self._update_rotation()

    def _event(self, kind):
        self._advance()
        self.events.append({"kind": kind, "time": self.now, "held": self.held, "position": self.position[:],
                            "yaw": self.yaw, "pitch": self.pitch})
        if self.rpc_latency:
            self.sleep(self.rpc_latency)

    def stop(self):
        self._event("stop")
        self.calls.append(("stop",))
        self.held = ();self.rotation=None
        self.button_deadlines={}
        self.lease_until = self.now

    def navigation(self):
        self._event("navigation")
        state = super().navigation()
        state['sneaking']='sneak' in self.held
        state["eye_position"] = [self.position[0], self.position[1]+(1.27 if state['sneaking'] else 1.62), self.position[2]]
        return state

    def look(self, yaw, pitch, *, actor_session, duration_ms=None, rotation_profile=None):
        self._event("look")
        super().look(yaw, pitch, actor_session=actor_session,duration_ms=duration_ms,rotation_profile=rotation_profile)
        self.pitch = pitch
        self.view_trace.append((yaw, pitch));self.rotation_request_trace.append(
            {'yaw':yaw,'pitch':pitch,'duration_ms':duration_ms,'rotation_profile':rotation_profile,'time':self.now})

    def drive(self, buttons, ticks, *, wait, actor_session, button_ticks=None):
        assert actor_session == self.session
        assert 1 <= ticks <= 100 and not wait  # Native API bound; controller policy has separate assertions.
        self._event("drive")
        self.calls.append(("drive", buttons, ticks))
        self.drive_trace.append({"buttons": buttons[:], "ticks": ticks, "position": self.position[:],
                                 "yaw": self.yaw, "pitch": self.pitch, "time": self.now, "previously_held": self.held})
        self.held = tuple(buttons)
        self.button_deadlines={key:self.now+(button_ticks.get(key,ticks) if button_ticks is not None else ticks)*.05 for key in buttons}
        self.lease_until = self.now+ticks*.05
        self._lease_session = actor_session
        self.on_drive()

    def observe(self):
        self._event("observe")
        self.observations += 1
        eye = [self.position[0], self.position[1]+1.62, self.position[2]]
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        view = [-math.sin(yaw)*math.cos(pitch), -math.sin(pitch), math.cos(yaw)*math.cos(pitch)]
        visible, hits = [], []
        for row in self.targets:
            delta = [row["aim_position"][i]-eye[i] for i in range(3)]
            length = math.dist(eye, row["aim_position"])
            if length <= 64 and sum(delta[i]*view[i] for i in range(3))/length >= .5:
                visible.append(dict(row, distance=length))
            # Independent slab-ray fixture for a chest's outline, limited to vanilla interaction range.
            low, high = 0., 4.5
            for i in range(3):
                a = row["position"][i]+(.0625 if i != 1 else 0)
                b = row["position"][i]+(.9375 if i != 1 else .875)
                if abs(view[i]) < 1e-10:
                    if not a <= eye[i] <= b:
                        high = -1.
                else:
                    t1, t2 = (a-eye[i])/view[i], (b-eye[i])/view[i]
                    low, high = max(low, min(t1, t2)), min(high, max(t1, t2))
            if low <= high:
                hits.append((low, row))
        scene = {"in_world": True, "alive": True, "position": self.position[:], "eye_position": eye,
                 "yaw": self.yaw, "pitch": self.pitch,
                 "visibility": {"profile": "sampled_surfaces_v1"}, "visible_interactables": visible}
        if hits:
            hit = min(hits, key=lambda h: h[0])[1]
            scene["target"] = {"kind": "block", "id": hit["id"], "position": hit["position"][:]}
            scene["sight_target"] = {"id": hit["id"], "position": hit["position"][:]}
        if self.native_override is not False:
            scene["target"] = self.native_override
        scene = self.scene_transform(scene)
        self.scene_records.append({"position": self.position[:], "yaw": self.yaw, "pitch": self.pitch,
            "visible": [r["position"] for r in scene["visible_interactables"]], "drives": len(self.drive_trace)})
        return scene

    def action(self, *args, **kwargs):
        raise AssertionError("Approach must NEVER use, attack, open a menu or transfer items")


class ApproachContracts(unittest.TestCase):
    def execute(self, player, **parameters):
        return run_skill(default_registry(), player, "approach", {"timeout_seconds": 25., **parameters},
                         clock=player.clock, sleeper=player.sleep)

    def test_AR01_distant_visible_chest_frontier_arrival_aim_and_no_use(self):
        player = ApproachPlayer()
        progress = []
        result = run_skill(default_registry(), player, "approach", {"target": "chest", "timeout_seconds": 25.},
                           clock=player.clock, sleeper=player.sleep, publish=progress.append)
        self.assertEqual(result.reason, "ready_to_interact")
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.details["native_target"], {"kind": "block", "id": "minecraft:chest", "position": [7, 64, 0]})
        self.assertEqual(result.details["target"]["position"], [7, 64, 0])
        self.assertNotIn((7, 64, 0), player.trace)
        self.assertTrue(any(p["route_is_partial"] for p in progress))
        self.assertGreater(player.observations, 2)
        self.assertTrue(any("sneak" not in c[1] for c in player.calls if c[0] == "drive"))
        self.assertTrue(all(set(c[1]) <= {"forward", "back", "left", "right", "sneak"}
                            for c in player.calls if c[0] == "drive"))
        self.assertEqual(player.calls[-1], ("stop",))
        self.assertEqual(result.cleanup, "released")

    def test_AR02_nearest_locally_reachable_and_explicit_visible_position(self):
        near, far = target(4), target(6, z=3)
        player = ApproachPlayer([near, far])
        self.assertEqual(self.execute(player).details["target"]["position"], near["position"])
        player = ApproachPlayer([near, far])
        self.assertEqual(self.execute(player, position=far["position"]).details["target"]["position"], far["position"])
        player = ApproachPlayer([target(0, z=4), target(7)])
        player.yaw = -45.
        player.cells = {(x, 64, 0) for x in range(7)}
        result = self.execute(player)
        self.assertEqual(result.reason, "ready_to_interact")
        self.assertEqual(result.details["target"]["position"], [7, 64, 0])

    def test_AR03_no_target_hidden_override_old_observation_and_no_route(self):
        for player, params, expected in [
            (ApproachPlayer([]), {}, "target_not_visible"),
            (ApproachPlayer(), {"position": [20, 64, 0]}, "target_not_visible"),
            (ApproachPlayer(), {"target": "barrel"}, "target_not_visible"),
        ]:
            self.assertEqual(self.execute(player, **params).reason, expected)
            self.assertFalse(player.trace)
        player = ApproachPlayer()
        player.scene_transform = lambda s: dict(s, visibility={})
        self.assertEqual(self.execute(player).reason, "visibility_observation_required")
        self.assertFalse(player.trace)
        player = ApproachPlayer()
        player.cells = {(0, 64, 0)}
        self.assertEqual(self.execute(player).reason, "no_known_approach_route")
        self.assertFalse(player.trace)

    def test_AR04_reobserve_target_loss_replacement_and_no_silent_retarget(self):
        for replacement in [[], [target(block_id="minecraft:barrel")], [target(9, z=2)]]:
            player = ApproachPlayer()
            player.on_drive = lambda p=player, rows=replacement: setattr(p, "targets", rows)
            result = self.execute(player)
            self.assertEqual(result.reason, "target_lost")
            self.assertEqual(len([c for c in player.calls if c[0] == "drive"]), 1)
            self.assertEqual(player.calls[-1], ("stop",))

    def test_AR05_native_crosshair_postcondition_not_distance_or_receipt(self):
        for hit in [{}, {"kind": "block", "id": "minecraft:chest", "position": [8, 64, 0]},
                    {"kind": "block", "id": "minecraft:barrel", "position": [7, 64, 0]}]:
            player = ApproachPlayer()
            player.native_override = hit
            result = self.execute(player)
            self.assertEqual(result.reason, "native_target_not_acquired")
            self.assertEqual(result.status, "blocked")
            self.assertEqual(player.calls[-1], ("stop",))

    def test_AR06_validation_has_no_observations_or_control_effects(self):
        for invalid in [{"target": ""}, {"target": "chest; use"}, {"target": 1},
                        {"position": [1, 64]}, {"position": [1., 64, 0]}, {"position": [True, 64, 0]},
                        {"position": [math.nan, 64, 0]}, {"position": [30_000_000, 64, 0]},
                        {"sneak": 1}, {"avoid_damage": "true"}, {"timeout_seconds": 121.}, {"typo": True}]:
            player = ApproachPlayer()
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.execute(player, **invalid)
            self.assertEqual(player.calls, [])
            self.assertEqual(player.samples, 0)
            self.assertEqual(player.observations, 0)

    def test_AR07_actor_replacement_before_discovery_and_after_drive(self):
        player = ApproachPlayer()
        def replace(scene):
            player.session = "replacement"
            return scene
        player.scene_transform = replace
        self.assertEqual(self.execute(player).reason, "actor_session_changed")
        self.assertEqual(player.calls, [("stop",)])
        player = ApproachPlayer()
        player.on_drive = lambda: setattr(player, "session", "replacement")
        self.assertEqual(self.execute(player).reason, "actor_session_changed")
        self.assertEqual(len([c for c in player.calls if c[0] == "drive"]), 1)
        self.assertEqual(player.calls[-1], ("stop",))

    def test_AR08_damage_known_hazards_stuck_and_mesh_detour(self):
        player = ApproachPlayer()
        player.on_drive = lambda: setattr(player, "health", 18.)
        self.assertEqual(self.execute(player).reason, "damage_observed")
        player = ApproachPlayer()
        player.cells = {(x, 64, 0) for x in range(7)}
        player.hazards = {(1, 64, 0)}
        self.assertEqual(self.execute(player).reason, "no_known_approach_route")
        self.assertEqual(self.execute(player, avoid_damage=False).reason, "ready_to_interact")
        player = ApproachPlayer()
        player.speed = 0
        self.assertEqual(self.execute(player).reason, "stuck")
        player = ApproachPlayer()
        player.cells.remove((1, 64, 0))
        self.assertEqual(self.execute(player).reason, "ready_to_interact")
        self.assertNotIn((1, 64, 0), player.trace)
        self.assertTrue(any(c[2] != 0 for c in player.trace))

    def test_AR09_deadline_cancellation_and_cleanup_failure(self):
        player = ApproachPlayer()
        self.assertEqual(self.execute(player, timeout_seconds=.1).status, "timed_out")
        player = ApproachPlayer()
        event = threading.Event()
        result = run_skill(default_registry(), player, "approach", {}, cancel_event=event,
            clock=player.clock, sleeper=player.sleep, publish=lambda _: event.set())
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(player.calls, [("stop",)])
        player = ApproachPlayer([target(2)])
        stops = []
        def fail_final_stop():
            stops.append(1)
            if len(stops) > 1:
                raise BridgeError("fixture")
        player.stop = fail_final_stop
        result = self.execute(player)
        self.assertEqual(result.reason, "stop_not_confirmed")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.cleanup, "not_confirmed")

    def test_AR10_mcp_background_exclusivity_and_cancellation(self):
        try:
            import mcp
        except ImportError:
            self.skipTest("MCP not installed")
        from blockwire.mcp_server import create_server
        player = ApproachPlayer()
        with patch("blockwire.mcp_server.Bridge.from_env"), patch("blockwire.mcp_server.Player", return_value=player):
            server = create_server()
        def call(name, **arguments):
            return server._tool_manager.get_tool(name).fn(**arguments)
        job = call("approach", target="chest")
        try:
            self.assertEqual(call("skill_status", job_id=job["id"])["status"], "running")
            with self.assertRaises(RuntimeError):
                call("look", yaw=0., pitch=0.)
            self.assertTrue(call("describe_surroundings")["in_world"])
            call("cancel_skill", job_id=job["id"])
            for _ in range(100):
                status = call("skill_status", job_id=job["id"])
                if status["status"] != "running":
                    break
                time.sleep(.01)
            self.assertEqual(status["status"], "cancelled")
            self.assertEqual(status["result"]["cleanup"], "released")
        finally:
            call("cancel_skill", job_id=job["id"])

    def test_AR12_readiness_danger_vertical_and_pre_cancel_guards(self):
        for reason, transform in [
            ("screen_or_pause", lambda s: dict(s, ready=False, reason="screen_or_pause")),
            ("player_dead", lambda s: dict(s, ready=False, reason="player_dead")),
            ("not_grounded", lambda s: dict(s, ready=False, reason="not_grounded")),
            ("unsupported_navigation_profile", lambda s: dict(s, profile="other")),
            ("known_danger_nearby", lambda s: dict(s, nearby_hostiles=[{"entity_id": 1}])),
            ("known_danger_nearby", lambda s: dict(s, on_fire=True)),
            ("current_cell_center_obstructed", lambda s: dict(s, current_center_access=False)),
        ]:
            player = ApproachPlayer()
            player.transform = transform
            with self.subTest(reason=reason):
                self.assertEqual(self.execute(player).reason, reason)
                self.assertEqual(player.calls, [("stop",)])
        player = ApproachPlayer()
        player.on_drive = lambda: player.position.__setitem__(1, 65.)
        self.assertEqual(self.execute(player).reason, "vertical_route_unsupported")
        player = ApproachPlayer()
        event = threading.Event()
        event.set()
        result = run_skill(default_registry(), player, "approach", {}, cancel_event=event)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(player.samples, 0)
        self.assertEqual(player.calls, [("stop",)])

    def test_AR13_negative_coordinates_offcenter_and_schema_boundaries(self):
        player = ApproachPlayer([target(-5, z=-3)])
        player.position = [-.15, 64., .2]
        player.yaw = 120.
        result = self.execute(player, target="minecraft:chest")
        self.assertEqual(result.reason, "ready_to_interact")
        self.assertEqual(result.details["target"]["position"], [-5, 64, -3])
        self.assertNotIn((-5, 64, -3), player.trace)
        for position in [[-29_999_984, -2048, 29_999_984], [29_999_984, 2048, -29_999_984]]:
            validated = Approach(position=position, timeout_seconds=.1)
            self.assertEqual(validated.position, position)
        self.assertEqual(Approach(timeout_seconds=120.).timeout_seconds, 120.)

    def test_AR14_faster_native_motion_does_not_oscillate_around_cell_center(self):
        player = ApproachPlayer()
        player.position = [.36, 64., .5]
        player.speed = 2.2  # The old fixed two-tick estimate alternated x=.36/.646 forever.
        progress = []
        result = run_skill(default_registry(), player, "approach", {"timeout_seconds": 25.},
            clock=player.clock, sleeper=player.sleep, publish=progress.append)
        self.assertEqual(result.reason, "ready_to_interact")
        # Feedback updates are more frequent than the old completed pulses; measure elapsed
        # convergence, not update count. Precision one-tick centering is tested separately.
        self.assertLess(player.now, 10.)
        self.assertTrue(all(1 <= d["ticks"] <= 8 for d in player.drive_trace))
        self.assertEqual(player.calls[-1], ("stop",))

    def test_AR15_oscillating_displacement_is_detected_as_no_progress(self):
        player = ApproachPlayer()
        player.position = [.36, 64., .5]
        player.speed = 0.
        drives = []
        def rebound():
            drives.append(1)
            player.position[0] = .646 if len(drives) % 2 else .36
        player.on_drive = rebound
        result = self.execute(player)
        self.assertEqual(result.reason, "stuck")
        self.assertLessEqual(len(drives), 9)
        self.assertEqual(result.cleanup, "released")
        self.assertEqual(player.calls[-1], ("stop",))

    def test_AR16_native_direction_keys_approximate_world_vector_during_turns(self):
        for motion in range(-180, 181, 15):
            for distance in [.14, .349, .35, 1.5]:
                for current in [-179., -90., -70., 0., 90., 110., 458.5]:
                    yaw, keys = travel_inputs(motion, current, distance)
                    forward = int("forward" in keys)-int("back" in keys)
                    right = int("right" in keys)-int("left" in keys)
                    length=max(1.,math.hypot(forward,right));forward,right=forward/length,right/length
                    angle = math.radians(current)
                    dx = -math.sin(angle)*forward-math.cos(angle)*right
                    dz = math.cos(angle)*forward-math.sin(angle)*right
                    actual=math.degrees(math.atan2(-dx,dz))
                    self.assertLessEqual(abs((actual-motion+180)%360-180),22.5+1e-6)
                    self.assertLess(abs((yaw-motion+180)%360-180),1e-6)
                    self.assertTrue(set(keys)<={"forward","back","left","right"})
                    self.assertFalse({"forward","back"}<=set(keys));self.assertFalse({"left","right"}<=set(keys))

    def test_AR17_approach_travel_uses_timed_rotation_without_stopping_motion(self):
        player = ApproachPlayer([target(7, z=6)])
        progress = []
        result = run_skill(default_registry(), player, "approach", {"timeout_seconds": 25.},
            clock=player.clock, sleeper=player.sleep, publish=progress.append)
        self.assertEqual(result.reason, "ready_to_interact")
        timed=[request for request in player.rotation_request_trace if request['duration_ms'] is not None]
        self.assertTrue(timed)
        self.assertTrue(all(request['duration_ms']==200 and request['rotation_profile']=='smoothstep' for request in timed))
        self.assertTrue(any(abs((request['yaw']+90+180)%360-180)>8 for request in timed))
        self.assertTrue(any(event['held'] for event in player.events if event['kind']=='look'))
        drives = player.drive_trace
        self.assertTrue(all(math.isfinite(d["pitch"]) and abs(d["pitch"])<=90 for d in drives))
        self.assertLessEqual(abs(drives[-1]['pitch']),1.)
        self.assertGreaterEqual(sum("forward" in c["buttons"] for c in drives)/len(drives), .55)
        self.assertTrue(all(c["ticks"] <= 8 for c in drives if {"left", "right"} & set(c["buttons"])))
        self.assertTrue(any(p["phase"] == "checking_target" for p in progress))
        self.assertEqual(player.calls[-1], ("stop",))

    def test_AR18_actor_and_cancel_checked_during_turning_before_any_drive(self):
        player = ApproachPlayer([target(7, z=6)])
        player.yaw = -80.
        original_look=player.look;drives_at_replacement=[]
        def replace_during_turn(*args,**kwargs):
            original_look(*args,**kwargs);drives_at_replacement.append(len(player.drive_trace));player.session="replacement"
        player.look=replace_during_turn
        result = self.execute(player)
        self.assertEqual(result.reason, "actor_session_changed")
        self.assertEqual(len(player.drive_trace),drives_at_replacement[0])  # Fresh actor fence precedes any post-turn drive.
        self.assertEqual(player.calls[-1], ("stop",))
        player = ApproachPlayer([target(7, z=6)])
        player.yaw = -80.
        event = threading.Event()
        original_look = player.look
        drives_at_cancel=[]
        def cancel_on_turn(*args, **kwargs):
            original_look(*args, **kwargs);drives_at_cancel.append(len(player.drive_trace));event.set()
        player.look = cancel_on_turn
        result = run_skill(default_registry(), player, "approach", {}, clock=player.clock,
                           sleeper=player.sleep, cancel_event=event)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(len(player.drive_trace),drives_at_cancel[0])  # Cancellation check precedes another drive.
        self.assertEqual(player.calls[-1], ("stop",))

    def test_AR19_timed_turn_uses_shortest_arc_and_accepts_unwrapped_observations(self):
        player = ApproachPlayer()
        context = SkillContext(player, threading.Event(), 10., lambda _: None, player.clock, player.sleep)
        for view, wanted in [((179.,0.),(-179.,0.)),((-179.,0.),(179.,0.)),((458.5,0.),(99.5,0.))]:
            player.rotation=None;player.yaw,player.pitch=view
            delta=_yaw_delta(wanted[0],view[0])
            self.assertTrue(rotate_view_timed(context,view,wanted,player.session))
            advanced=_yaw_delta(player.yaw,view[0])
            self.assertGreater(advanced*delta,0.);self.assertLess(abs(advanced),abs(delta))
            player.sleep(.15)
            self.assertLess(abs(_yaw_delta(wanted[0],player.yaw)),1e-6)
            request=player.rotation_request_trace[-1]
            self.assertEqual((request['duration_ms'],request['rotation_profile']),(200,'smoothstep'))
        self.assertFalse(any(c[0] == "drive" for c in player.calls))

    def test_AR11_python_and_cli_dispatch(self):
        calls = []
        player = Player(CallableBackend(lambda q: calls.append(q) or {"profile": "flat_full_blocks_v1", "ready": False,
                                                                   "reason": "not_in_world"}))
        self.assertEqual(player.approach("chest")["reason"], "not_in_world")
        self.assertEqual(calls, [{"op": "navigation"}, {"op": "stop"}])
        from blockwire.cli import main
        with patch.object(sys, "argv", ["blockwire", "approach", "chest", "--position", "7", "64", "0", "--sneak"]), \
             patch("blockwire.cli.Bridge.from_env"), patch("blockwire.cli.Player") as factory, \
             contextlib.redirect_stdout(io.StringIO()):
            factory.return_value.approach.return_value = {"status": "succeeded"}
            main()
            factory.return_value.approach.assert_called_once_with("chest", position=[7, 64, 0], sneak=True,
                                                                avoid_damage=True, timeout_seconds=30)


if __name__ == "__main__":
    unittest.main()
