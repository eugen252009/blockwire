"""FO contracts: one-job melee continuity and RPC budgets; simulated, not gameplay."""
import threading
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from blockwire import CallableBackend, Player
from blockwire.skills import SkillResult, default_registry, run_skill
from test_fighting import Fighter
from test_autopilot import threat


class ReturningEnemy(Fighter):
    def __init__(self):
        super().__init__()
        self.threats = [threat("minecraft:zombie", position=(4.5, 64., .5))]
        self.return_at = .25
        self.inventory_reads = 0

    def navigation(self):
        if self.threats and self.now >= self.return_at:
            mob = self.threats[0]
            mob["position"] = [2.5, 64., .5]
            mob["eye_position"] = [2.5, 65.6, .5]
        return super().navigation()

    def inventory(self):
        self.inventory_reads += 1
        return super().inventory()


class FightOptimizationContracts(unittest.TestCase):
    def execute(self, p, **parameters):
        return run_skill(default_registry(), p, "fight", {"duration_seconds": 8.,
            "timeout_seconds": 9., **parameters}, clock=p.clock, sleeper=p.sleep)

    def test_FO01_one_job_waits_and_resumes_after_repeated_knockback(self):
        p = ReturningEnemy(); hits = []; progress = []
        def hit():
            hits.append(p.now)
            if len(hits) == 6:
                p.threats.clear()
            else:
                p.threats[0]["position"] = [4.5, 64., .5]
                p.threats[0]["eye_position"] = [4.5, 65.6, .5]
                p.return_at = p.now + .25
        p.on_attack = hit
        r = run_skill(default_registry(), p, "fight", {"pursue": False, "duration_seconds": 8.},
            clock=p.clock, sleeper=p.sleep, publish=progress.append)
        self.assertEqual(r.status, "succeeded")
        self.assertEqual(r.details["attacks_submitted"], 6)
        self.assertIsNone(r.details["kills_confirmed"])
        self.assertEqual(r.cleanup, "released")
        self.assertTrue(all(b-a >= .7 for a, b in zip(hits, hits[1:])))
        self.assertFalse(p.drive_trace)
        self.assertEqual(len([c for c in p.calls if c[0] == "look"]), 6)
        self.assertEqual(p.observations, 6)
        self.assertEqual(p.inventory_reads, 7)  # Initial gate + one fresh equipment check per attempt.
        self.assertIn("wait_for_melee", [s["behavior"] for s in progress])
        self.assertEqual(progress[-1]["attacks_submitted"], 6)

    def test_FO02_other_level_waits_without_movement_then_attacks_in_reach(self):
        p = ReturningEnemy()
        p.threats[0]["position"][1] = 65.
        p.threats[0]["eye_position"][1] = 66.6
        progress = []; p.on_attack = lambda: p.threats.clear()
        r = run_skill(default_registry(), p, "fight", {}, clock=p.clock,
                      sleeper=p.sleep, publish=progress.append)
        self.assertEqual(r.status, "succeeded")
        self.assertEqual(r.details["attacks_submitted"], 1)
        self.assertFalse(p.drive_trace)
        self.assertEqual(progress[0]["attack_wait_reason"], "enemy_on_other_level")
        self.assertEqual(progress[0]["behavior"], "wait_for_melee")
        p = ReturningEnemy(); p.threats[0]["position"][1] = 65.
        self.assertEqual(self.execute(p, melee_wait_seconds=0.).reason, "enemy_on_other_level")
        self.assertEqual(p.now, 0.)

    def test_FO03_grace_is_bounded_even_if_target_identity_changes(self):
        p = ReturningEnemy(); p.return_at = float("inf")
        original = p.navigation
        def swap():
            p.threats[0]["entity_id"] = 1 + p.samples % 2
            return original()
        p.navigation = swap
        r = self.execute(p, pursue=False, melee_wait_seconds=.3)
        self.assertEqual(r.reason, "enemy_out_of_reach")
        self.assertGreaterEqual(p.now, .3)
        self.assertLess(p.now, .41)
        self.assertFalse(p.drive_trace)
        self.assertFalse(any(c[0] in {"look", "action"} for c in p.calls))
        p = ReturningEnemy()
        self.assertEqual(self.execute(p, pursue=False, melee_wait_seconds=0.).reason, "enemy_out_of_reach")
        self.assertEqual(p.now, 0.)
        p = ReturningEnemy()
        self.assertEqual(self.execute(p, pursue=False, duration_seconds=.1).status, "timed_out")
        self.assertFalse(p.drive_trace)

    def test_FO04_wait_rechecks_cancel_session_health_and_screens(self):
        for kind, reason in [("actor", "actor_session_changed"), ("health", "low_health"),
                             ("screen", "screen_or_pause"), ("cancel", "cancel_requested"),
                             ("hazard", "unsafe_current_cell"), ("fire", "on_fire")]:
            with self.subTest(kind=kind):
                p = ReturningEnemy(); p.return_at = float("inf"); event = threading.Event()
                original = p.navigation
                def changed():
                    if p.now >= .1:
                        if kind == "actor": p.session = "new-world"
                        if kind == "health": p.health = 8.
                        if kind == "cancel": event.set()
                        if kind == "hazard": p.hazards.add((0, 64, 0))
                    s = original()
                    if kind == "screen" and p.now >= .1: s.update(ready=False, reason="screen_or_pause")
                    if kind == "fire" and p.now >= .1: s["on_fire"] = True
                    return s
                p.navigation = changed
                r = run_skill(default_registry(), p, "fight", {"pursue": False},
                    clock=p.clock, sleeper=p.sleep, cancel_event=event)
                self.assertEqual(r.reason, reason)
                self.assertEqual(r.cleanup, "released")
                self.assertFalse(any(c[0] == "action" for c in p.calls))
                if kind != "health": self.assertFalse(p.drive_trace)

    def test_FO05_evade_preempts_waiting(self):
        p = ReturningEnemy(); p.return_at = float("inf"); original = p.navigation
        def arrive():
            if p.now >= .1 and len(p.threats) == 1:
                p.threats.append(threat(position=(3.5, 64., .5), entity_id=2))
            return original()
        p.navigation = arrive; p.on_drive = lambda: p.threats.clear()
        r = self.execute(p, pursue=False)
        self.assertEqual(r.status, "succeeded")
        self.assertTrue(p.drive_trace)
        self.assertFalse(any(c[0] == "action" for c in p.calls))

    def test_FO06_equipment_is_refreshed_after_aim_and_before_movement(self):
        p = ReturningEnemy(); p.return_at = 0.
        original = p.look
        def change(*a, **k): original(*a, **k); p.weapon = None
        p.look = change
        self.assertEqual(self.execute(p).reason, "select_usable_hotbar_weapon")
        self.assertEqual(p.inventory_reads, 2)
        self.assertFalse(any(c[0] == "action" for c in p.calls))
        p = ReturningEnemy(); p.return_at = float("inf")
        p.on_inventory = lambda: setattr(p, 'weapon', None) if p.inventory_reads == 2 else None
        self.assertEqual(self.execute(p).reason, "select_usable_hotbar_weapon")
        self.assertFalse(p.drive_trace)

    def test_FO07_attack_receipt_is_published_before_cancel_and_mismatch_is_explained(self):
        p = ReturningEnemy(); p.return_at = 0.; event = threading.Event(); progress = []
        p.on_attack = event.set
        r = run_skill(default_registry(), p, "fight", {}, clock=p.clock, sleeper=p.sleep,
                      publish=progress.append, cancel_event=event)
        self.assertEqual(r.status, "cancelled")
        self.assertEqual(progress[-1]["attacks_submitted"], 1)
        self.assertEqual(progress[-1]["attack_wait_reason"], "submitted")
        p = ReturningEnemy(); p.return_at = 0.; p.hit_override = {"kind": "entity", "id": 99}
        progress = []
        r = run_skill(default_registry(), p, "fight", {"duration_seconds": .4},
                      clock=p.clock, sleeper=p.sleep, publish=progress.append)
        self.assertEqual(r.status, "timed_out")
        mismatches = [s for s in progress if s.get("attack_wait_reason") == "crosshair_mismatch"]
        self.assertTrue(mismatches)
        self.assertEqual(mismatches[0]["crosshair_entity_id"], 99)
        self.assertEqual(mismatches[0]["entity_id"], 1)
        self.assertFalse(any(c[0] == "action" for c in p.calls))

    def test_FO08_wait_parameter_validation_sdk_and_mcp_schema(self):
        for value in [-.1, 5.1, True, "3", float("inf")]:
            p = ReturningEnemy()
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.execute(p, melee_wait_seconds=value)
            self.assertFalse(p.calls)
        p = Player(CallableBackend(lambda _: {}))
        with patch("blockwire.skills.run_skill", return_value=SkillResult(status="blocked", reason="fixture", text="fixture")) as run:
            p.fight(melee_wait_seconds=.5)
            self.assertEqual(run.call_args.args[3]["melee_wait_seconds"], .5)
        from blockwire.mcp_server import create_server
        with patch("blockwire.mcp_server.Bridge.from_env"), patch("blockwire.mcp_server.Player"):
            server = create_server()
        model = server._tool_manager.get_tool("fight").fn_metadata.arg_model
        for value in [True, "3"]:
            with self.assertRaises(ValidationError): model.model_validate({"melee_wait_seconds": value})
        self.assertEqual(model.model_validate({}).melee_wait_seconds, 3.)

    def test_FO09_knockback_and_equipment_swap_cannot_shorten_prior_cooldown(self):
        p = ReturningEnemy(); p.return_at = 0.; p.weapon["item"] = "minecraft:wooden_axe"
        times = []
        def hit():
            times.append(p.now)
            if len(times) == 2:
                p.threats.clear()
            else:
                p.weapon["item"] = "minecraft:iron_sword"
                p.threats[0]["position"] = [4.5, 64., .5]
                p.return_at = p.now + .25
        p.on_attack = hit
        self.assertEqual(self.execute(p, pursue=False).status, "succeeded")
        self.assertEqual(len(times), 2)
        self.assertGreaterEqual(times[1]-times[0], 1.3)
        self.assertFalse(p.drive_trace)

    def test_FO10_receipt_count_survives_airborne_progress_and_cancel(self):
        p = ReturningEnemy(); p.return_at = 0.; hits = []; progress = []; event = threading.Event()
        p.on_attack = lambda: hits.append(p.now)
        nav, sleep = p.navigation, p.sleep
        def airborne():
            s = nav()
            if hits and p.now < hits[0]+.4: s.update(ready=False, reason="not_grounded")
            return s
        def cancel_after_recovery(seconds):
            sleep(seconds)
            if hits and p.now >= hits[0]+.15: event.set()
        p.navigation = airborne; p.sleep = cancel_after_recovery
        r = run_skill(default_registry(), p, "fight", {}, clock=p.clock, sleeper=p.sleep,
                      publish=progress.append, cancel_event=event)
        self.assertEqual(r.status, "cancelled")
        self.assertEqual(progress[-1]["behavior"], "recover_grounding")
        self.assertEqual(progress[-1]["attacks_submitted"], 1)
        self.assertEqual(r.cleanup, "released")
        self.assertFalse(p.drive_trace)

    def test_FO11_one_job_resumes_after_repeated_visibility_loss(self):
        p = ReturningEnemy(); p.return_at = 0.; hits = []; progress = []
        original = p.navigation
        def visibility():
            if p.threats and p.now >= p.return_at: p.threats[0]["visible"] = True
            return original()
        p.navigation = visibility
        def hit():
            hits.append(p.now)
            if len(hits) == 6:
                p.threats.clear()
            else:
                p.threats[0]["visible"] = False
                p.return_at = p.now + .25
        p.on_attack = hit
        r = run_skill(default_registry(), p, "fight", {"pursue": False, "duration_seconds": 8.},
            clock=p.clock, sleeper=p.sleep, publish=progress.append)
        self.assertEqual(r.status, "succeeded")
        self.assertEqual(r.details["attacks_submitted"], 6)
        self.assertTrue(all(b-a >= .7 for a, b in zip(hits, hits[1:])))
        self.assertFalse(p.drive_trace)
        self.assertEqual(p.inventory_reads, 7)
        self.assertIn("no_visible_selected_enemy", [s.get("attack_wait_reason") for s in progress])

    def test_FO12_hidden_wait_is_bounded_and_never_uses_stale_crosshair(self):
        p = ReturningEnemy(); p.return_at = float("inf")
        p.threats[0]["visible"] = False; p.hit_override = {"kind": "entity", "id": 1}
        r = self.execute(p, melee_wait_seconds=.3)
        self.assertEqual(r.reason, "no_visible_selected_enemy")
        self.assertGreaterEqual(p.now, .3)
        self.assertLess(p.now, .41)
        self.assertEqual(p.inventory_reads, 0)
        self.assertFalse(any(c[0] in {"look", "drive", "action"} for c in p.calls))
        p = ReturningEnemy(); p.threats[0]["visible"] = False
        self.assertEqual(self.execute(p, melee_wait_seconds=0.).reason, "no_visible_selected_enemy")
        self.assertEqual(p.now, 0.)

    def test_FO13_evade_preempts_hidden_wait(self):
        p = ReturningEnemy(); p.return_at = float("inf"); p.threats[0]["visible"] = False
        original = p.navigation
        def arrive():
            if p.now >= .1 and len(p.threats) == 1:
                p.threats.append(threat(position=(3.5, 64., .5), entity_id=2))
            return original()
        p.navigation = arrive; p.on_drive = lambda: p.threats.clear()
        r = self.execute(p, pursue=False)
        self.assertEqual(r.status, "succeeded")
        self.assertTrue(p.drive_trace)
        self.assertFalse(any(c[0] == "action" for c in p.calls))

    def test_FO14_visibility_loss_after_aim_cannot_use_cached_native_hit(self):
        p = ReturningEnemy(); p.return_at = float("inf")
        p.threats[0]["position"] = [2.5, 64., .5]
        p.threats[0]["eye_position"] = [2.5, 65.6, .5]
        p.hit_override = {"kind": "entity", "id": 1}
        look, action = p.look, p.action; attempts = []
        def occlude(*a, **k): look(*a, **k); p.threats[0]["visible"] = False
        def attempted(*a, **k): attempts.append(k); return action(*a, **k)
        p.look = occlude; p.action = attempted
        r = self.execute(p, duration_seconds=.4)
        self.assertEqual(r.status, "timed_out")
        self.assertFalse(attempts)
        self.assertFalse(p.drive_trace)
        self.assertEqual(len(p.view_trace), 1)


if __name__ == "__main__": unittest.main()
