"""AR20–AR25: forward travel and bounded target-memory checkpoints, NOT graphical acceptance."""
import threading
import unittest
from blockwire.skills import default_registry, run_skill
from test_approach import ApproachPlayer, target


class NaturalApproachContracts(unittest.TestCase):
    def execute(self, player, *, publish=lambda _: None, cancel_event=None):
        return run_skill(default_registry(), player, "approach", {"timeout_seconds": 60.},
            clock=player.clock, sleeper=player.sleep, publish=publish, cancel_event=cancel_event)

    def test_AR20_out_of_view_travel_uses_bounded_checkpoints_and_forward(self):
        player = ApproachPlayer([target(10, z=8)])
        progress = []
        result = self.execute(player, publish=progress.append)
        self.assertEqual(result.reason, "ready_to_interact")
        self.assertTrue(any(p["phase"] == "checking_target" for p in progress))
        self.assertLess(sum(p["phase"] == "checking_target" for p in progress), len(player.drive_trace)/4)
        self.assertGreaterEqual(sum("forward" in d["buttons"] for d in player.drive_trace)/len(player.drive_trace), .8)
        self.assertTrue(all("back" not in d["buttons"] for d in player.drive_trace))
        last_seen = 0
        for scene in player.scene_records:
            if [10, 64, 8] in scene["visible"]:
                last_seen = scene["drives"]
            else:
                self.assertLessEqual(scene["drives"]-last_seen, 8)  # Includes rolling renewals; no relaxed memory budget.
        self.assertEqual(player.calls[-1], ("stop",))

    def test_AR21_missing_target_out_of_view_stops_at_checkpoint_without_retarget(self):
        player = ApproachPlayer([target(10, z=8)])
        lost_at = []
        def remove():
            if player.position[0] >= 6 and not lost_at:
                lost_at.append(len(player.drive_trace))
                player.targets = []
        player.on_drive = remove
        progress = []
        result = self.execute(player, publish=progress.append)
        self.assertEqual(result.reason, "target_lost")
        self.assertEqual(result.status, "blocked")
        self.assertTrue(any(p["phase"] == "checking_target" for p in progress))
        self.assertLessEqual(len(player.drive_trace)-lost_at[0], 8)
        self.assertEqual(result.cleanup, "released")
        self.assertEqual(player.calls[-1], ("stop",))

    def test_AR25_stale_native_crosshair_cannot_reset_target_checkpoint_budget(self):
        player = ApproachPlayer([target(10, z=8)])
        # Cached renderer target may still name the chest after it is out of view/removed.
        player.native_override = {"kind": "block", "id": "minecraft:chest", "position": [10, 64, 8]}
        lost_at = []
        def remove():
            if player.position[0] >= 6 and not lost_at:
                lost_at.append(len(player.drive_trace))
                player.targets = []
        player.on_drive = remove
        result = self.execute(player)
        self.assertEqual(result.reason, "target_lost")
        self.assertLessEqual(len(player.drive_trace)-lost_at[0], 8)
        self.assertEqual(result.cleanup, "released")

    def test_AR22_visible_straight_route_has_no_target_glances_during_walking(self):
        player = ApproachPlayer()
        progress = []
        result = self.execute(player, publish=progress.append)
        self.assertEqual(result.reason, "ready_to_interact")
        self.assertFalse(any(p["phase"] == "checking_target" for p in progress))
        self.assertTrue(all(d["buttons"] == ["forward", "sneak"] for d in player.drive_trace))
        self.assertTrue(all(abs(d["yaw"]+90) < 1e-6 and abs(d["pitch"]) < 1e-6 for d in player.drive_trace))
        self.assertGreaterEqual(player.observations, len(player.drive_trace)+1)

    def test_AR23_checkpoint_turn_keeps_actor_cancel_and_no_drive_guards(self):
        for cancel in [False, True]:
            player = ApproachPlayer([target(10, z=8)])
            event = threading.Event()
            checkpoint = []
            def publish(progress):
                if progress["phase"] == "checking_target" and not checkpoint:
                    checkpoint.append(len(player.drive_trace))
                    if cancel:
                        event.set()
                    else:
                        player.session = "replacement"
            # Mimic the native actor guard on any subsequent look, before changing orientation.
            original_look = player.look
            def look(*args, **kwargs):
                if kwargs["actor_session"] != player.session:
                    from blockwire import BridgeError
                    raise BridgeError("actor_session_changed")
                return original_look(*args, **kwargs)
            player.look = look
            result = self.execute(player, publish=publish, cancel_event=event)
            self.assertTrue(checkpoint)
            self.assertEqual(result.status, "cancelled" if cancel else "blocked")
            if not cancel:
                self.assertEqual(result.reason, "actor_session_changed")
            self.assertEqual(len(player.drive_trace), checkpoint[0])
            self.assertEqual(result.cleanup, "released")
            self.assertEqual(player.calls[-1], ("stop",))

    def test_AR24_elapsed_unconfirmed_time_checks_before_another_drive(self):
        player = ApproachPlayer([target(10, z=8)])
        jumped_at, checked_at = [], []
        def delay(scene):
            if player.drive_trace and not jumped_at and not scene["visible_interactables"]:
                player.now += 3.1
                jumped_at.append(len(player.drive_trace))
            return scene
        player.scene_transform = delay
        def publish(progress):
            if progress["phase"] == "checking_target" and not checked_at:
                checked_at.append(len(player.drive_trace))
        result = self.execute(player, publish=publish)
        self.assertEqual(result.reason, "ready_to_interact")
        self.assertTrue(jumped_at)
        self.assertEqual(checked_at[0], jumped_at[0])


if __name__ == "__main__":
    unittest.main()
