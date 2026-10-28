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
        self.assertEqual(sum(e["kind"] == "stop" for e in player.events), 1)  # First alignment only.
        for kind in ["navigation", "observe", "look", "drive"]:
            self.assertTrue(any(e["kind"] == kind and "forward" in e["held"] for e in player.events))
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

    def test_CM04_small_steering_overlaps_but_large_turn_releases_first(self):
        player, motor = ApproachPlayer([]), FlatMotion()
        context = self.context(player)
        self.update(motor, context)
        player.position[2] += .02
        previous_yaw = player.yaw
        self.update(motor, context)
        self.assertGreater(abs(player.yaw-previous_yaw), .01)
        self.assertLess(abs(player.yaw-previous_yaw), 4.)
        self.assertIn("forward", [e for e in player.events if e["kind"] == "look"][-1]["held"])
        self.assertEqual(sum(e["kind"] == "stop" for e in player.events), 1)
        count = len(player.drive_trace)
        player.yaw += 45.  # A fresh large camera error on the SAME straight route.
        self.update(motor, context)
        self.assertTrue(motor.turning)
        self.assertEqual(len(player.drive_trace), count)
        self.assertFalse(player.held)
        self.assertFalse([e for e in player.events if e["kind"] == "look"][-1]["held"])

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
                player.speed = .15  # .00975 blocks/sample: below the old per-sample stationary threshold.
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
