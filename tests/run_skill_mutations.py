#!/usr/bin/env python3
"""Isolated Python skill mutations; no live game, secrets or working-source changes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("BLOCKWIRE_VERIFICATION_DIR", ROOT / "build/skills-verification")) / "skill-mutations"
OUT.mkdir(parents=True, exist_ok=True)
mutations = [
    ("continuous_approach_small_progress", "approaching.py", "            previous = position[:]  # Accumulate",
     "        previous = position[:]  # Accumulate",
     "test_CM13_small_advances_accumulate_at_the_faster_feedback_cadence"),
    ("continuous_autopilot_small_progress", "autopilot.py", "                last_position = position[:]  # Accumulate",
     "            last_position = position[:]  # Accumulate",
     "test_CM13_small_advances_accumulate_at_the_faster_feedback_cadence"),
    ("continuous_sustained", "motion.py", "keep_held = (rolling and self.holding",
     "keep_held = (False and rolling and self.holding",
     "test_CM02_forward_is_held_during_observation_steering_and_renewal"),
    ("continuous_lease_bound", "motion.py", "LEASE_TICKS = 8", "LEASE_TICKS = 16",
     "test_CM03_controller_stall_does_not_extend_native_lease"),
    ("continuous_turn_release", "motion.py", "STEERING_DEGREES = 4.", "STEERING_DEGREES = 180.",
     "test_CM04_small_steering_overlaps_but_large_turn_releases_first"),
    ("continuous_uncertainty_stop", "motion.py", "if self.holding:\n            self.halt(context)",
     "if False:\n            self.halt(context)",
     "test_CM05_uncertain_route_readiness_and_replacement_stop_before_renewal"),
    ("continuous_approach_enabled", "approaching.py", 'view=(scene["yaw"], scene["pitch"]), continuous=True)',
     'view=(scene["yaw"], scene["pitch"]), continuous=False)',
     "test_CM11_autopilot_and_approach_share_real_rolling_integration"),
    ("continuous_autopilot_enabled", "autopilot.py", 'view=view, continuous=behavior == "travel")',
     "view=view, continuous=False)",
     "test_CM11_autopilot_and_approach_share_real_rolling_integration"),
    ("continuous_no_corner_shortcut", "motion.py",
     "if (path[i][0]-path[i-1][0], path[i][2]-path[i-1][2]) != (dx, dz) or path[i][1] != path[0][1]:",
     "if False:", "test_CM09_collinear_lookahead_never_shortcuts_a_corner_gap_or_offcenter_axis"),
    ("continuous_lateral_margin", "motion.py", "if lateral > .06:", "if False:",
     "test_CM09_collinear_lookahead_never_shortcuts_a_corner_gap_or_offcenter_axis"),
    ("continuous_arrival_after_release", "autopilot.py", "if motion.holding:", "if False:",
     "test_CM08_autopilot_reobserves_arrival_after_releasing_a_rolling_lease"),
    ("continuous_observed_speed", "motion.py", "bound = max(nominal*2.5, self._peak_step*1.5)",
     "bound = nominal*2.5", "test_CM10_observed_speed_jump_stops_rolling_instead_of_blind_renewal"),
    ("approach_shortest_yaw", "motion.py", "return (target-current+180) % 360-180", "return target-current",
     "test_AR19_turn_uses_shortest_yaw_arc_and_accepts_unwrapped_observations"),
    ("approach_strafe_key_direction", "motion.py", "motion_yaw-offset+180", "motion_yaw+offset+180",
     "test_AR16_forward_travel_and_only_tiny_aligned_strafe_corrections"),
    ("approach_strafe_only_near", "motion.py", "if distance < .35:", "if True:",
     "test_AR16_forward_travel_and_only_tiny_aligned_strafe_corrections"),
    ("approach_strafe_alignment", "motion.py", "if abs(_yaw_delta(camera_yaw, current_yaw)) <= 8.:", "if True:",
     "test_AR16_forward_travel_and_only_tiny_aligned_strafe_corrections"),
    ("approach_primary_forward", "motion.py", 'return (motion_yaw+180) % 360-180, ("forward",)',
     'return (motion_yaw+180) % 360-180, ("back",)',
     "test_AR16_forward_travel_and_only_tiny_aligned_strafe_corrections"),
    ("approach_checkpoint_pulses", "approaching.py", "unconfirmed_pulses >= TARGET_CHECK_PULSES", "False",
     "test_AR20_out_of_view_travel_uses_bounded_checkpoints_and_forward"),
    ("approach_checkpoint_time", "approaching.py", "context.clock()-confirmed_at >= TARGET_CHECK_SECONDS", "False",
     "test_AR24_elapsed_unconfirmed_time_checks_before_another_drive"),
    ("approach_no_stale_confirmation", "approaching.py", 'if updated is None and not _sighted(scene.get("sight_target", {}), selected):',
     'if updated is None and not _matches(scene.get("target", {}), selected):',
     "test_AR25_stale_native_crosshair_cannot_reset_target_checkpoint_budget"),
    ("approach_bounded_turn", "motion.py", "8./extent", "180./extent",
     "test_AR17_approach_camera_has_no_per_pulse_turn_back_and_bounded_steps"),
    ("approach_no_turn_back", "approaching.py", '        scene = observe()  # Keep the travel heading;',
     '        aim_at(state, selected, scene)\n        scene = observe()  # Keep the travel heading;',
     "test_AR17_approach_camera_has_no_per_pulse_turn_back_and_bounded_steps"),
    ("approach_no_drive_while_turning", "motion.py", "if self.turning:", "if False:",
     "test_AR18_actor_and_cancel_checked_during_turning_before_any_drive"),
    ("approach_centering_pulse", "motion.py",
     "ticks = lease if rolling else 1 if distance < .35 else min(max_ticks, max(1, math.floor(distance/speed)))",
     "ticks = lease if rolling else min(max_ticks, max(1, math.floor(distance/speed)))",
     "test_CM01_precision_near_actual_waypoint_remains_single_tick"),
    ("approach_progress_guard", "motion.py", "if self._no_progress >= 8:", "if False:",
     "test_AR15_oscillating_displacement_is_detected_as_no_progress"),
    ("approach_observed_reach", "approaching.py", 'if (_matches(scene.get("target", {}), selected)', "if (True",
     "test_AR05_native_crosshair_postcondition_not_distance_or_receipt"),
    ("approach_exact_native_position", "approaching.py", 'and hit.get("position") == selected["position"]', "and True",
     "test_AR05_native_crosshair_postcondition_not_distance_or_receipt"),
    ("approach_visible_override", "approaching.py", 'and (goal.position is None or row["position"] == goal.position)', "and True",
     "test_AR03_no_target_hidden_override_old_observation_and_no_route"),
    ("approach_session", "approaching.py", 'if state["actor_session"] != session:', "if False:",
     "test_AR07_actor_replacement_before_discovery_and_after_drive"),
    ("approach_target_loss", "approaching.py", 'if updated is None and not _sighted(scene.get("sight_target", {}), selected):', "if False:",
     "test_AR04_reobserve_target_loss_replacement_and_no_silent_retarget"),
    ("approach_damage_opt_out", "approaching.py", "avoid_damage=goal.avoid_damage, max_ticks=3,", "avoid_damage=True, max_ticks=3,",
     "test_AR08_damage_known_hazards_stuck_and_mesh_detour"),
    ("approach_no_use", "motion.py", "context.player.stop()\n        self.holding = False", 'context.player.action("use")\n        self.holding = False',
     "test_AR01_distant_visible_chest_frontier_arrival_aim_and_no_use"),
    ("autopilot_opt_in", "autopilot.py", "if creepers and goal.evade_creepers:", "if creepers:",
     "test_AP03_creeper_opt_in_priority_and_goal_resume"),
    ("autopilot_target", "autopilot.py", 'and hit.get("id") == enemy["entity_id"]', "and True",
     "test_AP05_defense_only_attacks_selected_native_target_without_pursuit"),
    ("autopilot_session", "autopilot.py", 'if state["actor_session"] != session:', "if False:",
     "test_AP07_lifecycle_damage_deadline_stuck_cleanup"),
    ("autopilot_escape_hazard", "autopilot.py", 'if cell["hazards"]:', "if False:",
     "test_AP04_escape_requires_increasing_distance_valid_edge_and_no_hazard"),
    ("autopilot_run", "motion.py", 'buttons.append("sprint")', "pass",
     "test_AP02_goal_walk_run_sneak_arrival_and_hole_detour"),
    ("hazard_filter", "walking.py", "if not (avoid_damage and cell[\"hazards\"])", "if True",
     "test_hazard_detour_and_opt_out"),
    ("observed_arrival", "walking.py", "if distance <= .3:", "if True:",
     "test_flat_arrival_is_observed_and_releases"),
    ("actor_identity", "walking.py", 'if session != state["actor_session"]:', "if False:",
     "test_session_replacement_stops_before_new_actor_input"),
    ("cleanup", "core.py", "                player.stop()", "                pass",
     "test_flat_arrival_is_observed_and_releases"),
    ("deadline", "core.py", "if self.clock() >= self.deadline:", "if False:",
     "test_stuck_and_timeout"),
    ("single_owner", "core.py", "if self._active is not None:", "if False:",
     "test_background_job_status_cancel_and_exclusive_control"),
]
results = []
for name, filename, before, after, expected in mutations:
    with tempfile.TemporaryDirectory(prefix="blockwire-skill-mutation-") as folder:
        copied = Path(folder) / "blockwire"
        shutil.copytree(ROOT / "python/src/blockwire", copied, ignore=shutil.ignore_patterns("__pycache__"))
        path = copied / "skills" / filename
        source = path.read_text()
        assert source.count(before) == 1
        path.write_text(source.replace(before, after))
        environment = dict(os.environ, PYTHONPATH=folder)
        run = subprocess.run([str(ROOT / ".venv/bin/python"), "-B", "-m", "unittest",
                              "discover", "-s", str(ROOT / "python/tests"), "-p", "test_*.py", "-v"],
                             env=environment, cwd=ROOT, text=True, capture_output=True, timeout=20)
        output = run.stdout + run.stderr
        (OUT / f"{name}.log").write_text(output)
        killed = run.returncode != 0 and f"FAIL: {expected}" in output
        results.append({"mutation": name, "status": "KILLED" if killed else ("SURVIVED" if run.returncode == 0 else "INCONCLUSIVE")})
(OUT / "results.json").write_text(json.dumps(results, indent=2)+"\n")
print(json.dumps(results, indent=2))
if not all(result["status"] == "KILLED" for result in results):
    raise SystemExit(1)
