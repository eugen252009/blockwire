"""CM01–CM13: lease/feedback traces in a deterministic fixture, NOT Minecraft acceptance."""
import math
import threading
import unittest

from blockwire import BridgeError
from blockwire.skills import default_registry, run_skill
from blockwire.skills.core import SkillContext
from blockwire.skills.motion import FlatMotion, _straight_ahead
from test_approach import ApproachPlayer
from test_autopilot import AutoPlayer


class ContinuousMotionContracts(unittest.TestCase):
    def context(self, player):
        return SkillContext(player, threading.Event(), player.now+30., lambda _: None, player.clock, player.sleep)

    def update(self, motor, context, destination=(10.5, 64., .5)):
        state = context.player.navigation()
        scene = context.player.observe()
        return motor.pulse(context, state, destination, "sneak", max_ticks=3,
                           view=(scene["yaw"], scene["pitch"]), continuous=True)

    def test_CM01_precision_near_actual_waypoint_remains_single_tick(self):
        player, motor = ApproachPlayer([]), FlatMotion()
        player.position[0], player.speed = .36, 2.2
        context = self.context(player)
        self.assertIsNone(self.update(motor, context, (.5, 64., .5)))
        self.assertEqual(player.drive_trace[0]["ticks"], 1)
        self.assertAlmostEqual(player.position[0], .503)
        self.assertFalse(player.held)
        self.assertFalse(motor.holding)

    def test_CM02_forward_is_held_during_observation_steering_and_renewal(self):
        player, motor = ApproachPlayer([]), FlatMotion()
        context = self.context(player)
        for _ in range(4):
            self.assertIsNone(self.update(motor, context))  # No input receipt is a goal outcome.
        self.assertEqual(motor.mode, "rolling")
        self.assertEqual(sum(e["kind"] == "stop" for e in player.events), 0)  # Already aligned: no synthetic release stage.
        for kind in ["navigation", "observe", "drive"]:
            self.assertTrue(any(e["kind"] == kind and "forward" in e["held"] for e in player.events))
        self.assertFalse(any(e["kind"] == "look" for e in player.events))
        self.assertTrue(all(d["previously_held"] == ("forward", "sneak") for d in player.drive_trace[1:]))
        self.assertTrue(all(4 <= d["ticks"] <= 8 for d in player.drive_trace))
        # Four renewals execute four feedback intervals, NOT four complete 8-tick impulses.
        self.assertAlmostEqual(player.position[0]-.5, 4*.065)
        motor.halt(context)
        self.assertFalse(player.held)

    def test_CM03_controller_stall_does_not_extend_native_lease(self):
        player, motor = ApproachPlayer([]), FlatMotion()
        self.update(motor, self.context(player))
        self.assertEqual(player.drive_trace[0]["ticks"], 8)
        player.sleep(1.)
        self.assertFalse(player.held)
        self.assertAlmostEqual(player.position[0]-.5, 8*.065)
        position = player.position[:]
        player.sleep(2.)
        self.assertEqual(player.position, position)
        self.assertEqual(len(player.drive_trace), 1)

    def test_CM04_small_right_angle_and_reverse_rotation_keep_world_motion(self):
        player, motor = ApproachPlayer([]), FlatMotion()
        context = self.context(player)
        self.update(motor, context)
        player.position[2] += .02
        previous_yaw = player.yaw
        self.update(motor, context)
        self.assertGreater(abs(player.yaw-previous_yaw), .01)
        self.assertIn("forward", [e for e in player.events if e["kind"] == "look"][-1]["held"])
        self.assertEqual(sum(e["kind"] == "stop" for e in player.events), 0)
        count = len(player.drive_trace)
        player.rotation=None;player.yaw += 45.
        self.update(motor, context)
        self.assertTrue(motor.turning)
        self.assertEqual(len(player.drive_trace), count+1)
        self.assertTrue({"left","right"} & set(player.drive_trace[-1]["buttons"]))
        self.assertTrue(player.held)
        count = len(player.drive_trace);player.rotation=None;player.yaw = 90.
        self.update(motor, context)
        self.assertTrue(motor.turning)
        self.assertEqual(len(player.drive_trace), count+1)
        self.assertIn("back",player.drive_trace[-1]["buttons"])
        self.assertTrue(player.held)
        self.assertTrue(all(request['duration_ms']==200 and request['rotation_profile']=='smoothstep'
                            for request in player.rotation_request_trace))

    def test_CM17_narrow_support_turns_before_driving_but_broad_ground_overlaps(self):
        player,motor=ApproachPlayer([]),FlatMotion();player.yaw=90.
        player.cells={(x,64,0) for x in range(-1,13)}
        context=self.context(player)
        for _ in range(4):self.update(motor,context)
        self.assertFalse(player.drive_trace);self.assertTrue(player.rotation_request_trace)
        self.update(motor,context)
        self.assertTrue(player.drive_trace);self.assertIn('forward',player.drive_trace[-1]['buttons'])
        broad=ApproachPlayer([]);broad.yaw=90.
        self.update(FlatMotion(),self.context(broad))
        self.assertTrue(broad.drive_trace)

    def test_CM16_drive_quantization_uses_fresh_view_after_timed_rotation_update(self):
        player,motor=ApproachPlayer([]),FlatMotion();player.yaw=90.
        self.assertIsNone(self.update(motor,self.context(player)))
        drive=player.drive_trace[-1];buttons=set(drive['buttons'])
        forward=int('forward' in buttons)-int('back' in buttons)
        right=int('right' in buttons)-int('left' in buttons)
        length=max(1.,math.hypot(forward,right));forward,right=forward/length,right/length
        angle=math.radians(drive['yaw'])
        dx=-math.sin(angle)*forward-math.cos(angle)*right
        dz=math.cos(angle)*forward-math.sin(angle)*right
        actual=math.degrees(math.atan2(-dx,dz))
        self.assertLessEqual(abs((actual+90+180)%360-180),22.5+1e-6)
        self.assertTrue({'back','left'}<=buttons)

    def test_CM15_transient_turn_revalidation_uncertainty_stops_and_replans(self):
        player,motor=ApproachPlayer([]),FlatMotion();context=self.context(player)
        self.update(motor,context);count=len(player.drive_trace)
        player.rotation=None;player.yaw=90.;samples=[0]
        def transient(state):
            samples[0]+=1
            return dict(state,current_center_access=False) if samples[0]==2 else state
        player.transform=transient;before=player.now
        self.assertIsNone(self.update(motor,context))
        self.assertGreater(player.now-before,.19)  # Timed request feedback plus bounded settling checks.
        self.assertEqual(len(player.drive_trace),count);self.assertFalse(player.held)
        self.assertEqual(motor.mode,'turning')
        player.transform=lambda state:state
        self.assertIsNone(self.update(motor,context));self.assertEqual(len(player.drive_trace),count+1)

    def test_CM18_recorded_sneak_edge_pose_uses_only_supported_single_tick_pulses(self):
        from test_skills import FlatPlayer
        player,motor=FlatPlayer(),FlatMotion();player.position=[3.015,64.,.52];player.cells={(3,64,0)};player.yaw=90.
        context=self.context(player);state=player.navigation();scene=player.observe()
        result=motor.pulse(context,state,(2.7004,64.,.52),'sneak',view=(scene['yaw'],scene['pitch']),
                           continuous=True,precision_sneak=False,arrival_radius=.3)
        directional=[c for c in player.calls if c[0]=='drive' and any(b in c[1] for b in ('forward','back','left','right'))]
        self.assertIsNone(result);self.assertEqual(len(directional),1)
        self.assertEqual(player.calls[0],('drive',['sneak'],8))
        self.assertEqual(directional[0][2],8)
        self.assertEqual(directional[0][3],{'forward':1,'sneak':8})
        self.assertEqual(player.calls[-1],('drive',['sneak'],8))
        self.assertEqual(motor.mode,'edge_precision');self.assertFalse(motor.holding)
        self.assertTrue(motor.sneak_stance)
        self.assertFalse(any(c[0]=='stop' for c in player.calls))
        motor.halt(context)
        self.assertFalse(motor.sneak_stance);self.assertEqual(player.calls[-1],('stop',))

        for movement,target in [('walk',(2.7004,64.,.52)),('sneak',(2.7,64.,.52))]:
            with self.subTest(movement=movement,target=target):
                player,motor=FlatPlayer(),FlatMotion();player.position=[3.015,64.,.52];player.cells={(3,64,0)};player.yaw=90.
                state=player.navigation();scene=player.observe()
                result=motor.pulse(self.context(player),state,target,movement,view=(scene['yaw'],scene['pitch']),
                                   continuous=True,precision_sneak=False,arrival_radius=.3)
                self.assertIsNotNone(result);self.assertEqual(result.reason,'no_known_safe_route')
                self.assertFalse(any(c[0]=='drive' for c in player.calls))

    def test_CM19_edge_stance_is_released_on_actor_loss_before_another_pulse(self):
        from test_skills import FlatPlayer
        player,motor=FlatPlayer(),FlatMotion();player.position=[3.015,64.,.52];player.cells={(3,64,0)};player.yaw=90.
        context=self.context(player)
        motor.pulse(context,player.navigation(),(2.7004,64.,.52),'sneak',view=(90.,0.),continuous=True)
        self.assertTrue(motor.sneak_stance);self.assertFalse(motor.holding)
        player.session='replacement';state=player.navigation();before=len(player.calls)
        result=motor.pulse(context,state,(2.7004,64.,.52),'sneak',view=(90.,0.),continuous=True)
        self.assertEqual(result.reason,'actor_session_changed')
        self.assertEqual(player.calls[before:],[('stop',)])
        self.assertFalse(motor.sneak_stance)

    def test_CM05_uncertain_route_readiness_and_replacement_stop_before_renewal(self):
        for invalid in ["route", "ready", "session"]:
            with self.subTest(invalid=invalid):
                player, motor = ApproachPlayer([]), FlatMotion()
                context = self.context(player)
                self.update(motor, context)
                state = player.navigation()
                if invalid == "route":
                    state["edges"] = []
                elif invalid == "ready":
                    state["ready"] = False
                else:
                    player.session = state["actor_session"] = "replacement"
                result = motor.pulse(context, state, (10.5, 64., .5), "sneak",
                                     view=(player.yaw, player.pitch), continuous=True)
                self.assertEqual(result.status, "blocked")
                self.assertFalse(player.held)
                self.assertEqual(len(player.drive_trace), 1)

    def test_CM06_cancel_during_renewal_releases_owned_controls(self):
        player, event = ApproachPlayer(), threading.Event()
        def cancel():
            if len(player.drive_trace) == 2:
                event.set()
        player.on_drive = cancel
        result = run_skill(default_registry(), player, "approach", {}, cancel_event=event,
                           clock=player.clock, sleeper=player.sleep)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.cleanup, "released")
        self.assertEqual(len(player.drive_trace), 2)
        self.assertTrue(player.drive_trace[-1]["previously_held"])
        self.assertFalse(player.held)

    def test_CM07_damage_actor_change_and_deadline_during_hold_do_not_renew(self):
        for invalid in ["damage", "session", "deadline"]:
            with self.subTest(invalid=invalid):
                player = ApproachPlayer()
                def interrupt():
                    if invalid == "damage":
                        player.health -= 1
                    elif invalid == "session":
                        player.session = "replacement"
                    else:
                        player.now += 31.
                player.on_drive = interrupt
                result = run_skill(default_registry(), player, "approach", {},
                                   clock=player.clock, sleeper=player.sleep)
                self.assertEqual(result.reason, {"damage": "damage_observed", "session": "actor_session_changed",
                                                "deadline": "deadline_exceeded"}[invalid])
                self.assertEqual(len(player.drive_trace), 1)
                self.assertEqual(result.cleanup, "released")
                self.assertFalse(player.held)

    def test_CM08_autopilot_reobserves_arrival_after_releasing_a_rolling_lease(self):
        player = AutoPlayer()
        def relocate():
            player.position[0] = 4.5  # Fixture external update, not an automation teleport action.
        player.on_drive = relocate
        result = run_skill(default_registry(), player, "autopilot", {"destination": {"x": 4.5, "y": 64., "z": .5},
                           "movement": "sneak"}, clock=player.clock, sleeper=player.sleep)
        self.assertEqual(result.reason, "arrived")
        self.assertFalse([e for e in player.events if e["kind"] == "navigation"][-1]["held"])
        self.assertLessEqual(math.dist(player.position, [4.5, 64., .5]), .3)
        self.assertEqual(result.cleanup, "released")
        self.assertFalse(player.held)

    def test_CM09_collinear_lookahead_never_shortcuts_a_corner_gap_or_offcenter_axis(self):
        self.assertIsNone(_straight_ahead([(0,64,0), (1,64,0), (1,64,1)], [.5,64,.5]))
        self.assertIsNone(_straight_ahead([(0,64,0), (2,64,0), (3,64,0)], [.5,64,.5]))
        self.assertIsNone(_straight_ahead([(0,64,0), (1,64,0), (2,64,0)], [.5,64,.7]))
        for dx, dz in [(1,0), (-1,0), (0,1), (0,-1)]:
            with self.subTest(direction=(dx,dz)):
                path = [(dx*i,64,dz*i) for i in range(4)]
                point, direction = _straight_ahead(path, [.5,64,.5])
                self.assertEqual(point, (dx*3+.5,64,dz*3+.5))
                self.assertEqual(direction, (dx,dz))
        point, _ = _straight_ahead([(0,64,0), (1,64,0), (2,64,0), (2,64,1)], [.5,64,.5])
        self.assertEqual(point, (2.5,64,.5))

    def test_CM10_observed_speed_jump_stops_rolling_instead_of_blind_renewal(self):
        player, motor = ApproachPlayer([]), FlatMotion()
        context = self.context(player)
        self.update(motor, context)
        player.speed = 20.
        player.sleep(.05)
        self.update(motor, context)
        self.assertNotEqual(motor.mode, "rolling")
        self.assertFalse(player.held)
        self.assertEqual(len(player.drive_trace), 1)

    def test_CM14_native_speed_brakes_before_final_arrival(self):
        player,motor=ApproachPlayer([]),FlatMotion();player.position=[4.1,64.,.5]
        state=player.navigation();state['horizontal_speed']=.15;motor.holding=True;motor._session=player.session
        count=len(player.drive_trace);self.assertIsNone(motor.pulse(self.context(player),state,(4.5,64.,.5),'walk',
            view=(player.yaw,player.pitch),continuous=True,precision_sneak=False,arrival_radius=.3))
        self.assertEqual(motor.mode,'braking');self.assertEqual(len(player.drive_trace),count);self.assertFalse(player.held)

    def test_CM11_autopilot_and_approach_share_real_rolling_integration(self):
        for skill, player, parameters in [
            ("approach", ApproachPlayer(), {}),
            ("autopilot", AutoPlayer(), {"destination": {"x": 4.5, "y": 64., "z": .5}, "movement": "sneak"}),
        ]:
            with self.subTest(skill=skill):
                result = run_skill(default_registry(), player, skill, parameters,
                                   clock=player.clock, sleeper=player.sleep)
                self.assertEqual(result.status, "succeeded")
                self.assertTrue(any(d["previously_held"] for d in player.drive_trace))
                self.assertTrue(any(e["kind"] == "observe" and "forward" in e["held"] for e in player.events))
                self.assertTrue(all(1 <= d["ticks"] <= 8 for d in player.drive_trace))
                self.assertFalse(player.held)

    def test_CM12_unconfirmed_cleanup_is_not_success_and_lease_still_expires(self):
        player = ApproachPlayer()
        original_stop, fail = player.stop, []
        def stop():
            if fail:
                raise BridgeError("fixture stop unavailable")
            return original_stop()
        def damage():
            player.health -= 1
            fail.append(True)
        player.stop, player.on_drive = stop, damage
        result = run_skill(default_registry(), player, "approach", {}, clock=player.clock, sleeper=player.sleep)
        self.assertEqual(result.reason, "damage_observed")
        self.assertNotEqual(result.status, "succeeded")
        self.assertEqual(result.cleanup, "not_confirmed")
        self.assertTrue(player.held)  # Failed cleanup must not pretend native keys were released.
        player.sleep(1.)
        self.assertFalse(player.held)

    def test_CM13_small_advances_accumulate_at_the_faster_feedback_cadence(self):
        for skill, player, parameters in [
            ("approach", ApproachPlayer(), {}),
            ("autopilot", AutoPlayer(), {"destination": {"x": 4.5, "y": 64., "z": .5}, "movement": "sneak"}),
        ]:
            with self.subTest(skill=skill):
                event = threading.Event()
                # Same .00975-block feedback step for upright approach and sneak autopilot.
                player.speed = .00975 / (.215 if skill == "approach" else .065)
                def cancel():
                    if len(player.drive_trace) >= 20:
                        event.set()
                player.on_drive = cancel
                result = run_skill(default_registry(), player, skill, parameters, cancel_event=event,
                                   clock=player.clock, sleeper=player.sleep)
                self.assertEqual(result.status, "cancelled")  # Not a false 'stuck' before this cancellation.
                self.assertEqual(len(player.drive_trace), 20)
                self.assertGreater(player.position[0], .6)
                self.assertEqual(result.cleanup, "released")
                self.assertFalse(player.held)


if __name__ == "__main__":
    unittest.main()
