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
        self.yaw, self.pitch = -90., 0.
        self.rotation = None
        self.rotation_requests=[]
        self.transform = lambda state: state

    def clock(self): return self.now
    def _update_rotation(self,at=None):
        if self.rotation is None:return
        now=self.now if at is None else at;start,sy,sp,ty,tp,duration,profile=self.rotation
        t=max(0.,min(1.,(now-start)/duration));p=t if profile=='linear' else t*t*(3-2*t)
        dy=(ty-sy+180)%360-180;self.yaw=sy+dy*p;self.pitch=sp+(tp-sp)*p
        if t>=1:self.rotation=None
    def sleep(self, seconds):self.now+=seconds;self._update_rotation()

    def navigation(self):
        self._update_rotation();self.samples += 1
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

    def observe(self):
        self._update_rotation();return {"in_world": True, "alive": True, "yaw": self.yaw, "pitch": self.pitch}

    def look(self, yaw, pitch, *, actor_session, duration_ms=None, rotation_profile=None):
        assert actor_session == self.session;self._update_rotation()
        if duration_ms is None:self.yaw,self.pitch=yaw,pitch;self.rotation=None
        else:
            target=(yaw+180)%360-180;profile=rotation_profile or 'smoothstep'
            same=(self.rotation is not None and abs((self.rotation[3]-target+180)%360-180)<1e-6 and
                  abs(self.rotation[4]-pitch)<1e-6 and self.rotation[5]==duration_ms/1000 and self.rotation[6]==profile)
            if not same:self.rotation=(self.now,self.yaw,self.pitch,target,pitch,duration_ms/1000,profile)
        self.calls.append(("look", yaw));self.rotation_requests.append(
            {'yaw':yaw,'pitch':pitch,'duration_ms':duration_ms,'rotation_profile':rotation_profile,'time':self.now})

    def drive(self, buttons, ticks, *, wait, actor_session):
        assert actor_session == self.session
        assert ticks <= 8 and not wait
        self.calls.append(("drive", buttons, ticks))
        speed = .065 if "sneak" in buttons else .215
        forward=int("forward" in buttons)-int("back" in buttons)
        right=int("right" in buttons)-int("left" in buttons)
        length=max(1.,math.hypot(forward,right));forward,right=forward/length,right/length
        yaw=math.radians(self.yaw)
        for _ in range(ticks):
            distance=speed*self.speed
            candidate = [self.position[0]+(-math.sin(yaw)*forward-math.cos(yaw)*right)*distance, 64.,
                         self.position[2]+(math.cos(yaw)*forward-math.sin(yaw)*right)*distance]
            cell = (math.floor(candidate[0]), 64, math.floor(candidate[2]));self.trace.append(cell)
            if cell not in self.cells:break
            self.position = candidate

    def stop(self):self._update_rotation();self.rotation=None;self.calls.append(("stop",))


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
        drives = [call for call in player.calls if call[0] == "drive"]
        self.assertTrue(drives)
        self.assertTrue(all("sneak" not in call[1] for call in drives))
        self.assertFalse(result.details["effective_sneak"])

    def test_precision_arrival_is_observed_without_implicit_sneak(self):
        player=FlatPlayer();result=self.execute(player,arrival_radius=.08)
        self.assertEqual(result.status,'succeeded',result)
        self.assertLessEqual(math.dist(player.position,[3.5,64.,.5]),.08)
        self.assertFalse(any('sneak' in c[1] for c in player.calls if c[0]=='drive'))
        self.assertEqual(result.cleanup,'released')

    def test_default_arrival_waits_for_native_velocity_and_settling(self):
        class DriftPlayer(FlatPlayer):
            def __init__(self):
                super().__init__();self.position=[3.79,64.,.5];self.yaw=90.;self.native_speed=.02;self.drifted=0
            def navigation(self):
                state=super().navigation();state['horizontal_speed']=self.native_speed;return state
            def sleep(self,seconds):
                if self.native_speed and seconds>0:
                    self.position[0]+=.0005;self.drifted+=1
                    if self.drifted>=10:self.native_speed=0.
                super().sleep(seconds)
        p=DriftPlayer();result=self.execute(p)
        self.assertEqual(result.status,'succeeded',result);self.assertGreaterEqual(p.drifted,10);self.assertEqual(p.native_speed,0.)
        self.assertLessEqual(math.dist(p.position,[3.5,64.,.5]),.3)
        self.assertEqual(result.cleanup,'released')

    def test_precision_arrival_waits_for_observed_native_settling(self):
        class DriftPlayer(FlatPlayer):
            def __init__(self):
                super().__init__();self.position=[3.55,64.,.5];self.yaw=90.;self.speed=.5;self.drifted=False
            def sleep(self,seconds):
                if not self.drifted and seconds>0:
                    self.position[0]+=.04;self.drifted=True
                super().sleep(seconds)
        p=DriftPlayer();result=self.execute(p,arrival_radius=.08)
        self.assertEqual(result.status,'succeeded',result);self.assertTrue(p.drifted)
        self.assertLessEqual(math.dist(p.position,[3.5,64.,.5]),.08)
        self.assertGreaterEqual(p.clock(),.4)
        self.assertEqual(result.cleanup,'released')

    def test_arrival_radius_is_bounded_and_default_unchanged(self):
        from blockwire.skills.walking import WalkTo
        self.assertEqual(WalkTo(x=0.,y=64.,z=0.).arrival_radius,.3)
        for radius in (0.,.07,.31):
            with self.assertRaises(ValueError):WalkTo(x=0.,y=64.,z=0.,arrival_radius=radius)

    def test_explicit_sneak_is_independent_of_damage_avoidance(self):
        for avoid_damage in [False, True]:
            with self.subTest(avoid_damage=avoid_damage):
                player = FlatPlayer()
                result = self.execute(player, sneak=True, avoid_damage=avoid_damage)
                self.assertEqual(result.status, "succeeded")
                self.assertTrue(result.details["effective_sneak"])
                drives = [call for call in player.calls if call[0] == "drive"]
                self.assertTrue(drives)
                self.assertTrue(all("sneak" in call[1] for call in drives))

    def test_non_center_initial_position_and_non_center_goal(self):
        player = FlatPlayer()
        player.position = [.15, 64., .2]
        result = self.execute(player, x=3.15, z=.25)
        self.assertEqual(result.status, "succeeded")

    def test_route_costs_diagonals_by_native_distance(self):
        mesh={'profile':'flat_full_blocks_v1','current_cell':[0,64,0],
              'cells':[{'position':[0,64,0],'hazards':[]},{'position':[1,64,1],'hazards':[]},
                       {'position':[2,64,0],'hazards':[]},{'position':[1,64,0],'hazards':[]}],
              'edges':[[0,1],[1,2],[0,3],[3,2]]}
        self.assertEqual(route(mesh,(2.5,64.,.5),True),[(0,64,0),(1,64,0),(2,64,0)])

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
                # Even a replacement observed at the goal must never count as arrival.
                player.position = state["position"] = [3.5, 64., .5]
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
        self.assertEqual([d["name"] for d in registry.describe()], ["walk_to", "autopilot", "approach", "fight", "gather_wood", "estimate_distance", "craft_item", "equip_item", "interact_with_block", "place_block", "place_at", "gather_block", "remove_block", "consume_item", "search_blocks", "dig_step", "aim_at"])

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
