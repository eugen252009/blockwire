"""Walk-to rolling integration contracts, not graphical smoothness acceptance."""
import math
import threading
import unittest

from blockwire.skills import default_registry, run_skill
from test_approach import ApproachPlayer


class WalkingContinuousContracts(unittest.TestCase):
    def execute(self, player, *, event=None, publish=lambda _: None):
        return run_skill(default_registry(), player, "walk_to",
                         {"x": 10.5, "y": 64., "z": .5, "timeout_seconds": 30.},
                         clock=player.clock, sleeper=player.sleep,
                         cancel_event=event, publish=publish)

    def test_WC01_walk_holds_forward_across_feedback_and_arrives_upright(self):
        player = ApproachPlayer([])
        progress = []
        result = self.execute(player, publish=progress.append)
        self.assertEqual(result.status, "succeeded", result)
        self.assertLessEqual(math.dist(player.position, [10.5, 64., .5]), .3)
        self.assertTrue(any(p["control_mode"] == "rolling" for p in progress))
        self.assertTrue(any(d["previously_held"] == ("forward",) for d in player.drive_trace[1:]))
        for kind in ["navigation", "observe"]:
            self.assertTrue(any(e["kind"] == kind and "forward" in e["held"] for e in player.events))
        self.assertFalse(any(e["kind"] == "look" for e in player.events))  # Already-aligned camera is not rewritten.
        self.assertTrue(all("sneak" not in d["buttons"] for d in player.drive_trace))
        self.assertTrue(all(1 <= d["ticks"] <= 8 for d in player.drive_trace))
        self.assertFalse(player.held)
        self.assertEqual(result.cleanup, "released")

    def test_WC02_cancel_and_damage_release_a_rolling_walk(self):
        for damage in [False, True]:
            with self.subTest(damage=damage):
                player, event = ApproachPlayer([]), threading.Event()
                def interrupt():
                    if len(player.drive_trace) == 3:
                        if damage:
                            player.health = 18.
                        else:
                            event.set()
                player.on_drive = interrupt
                result = self.execute(player, event=event)
                self.assertEqual(result.status, "blocked" if damage else "cancelled")
                if damage:
                    self.assertEqual(result.reason, "damage_observed")
                self.assertEqual(len(player.drive_trace), 3)
                self.assertFalse(player.held)
                self.assertEqual(result.cleanup, "released")

    def test_WC03_large_turn_keeps_moving_and_cancel_releases(self):
        player, event = ApproachPlayer([]), threading.Event()
        player.yaw = 90.
        def interrupt():
            if len(player.drive_trace)==3:event.set()
        player.on_drive=interrupt
        result = self.execute(player, event=event)
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(len(player.drive_trace),3)
        self.assertTrue(player.rotation_request_trace)
        self.assertTrue(all(request['duration_ms']==200 and request['rotation_profile']=='smoothstep'
                            for request in player.rotation_request_trace))
        self.assertTrue(any(e["held"] for e in player.events if e["kind"] == "look"))
        self.assertGreaterEqual(player.samples,4)
        self.assertFalse(player.held);self.assertIsNone(player.rotation)


if __name__ == "__main__":
    unittest.main()
