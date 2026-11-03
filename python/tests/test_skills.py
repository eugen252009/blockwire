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
        self.sneaking = False
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
                     on_ground=True,horizontal_speed=0.,sneaking=self.sneaking,
                     eye_position=[self.position[0],self.position[1]+(1.27 if self.sneaking else 1.62),self.position[2]],
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

    def drive(self, buttons, ticks, *, wait, actor_session, button_ticks=None):
        assert actor_session == self.session
        assert ticks <= 8 and not wait
        self.sneaking='sneak' in buttons
        self.calls.append(("drive", buttons, ticks, button_ticks) if button_ticks is not None else ("drive", buttons, ticks))
        speed = .065 if "sneak" in buttons else .215
        forward=int("forward" in buttons)-int("back" in buttons)
        right=int("right" in buttons)-int("left" in buttons)
        length=max(1.,math.hypot(forward,right));forward,right=forward/length,right/length
        yaw=math.radians(self.yaw)
        movement_ticks=max((button_ticks.get(button,ticks) for button in ('forward','back','left','right') if button in buttons),default=ticks) if button_ticks is not None else ticks
        for _ in range(movement_ticks):
            distance=speed*self.speed
            candidate = [self.position[0]+(-math.sin(yaw)*forward-math.cos(yaw)*right)*distance, 64.,
                         self.position[2]+(math.cos(yaw)*forward-math.sin(yaw)*right)*distance]
            cell = (math.floor(candidate[0]), 64, math.floor(candidate[2]));self.trace.append(cell)
            if cell not in self.cells:break
            self.position = candidate

    def stop(self):self._update_rotation();self.rotation=None;self.sneaking=False;self.calls.append(("stop",))


class SkillContracts(unittest.TestCase):
    def execute(self, player, **arguments):
        parameters = {"x": 3.5, "y": 64., "z": .5, "timeout_seconds": 20., **arguments}
        return run_skill(default_registry(), player, "walk_to", parameters,
                         clock=player.clock, sleeper=player.sleep)

    def test_recorded_crouch_path_keeps_native_sneak_across_ordered_samples(self):
        player=FlatPlayer();player.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':0.}
        navigation=player.navigation
        def observed_navigation():player.calls.append(('navigation',));return navigation()
        player.navigation=observed_navigation
        result=run_skill(default_registry(),player,'replay_recorded_path',
                         {'samples':[[.5,64.,.43,0.,0.,1],[.5,64.,.36,0.,0.,1]],'arrival_radius':.08},
                         clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'succeeded')
        drives=[call for call in player.calls if call[0]=='drive']
        self.assertTrue(drives);self.assertTrue(all('sneak' in call[1] for call in drives))
        pulse=('drive',['back','sneak'],8,{'back':1,'sneak':8})
        self.assertIn(pulse,drives)
        self.assertEqual(pulse[3]['back'],1);self.assertEqual(pulse[3]['sneak'],8)
        self.assertLessEqual(math.hypot(player.position[0]-.5,player.position[2]-.36),.08)

    def test_recorded_path_requires_stable_native_settling_before_release(self):
        player=FlatPlayer()
        def unstable(state):
            position=state['position'][:]
            if player.samples>=4:position[0]+=.01*(player.samples-3)
            return {**state,'position':position,'on_ground':True,'horizontal_speed':0.}
        player.transform=unstable
        result=run_skill(default_registry(),player,'replay_recorded_path',
                         {'samples':[[.5,64.,.5,0.,0.,8],[.5,64.,.5,0.,0.,8]]},
                         clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'blocked');self.assertEqual(result.reason,'recorded_path_not_settled')

    def test_recorded_sequence_keeps_crouch_owned_across_exact_placement(self):
        player=FlatPlayer();player.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':0.}
        events=[[0,.5,64.,.43,0.,0.,1],
                [1,'minecraft:cobblestone',0,63,0,0,.5,64.,.43,.5,64.,.5],
                [0,.5,64.,.36,0.,0.,1]]
        placed=SkillResult(status='succeeded',reason='block_placed',text='placed');samples_at_placement=[]
        def place(*args,**kwargs):samples_at_placement.append(player.samples);return placed
        with patch('blockwire.skills.item_actions.place_block',side_effect=place) as action:
            result=run_skill(default_registry(),player,'replay_recorded_sequence',
                             {'events':events,'arrival_radius':.08},clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'succeeded');self.assertEqual(result.details['placements'],1)
        self.assertTrue(action.call_args.kwargs['preserve_recorded_sneak'])
        self.assertEqual(action.call_args.kwargs['expected_session'],'actor-a')
        self.assertGreaterEqual(samples_at_placement[0],3)
        self.assertTrue(all('sneak' in call[1] for call in player.calls if call[0]=='drive'))

    def test_recorded_sequence_observes_native_coast_after_final_one_tick_pulse(self):
        class CoastPlayer(FlatPlayer):
            def __init__(self):
                super().__init__();self.directional_pulses=0;self.post_third_elapsed=0.;self.coasted=False
            def drive(self,buttons,ticks,**kwargs):
                super().drive(buttons,ticks,**kwargs)
                if 'back' in buttons:self.directional_pulses+=1
            def sleep(self,seconds):
                super().sleep(seconds)
                if self.directional_pulses==3 and not self.coasted:
                    self.post_third_elapsed+=seconds
                    if self.post_third_elapsed>.08:
                        self.position[2]-=.07;self.coasted=True
        player=CoastPlayer();player.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':.02 if player.directional_pulses and not player.coasted else 0.}
        events=[[0,.5,64.,.5,0.,0.,8],
                [1,'minecraft:cobblestone',0,63,0,0,.5,64.,.5,.5,64.,.5],
                [0,.5,64.,0.,0.,0.,1]]
        placed=SkillResult(status='succeeded',reason='block_placed',text='placed')
        with patch('blockwire.skills.item_actions.place_block',return_value=placed):
            result=run_skill(default_registry(),player,'replay_recorded_sequence',
                             {'events':events,'arrival_radius':.3},clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'succeeded',result)
        self.assertTrue(player.coasted);self.assertEqual(player.directional_pulses,3)
        directional=[call for call in player.calls if call[0]=='drive' and 'back' in call[1]]
        self.assertEqual(len(directional),3)
        self.assertLessEqual(math.hypot(player.position[0]-.5,player.position[2]),.3)

    def test_recorded_path_directional_tick_covers_immediate_terminal_hold_checkpoint(self):
        player=FlatPlayer();player.position=[-2.7028867757736146,64.,-.9640921198414746]
        player.yaw,player.pitch=-137.24973,15.749997
        player.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':0.}
        samples=[[-2.70643406892,64.,-.68578578836,-137.24973,15.749997,3],
                 [-2.70643406892,64.,-.6622411968800002,-116.5497,16.649996,8]]
        result=run_skill(default_registry(),player,'replay_recorded_path',
                         {'samples':samples,'arrival_radius':.3},clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'succeeded',result)
        directional=[call for call in player.calls if call[0]=='drive' and 'right' in call[1]]
        self.assertEqual(directional,[('drive',['right','sneak'],8,{'right':1,'sneak':8})])
        self.assertLessEqual(math.hypot(player.position[0]-samples[-1][0],player.position[2]-samples[-1][2]),.3)

    def test_recorded_path_never_invents_direction_for_unreachable_hold_pair(self):
        player=FlatPlayer();player.position=[-2.7028867757736146,64.,-.9640921198414746]
        player.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':0.}
        samples=[[*player.position[:3],-137.24973,15.749997,8],
                 [-2.70643406892,64.,-.6622411968800002,-116.5497,16.649996,8]]
        result=run_skill(default_registry(),player,'replay_recorded_path',
                         {'samples':samples,'arrival_radius':.3},clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'blocked');self.assertEqual(result.reason,'recorded_path_sample_not_reached')
        self.assertEqual(result.details['sample'],1);self.assertEqual(result.details['hold_target'],None)
        self.assertFalse(any(call[0]=='drive' and any(button in call[1] for button in ('forward','back','left','right')) for call in player.calls))

    def test_recorded_path_terminal_hold_actor_and_deadline_precede_directional_tick(self):
        samples=[[-2.70643406892,64.,-.68578578836,-137.24973,15.749997,3],
                 [-2.70643406892,64.,-.6622411968800002,-116.5497,16.649996,8]]
        class ReplacedPlayer(FlatPlayer):
            def observe(self):
                value=super().observe();value['actor_session']='actor-b';return value
        replaced=ReplacedPlayer();replaced.position=[-2.7028867757736146,64.,-.9640921198414746]
        replaced.yaw,replaced.pitch=-137.24973,15.749997
        replaced.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':0.}
        actor=run_skill(default_registry(),replaced,'replay_recorded_path',{'samples':samples,'arrival_radius':.3},
                        clock=replaced.clock,sleeper=replaced.sleep)
        self.assertEqual(actor.reason,'actor_session_changed')
        self.assertFalse(any(call[0]=='drive' and 'right' in call[1] for call in replaced.calls))
        deadline=FlatPlayer();deadline.position=[-2.7028867757736146,64.,-.9640921198414746]
        deadline.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':0.}
        timed=run_skill(default_registry(),deadline,'replay_recorded_path',
                        {'samples':samples,'arrival_radius':.3,'timeout_seconds':.1},
                        clock=deadline.clock,sleeper=deadline.sleep)
        self.assertEqual(timed.status,'timed_out');self.assertEqual(timed.reason,'deadline_exceeded')
        self.assertFalse(any(call[0]=='drive' and 'right' in call[1] for call in deadline.calls))

    def test_recorded_path_terminal_hold_pre_cancel_has_no_directional_tick(self):
        player=FlatPlayer();event=threading.Event();event.set()
        samples=[[-2.70643406892,64.,-.68578578836,-137.24973,15.749997,3],
                 [-2.70643406892,64.,-.6622411968800002,-116.5497,16.649996,8]]
        result=run_skill(default_registry(),player,'replay_recorded_path',{'samples':samples,'arrival_radius':.3},cancel_event=event)
        self.assertEqual(result.status,'cancelled');self.assertEqual(result.reason,'cancel_requested')
        self.assertFalse(any(call[0]=='drive' and 'right' in call[1] for call in player.calls))

    def test_recorded_drop_uses_bounded_native_step_off_and_observed_landing(self):
        class DropPlayer(FlatPlayer):
            def __init__(self):
                super().__init__();self.position=[3.876,64.,3.627];self.on_ground=True;self.falling=False;self.pulses=0
            def navigation(self):
                state=super().navigation();return {**state,'position':self.position[:],'on_ground':self.on_ground,
                    'ready':self.on_ground,'reason':None if self.on_ground else 'not_grounded','horizontal_speed':0.}
            def drive(self,buttons,ticks,**kwargs):
                super().drive(buttons,ticks,**kwargs)
                if buttons==['forward']:
                    self.pulses+=1
                    if self.pulses==2:self.on_ground=False;self.falling=True
            def sleep(self,seconds):
                super().sleep(seconds)
                if self.falling:
                    self.position[1]-=.5
                    if self.position[1]<=61.:
                        self.position=[3.53,61.,3.34];self.on_ground=True;self.falling=False
        player=DropPlayer()
        result=run_skill(default_registry(),player,'replay_recorded_drop',
                         {'edge':[3.648,64.,3.422],'landing':[3.53,61.,3.34],
                          'yaw':126.3,'pitch':67.5,'direction':'forward'},clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'succeeded',result);self.assertEqual(player.pulses,2)
        self.assertTrue(all(call[2]==1 for call in player.calls if call[0]=='drive' and call[1]==['forward']))
        self.assertLessEqual(result.details['distance'],.5);self.assertEqual(player.calls[-1],('stop',))

    def test_recorded_grounded_checkpoint_uses_exact_view_and_one_tick_native_direction(self):
        player=FlatPlayer();player.transform=lambda state:{**state,'on_ground':True,'horizontal_speed':0.}
        result=run_skill(default_registry(),player,'walk_to',
                         {'x':.5,'y':64.,'z':.37,'movement':'sneak','arrival_radius':.08,
                          'recorded_yaw':0.,'recorded_pitch':0.,'recorded_direction':'back'},
                         clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'succeeded')
        self.assertIn(('drive',['back','sneak'],1),player.calls)
        self.assertLessEqual(math.hypot(player.position[0]-.5,player.position[2]-.37),.08)
        self.assertEqual(player.calls[-1],('stop',))

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
        self.assertEqual([d["name"] for d in registry.describe()], ["walk_to", "replay_recorded_path", "replay_recorded_sequence", "replay_recorded_drop", "autopilot", "approach", "fight", "gather_wood", "estimate_distance", "craft_item", "equip_item", "interact_with_block", "place_block", "place_at", "gather_block", "remove_block", "consume_item", "search_blocks", "dig_step", "aim_at"])

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
