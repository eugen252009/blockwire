"""Campaign scaffold contracts only; these are NOT autonomous gameplay acceptance."""
import importlib.util
import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

from blockwire.skills import SkillDefinition, SkillParameters, SkillRegistry, SkillResult, default_registry

SPEC = importlib.util.spec_from_file_location("blockwire_end_portal_example",
    Path(__file__).resolve().parents[2] / "examples/end_portal.py")
campaign = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = campaign
SPEC.loader.exec_module(campaign)


class PlayerFixture:
    def __init__(self):
        self.scene = {"in_world": True, "alive": True, "actor_session": "overworld-a",
                      "dimension": "minecraft:overworld", "eye_position": [.5, 65.62, .5]}
        self.items = {}
        self.stops = 0
        self.paused = False
        self.native_screen = None

    def observe(self): return dict(self.scene)
    def inventory(self): return {"items": [{"item": k, "count": v} for k, v in self.items.items()]}
    def stop(self): self.stops += 1
    def menu(self): return {"screen_open": self.paused or bool(self.native_screen),
                            "type": self.native_screen or ("PauseScreen" if self.paused else None)}
    def open_pause(self): self.paused = True


def registry(handler):
    result = SkillRegistry()
    for stage in campaign.STAGES:
        result.register(SkillDefinition(stage.skill, stage.goal, SkillParameters,
            lambda ctx, params, stage=stage: handler(ctx, stage)))
    return result


def satisfy(player, stage):
    if stage.dimension_after:
        if player.scene["dimension"] != stage.dimension_after:
            player.scene["actor_session"] += "-transition"
        player.scene["dimension"] = stage.dimension_after
    player.items = {"minecraft:iron_pickaxe": 1, "minecraft:iron_sword": 1, "minecraft:shield": 1,
                    "minecraft:bread": 16, "minecraft:blaze_rod": 8,
                    "minecraft:ender_pearl": 16, "minecraft:ender_eye": 16}
    player.scene["target"] = {"kind": "block", "position": [0, 64, 2],
        "id": "minecraft:end_portal" if stage.skill in {"survival_activate_end_portal", "survival_defeat_dragon"} else "minecraft:end_portal_frame"}
    if stage.skill == "survival_exit_end":
        player.native_screen = "WinScreen"


class EndPortalExampleContracts(unittest.TestCase):
    def test_EP01_missing_capabilities_cause_no_game_calls(self):
        class NoCalls:
            def __getattr__(self, name): raise AssertionError(name)
        try:
            result = campaign.run_campaign(NoCalls(), default_registry())
        except ValueError:
            self.fail("Missing capabilities must return a blocked result before schema dispatch")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "missing_survival_skills")
        self.assertEqual(len(result["missing_skills"]), 11)

    def test_EP02_receipt_does_not_complete_a_stage(self):
        player = PlayerFixture()
        skills = registry(lambda ctx, stage: SkillResult(status="succeeded", reason="receipt", text="submitted"))
        result = campaign.run_campaign(player, skills)
        self.assertEqual(result["reason"], "postcondition_not_observed")
        self.assertEqual(result["completed"], [])
        self.assertTrue(player.paused)
        self.assertGreater(player.stops, 0)

    def test_EP03_all_postconditions_and_expected_dimension_transitions(self):
        player = PlayerFixture()
        def handler(ctx, stage):
            satisfy(ctx.player, stage)
            return SkillResult(status="succeeded", reason="fixture", text="Simulated postcondition")
        result = campaign.run_campaign(player, registry(handler))
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(len(result["completed"]), 11)
        self.assertEqual(result["reason"], "native_credits_observed")
        self.assertEqual(player.native_screen, "WinScreen")
        self.assertFalse(player.paused)

    def test_EP04_unexpected_actor_replacement_is_not_a_completed_goal(self):
        player = PlayerFixture()
        def handler(ctx, stage):
            satisfy(player, stage)
            player.scene["actor_session"] = "replacement"
            return SkillResult(status="succeeded", reason="fixture", text="Simulated")
        result = campaign.run_campaign(player, registry(handler))
        self.assertEqual(result["reason"], "actor_changed_or_dead")
        self.assertEqual(result["completed"], [])

    def test_EP05_cancel_deadline_and_invalid_budget(self):
        skills = registry(lambda ctx, stage: self.fail("No stage may execute"))
        event = threading.Event()
        event.set()
        self.assertEqual(campaign.run_campaign(PlayerFixture(), skills, cancel=event)["status"], "cancelled")
        ticks = iter([0., 1000.])
        self.assertEqual(campaign.run_campaign(PlayerFixture(), skills, clock=lambda: next(ticks, 1000.))["status"], "timed_out")
        for value in [True, float("nan"), 0, 601]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                campaign.run_campaign(PlayerFixture(), skills, duration_seconds=value)

    def test_EP06_far_sight_and_portal_frame_are_not_active_portal_success(self):
        player = PlayerFixture()
        player.scene["sight_target"] = {"id": "minecraft:end_portal", "position": [0, 64, 2]}
        self.assertFalse(campaign.near_block(player.scene, "minecraft:end_portal"))
        player.scene["target"] = {"kind": "block", "id": "minecraft:end_portal_frame", "position": [0, 64, 2]}
        self.assertFalse(campaign.near_block(player.scene, "minecraft:end_portal"))
        player.scene["target"].update(id="minecraft:end_portal", position=[100, 64, 2])
        self.assertFalse(campaign.near_block(player.scene, "minecraft:end_portal"))

    def test_EP08_no_pause_releases_controls_on_block_cancel_and_failure(self):
        for status in ["blocked", "failed", "cancelled", "timed_out"]:
            with self.subTest(status=status):
                player = PlayerFixture()
                skills = registry(lambda ctx, stage: SkillResult(status=status, reason="fixture", text="Simulated stop"))
                result = campaign.run_campaign(player, skills, pause_on_stop=False)
                self.assertEqual(result["status"], status)
                self.assertEqual(result["cleanup"], "released")
                self.assertGreater(player.stops, 0)
                self.assertFalse(player.paused)

    def test_EP09_portal_and_provider_assertions_do_not_complete_the_game(self):
        player = PlayerFixture()
        def handler(ctx, stage):
            satisfy(player, stage)
            if stage.skill == "survival_exit_end":
                player.native_screen = None
                player.scene["completion_screen_type"] = "WinScreen"  # Forged scene claim.
            return SkillResult(status="succeeded", reason="game_won", text="Not proof")
        result = campaign.run_campaign(player, registry(handler), pause_on_stop=False)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "postcondition_not_observed")
        self.assertEqual(result["stage"], "survival_exit_end")
        self.assertEqual(len(result["completed"]), 10)
        self.assertFalse(player.paused)

    def test_EP10_completion_without_scripted_pause_and_unchanged_bounds(self):
        player = PlayerFixture()
        def handler(ctx, stage):
            satisfy(player, stage)
            return SkillResult(status="succeeded", reason="fixture", text="Simulated")
        result = campaign.run_campaign(player, registry(handler), pause_on_stop=False)
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["goal"], "defeat_dragon_and_reach_credits")
        self.assertFalse(player.paused)
        self.assertEqual(result["cleanup"], "released")
        self.assertGreater(player.stops, 0)

    def test_EP11_no_pause_never_silently_resumes_an_existing_pause(self):
        player = PlayerFixture()
        player.paused = True
        skills = registry(lambda ctx, stage: self.fail("No action while paused"))
        result = campaign.run_campaign(player, skills, pause_on_stop=False)
        self.assertEqual(result["reason"], "unexpected_pause_screen")
        self.assertEqual(result["completed"], [])
        self.assertEqual(player.stops, 0)
        self.assertTrue(player.paused)
        with self.assertRaises(ValueError):
            campaign.run_campaign(player, skills, pause_on_stop="false")

    def test_EP12_final_goal_plan_does_not_stop_at_the_portal(self):
        roadmap = campaign.plan()
        self.assertEqual(roadmap["goal"], "defeat_dragon_and_reach_credits")
        self.assertEqual(roadmap["final_pause_policy"], "no_scripted_pause")
        self.assertEqual([s["skill"] for s in roadmap["stages"]][-3:],
                         ["survival_enter_end", "survival_defeat_dragon", "survival_exit_end"])

    def test_EP13_wood_no_pause_cli_releases_without_opening_pause_menu(self):
        outcome = SkillResult(status="blocked", reason="fixture", text="No wood", cleanup="released")
        for no_pause in [False, True]:
            with self.subTest(no_pause=no_pause), patch.object(campaign.Bridge, "from_env"), patch.object(campaign, "Player") as player, patch.object(campaign, "run_skill", return_value=outcome), redirect_stdout(io.StringIO()):
                player.return_value.observe.return_value = {"in_world": True}
                player.return_value.menu.return_value = {"screen_open": False}
                args = ["--gather-wood", "1"] + (["--no-pause"] if no_pause else [])
                self.assertEqual(campaign.main(args), 2)
                self.assertEqual(player.return_value.open_pause.call_count, 0 if no_pause else 1)

    def test_EP14_cancellation_during_final_observation_cannot_report_completion(self):
        player, event = PlayerFixture(), threading.Event()
        original_inventory = player.inventory
        def inventory():
            if player.native_screen == "WinScreen":
                event.set()
            return original_inventory()
        player.inventory = inventory
        def handler(ctx, stage):
            satisfy(player, stage)
            return SkillResult(status="succeeded", reason="fixture", text="Simulated")
        result = campaign.run_campaign(player, registry(handler), pause_on_stop=False, cancel=event)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(len(result["completed"]), 10)
        self.assertEqual(result["cleanup"], "released")
        self.assertFalse(player.paused)

    def test_EP15_nether_then_return_then_crafting_order(self):
        names = [stage.skill for stage in campaign.STAGES]
        self.assertEqual(names[1:6], [
            "survival_enter_nether", "survival_collect_blaze_rods",
            "survival_collect_ender_pearls", "survival_return_overworld",
            "survival_craft_eyes"])
        stages = {s.skill: s for s in campaign.STAGES}
        self.assertEqual(stages["survival_collect_blaze_rods"].dimension_before, "minecraft:the_nether")
        self.assertEqual(stages["survival_collect_ender_pearls"].dimension_after, "minecraft:the_nether")
        self.assertEqual(stages["survival_craft_eyes"].dimension_before, "minecraft:overworld")

    def test_EP16_wrong_dimension_blocks_before_native_actions(self):
        player = PlayerFixture()
        player.scene["dimension"] = "minecraft:the_nether"
        calls = []
        def handler(ctx, stage):
            calls.append(stage.skill)
            satisfy(player, stage)
            return SkillResult(status="succeeded", reason="fixture", text="Simulated")
        result = campaign.run_campaign(player, registry(handler), pause_on_stop=False)
        self.assertEqual(result["reason"], "stage_dimension_mismatch")
        self.assertEqual(result["stage"], "survival_prepare_overworld")
        self.assertEqual(result["expected_dimension"], "minecraft:overworld")
        self.assertFalse(calls)
        self.assertEqual(player.stops, 0)

    def test_EP17_rods_in_wrong_dimension_are_not_a_nether_stage_outcome(self):
        player = PlayerFixture()
        def handler(ctx, stage):
            satisfy(player, stage)
            if stage.skill == "survival_collect_blaze_rods":
                # Deliberately retain the token to exercise the dimension check itself.
                player.scene["dimension"] = "minecraft:overworld"
            return SkillResult(status="succeeded", reason="fixture", text="Simulated")
        result = campaign.run_campaign(player, registry(handler), pause_on_stop=False)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "postcondition_not_observed")
        self.assertEqual(result["stage"], "survival_collect_blaze_rods")
        self.assertEqual(len(result["completed"]), 2)

    def test_EP18_statistics_are_attached_without_inventing_live_counters(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'player-statistics.json'
            path.write_text('{"stats":{"minecraft:custom":{"minecraft:deaths":2}}}')
            output = io.StringIO()
            with patch.object(campaign.Bridge, 'from_env', side_effect=AssertionError('No game connection')), redirect_stdout(output):
                self.assertEqual(campaign.main(['--run', '--stats-file', str(path)]), 2)
            result = json.loads(output.getvalue())
            self.assertEqual(result['reason'], 'missing_survival_skills')
            self.assertEqual(result['statistics']['totals']['deaths'], 2)
            self.assertEqual(result['statistics']['run_delta']['deaths'], 0)
            self.assertTrue(result['statistics']['snapshots_identical'])
            self.assertEqual(result['statistics']['freshness'], 'saved_only_not_live_verified')
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(campaign.main(['--run', '--stats-file', str(path.parent/'missing.json')]), 2)
            self.assertIsNone(json.loads(output.getvalue())['statistics']['totals'])

    def test_EP07_cli_plan_and_stock_run_never_connect(self):
        with patch.object(campaign.Bridge, "from_env", side_effect=AssertionError("No connection")), redirect_stdout(io.StringIO()):
            self.assertEqual(campaign.main(["--plan"]), 0)
            self.assertEqual(campaign.main(["--run"]), 2)


if __name__ == "__main__":
    unittest.main()
