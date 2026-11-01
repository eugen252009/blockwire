#!/usr/bin/env python3
"""Finalize retained timed-rotation evidence without opening Minecraft or replaying input."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
ROTATION_RUNS = {
    "legacy": "legacy-v1",
    "linear": "linear-v2",
    "smoothstep": "smoothstep-v2",
    "final_source_smoke": "smoothstep-final-smoke-v3",
}
FULL_PROFILES = ("linear", "smoothstep")
ROTATION_SOURCE_PATHS = (
    "python/src/blockwire/skills/motion.py",
    "python/src/blockwire/client.py",
    "src/main/java/dev/blockwire/Blockwire.java",
    "src/main/java/dev/blockwire/Protocol.java",
    "src/main/java/dev/blockwire/RotationController.java",
    "src/main/java/dev/blockwire/MotionTrace.java",
    "tests/rotation/reference.py",
    "tests/rotation/live.py",
    "tests/rotation/metrics.py",
)


def read(path: Path):
    return json.loads(path.read_text())


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_files(directory: Path):
    pattern = re.compile(r".+-[0-9]{2}\.json$")
    return sorted(path for path in directory.iterdir() if pattern.fullmatch(path.name))


def wilson(successes: int, total: int, z: float = 1.959963984540054):
    if not total:
        return [None, None]
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [centre - margin, centre + margin]


def stats(values):
    values = [value for value in values if value is not None]
    if not values:
        return None
    return {
        "count": len(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def artifact_set(directory: Path):
    files = sorted([*directory.glob("*.json"), *directory.glob("*.csv")], key=lambda p: p.name)
    entries = [f"{sha(path)}  {path.name}" for path in files]
    return {
        "files": len(files),
        "json_files": sum(path.suffix == ".json" for path in files),
        "csv_files": sum(path.suffix == ".csv" for path in files),
        "sha256": hashlib.sha256(("\n".join(entries) + "\n").encode()).hexdigest(),
        "summary_sha256": sha(directory / "summary.json"),
        "ended_world_manifest_sha256": sha(directory / "ended-world.manifest.json"),
    }


def classify(row):
    scenario = row["scenario"]
    name = scenario["name"]
    labels = []
    if scenario.get("movement"):
        labels.append("moving")
    else:
        labels.append("stationary")
    if scenario.get("cancel_after_ms") is not None:
        labels.append("cancellation")
    if scenario.get("supersede_after_ms") is not None:
        labels.append("supersession")
    if scenario.get("sequence"):
        labels.append("sequence")
    if "wrap" in name:
        labels.append("wraparound")
    if "combined" in name:
        labels.append("combined_axes")
    if name.startswith("pitch_"):
        labels.append("pitch_only")
    return labels


def rotation_run(directory: Path):
    summary = read(directory / "summary.json")
    rows = [read(path) for path in run_files(directory)]
    if len(rows) != summary["runs"]:
        raise ValueError(f"{directory.name}: raw/summary run count mismatch")
    successes = sum(bool(row["metrics"]["success"]) for row in rows)
    if successes != summary["successes"]:
        raise ValueError(f"{directory.name}: raw/summary success mismatch")

    def duration_applicable(row):
        recorded = row["metrics"].get("duration_applicable")
        if recorded is not None:
            return bool(recorded)
        return row["scenario"].get("cancel_after_ms") is None and row["metrics"].get("angular_extent_degrees", 0.0) > .5

    applicable = [row for row in rows if duration_applicable(row)]
    completion_rows = [row for row in rows if row["scenario"].get("cancel_after_ms") is None]
    categories = defaultdict(list)
    for row in rows:
        for label in classify(row):
            categories[label].append(row)

    duration_groups = {}
    for duration in (100, 200, 400):
        group = [row for row in applicable if row["metrics"]["requested_duration_ms"] == duration]
        duration_groups[str(duration)] = {
            "runs": len(group),
            "within_tolerance": sum(bool(row["metrics"].get("duration_within_tolerance")) for row in group),
            "actual_duration_ms": stats(row["metrics"]["actual_duration_ms"] for row in group),
            "duration_error_ms": stats(row["metrics"]["duration_error_ms"] for row in group),
            "absolute_duration_error_ms": stats(abs(row["metrics"]["duration_error_ms"]) for row in group if row["metrics"]["duration_error_ms"] is not None),
            "max_angular_step_degrees": stats(row["metrics"]["max_angular_step_degrees"] for row in group),
            "trajectory_rmse_degrees": stats(row["metrics"]["trajectory_rmse_degrees"] for row in group),
        }

    category_report = {}
    for name, group in sorted(categories.items()):
        category_report[name] = {
            "runs": len(group),
            "successes": sum(bool(row["metrics"]["success"]) for row in group),
            "full_stop_runs": sum(row["metrics"].get("full_stop_runs", 0) for row in group),
            "input_changes": sum(row["metrics"].get("input_changes", 0) for row in group),
            "trace_dropped_samples": sum(row.get("trace_dropped_samples", 0) for row in group),
        }
        if name == "cancellation":
            category_report[name]["stable"] = sum(bool(row["metrics"].get("cancellation_stable")) for row in group)

    failures = [
        {
            "scenario": row["scenario"]["name"],
            "repeat": row["repeat"],
            "terminal_status": row["outcome"].get("terminal_status"),
            "final_yaw_error": row["metrics"]["final_yaw_error"],
            "final_pitch_error": row["metrics"]["final_pitch_error"],
            "duration_error_ms": row["metrics"].get("duration_error_ms"),
        }
        for row in rows if not row["metrics"]["success"]
    ]
    aggregate = {
        "runs": len(rows),
        "successes": successes,
        "success_rate": successes / len(rows),
        "success_wilson_95": wilson(successes, len(rows)),
        "duration_applicable_runs": len(applicable),
        "duration_within_tolerance": sum(bool(row["metrics"].get("duration_within_tolerance")) for row in applicable),
        "instant_snaps": sum(bool(row["metrics"].get("instant_snap_observed")) for row in rows),
        "final_yaw_error": stats(abs(row["metrics"]["final_yaw_error"]) for row in rows),
        "final_pitch_error": stats(abs(row["metrics"]["final_pitch_error"]) for row in rows),
        "completion_final_yaw_error": stats(abs(row["metrics"]["final_yaw_error"]) for row in completion_rows),
        "completion_final_pitch_error": stats(abs(row["metrics"]["final_pitch_error"]) for row in completion_rows),
        "max_angular_step_degrees": stats(row["metrics"]["max_angular_step_degrees"] for row in rows),
        "max_overshoot_degrees": stats(row["metrics"].get("max_overshoot_degrees", 0.0) for row in rows),
        "trajectory_rmse_degrees": stats(row["metrics"]["trajectory_rmse_degrees"] for row in applicable),
        "tick_interval_ms": stats(row["metrics"]["tick_interval_ms_median"] for row in rows),
        "trace_dropped_samples": sum(row.get("trace_dropped_samples", 0) for row in rows),
    }
    return {
        "id": directory.name,
        "variant": summary["metadata"]["variant"],
        "metadata": summary["metadata"],
        "aggregate": aggregate,
        "duration_ms": duration_groups,
        "categories": category_report,
        "failures": failures,
        "artifacts": artifact_set(directory),
    }


def movement_regression(root: Path, current_source):
    summary = read(root / "summary.json")
    rows = [read(path) for path in run_files(root)]
    metrics = [row["metrics"] for row in rows]
    source = summary["metadata"]["source_sha256"]
    return {
        "id": root.name,
        "runs": len(rows),
        "successes": sum(bool(row["metrics"]["success"]) for row in rows),
        "fixture_identity": summary["metadata"]["fixture_identity"],
        "scenario_identity": summary["metadata"]["scenario_identity"],
        "minecraft_version": summary["metadata"]["minecraft_version"],
        "game_ticks_total": sum(row["game_ticks"] for row in metrics),
        "game_ticks_median": statistics.median(row["game_ticks"] for row in metrics),
        "full_stop_runs": sum(row["full_stop_runs"] for row in metrics),
        "input_changes": sum(row["input_changes"] for row in metrics),
        "max_horizontal_error": max(row["target_horizontal_error"] for row in metrics),
        "health_loss": sum(row["health_loss"] for row in metrics),
        "all_settled_at_end": all(row["settled_at_end"] for row in metrics),
        "trace_dropped_samples": sum(row.get("trace_dropped_samples", 0) for row in rows),
        "source_sha256": source,
        "source_matches_current": all(Path(path).exists() and sha(Path(path)) == digest for path, digest in source.items()),
        "summary_sha256": sha(root / "summary.json"),
    }


def building_regression(path: Path):
    result = read(path)
    verification = result["verification"]
    return {
        "id": result["metadata"]["test_id"],
        "scope": result["metadata"]["scope"],
        "fixture_identity": result["metadata"]["snapshot_identity"],
        "passed": result["passed"],
        "objective_verified": result["objective_verified"],
        "elapsed_seconds": result["elapsed_seconds"],
        "executed_operations": result["executed_operations"],
        "verified_native_placement_events": result["verified_native_placement_events"],
        "failed_actions": result["failed_actions"],
        "ended_snapshot_identity": result["ended_snapshot_identity"],
        "verification": {key: verification.get(key) for key in (
            "expected_blocks", "verified_blocks", "incorrect_blocks", "missing_blocks", "unknown_blocks",
            "entrance_clear", "interior_clear", "interior_accessible", "roof_complete", "floor_intact",
            "safe_player", "objective_verified",
        )},
        "result_sha256": sha(path),
    }


def retained_failure(path: Path):
    result = read(path)
    failure = result.get("failure") or {}
    response = failure.get("result", {}).get("result", {}) if isinstance(failure.get("result"), dict) else {}
    history = response.get("history", []) if isinstance(response, dict) else []
    return {
        "id": result["metadata"]["test_id"],
        "passed": result["passed"],
        "executed_operations": result.get("executed_operations"),
        "verified_native_placement_events": result.get("verified_native_placement_events"),
        "failed_actions": result.get("failed_actions"),
        "failure": {
            "layer": failure.get("layer"),
            "frame": failure.get("frame"),
            "type": failure.get("type"),
            "reason": failure.get("reason") or response.get("reason"),
            "terminal_action_reason": history[-1].get("reason") if history else None,
        },
        "verified_blocks": result.get("verification", {}).get("verified_blocks"),
        "result_sha256": sha(path),
    }


def mutation_report(path: Path):
    rows = read(path)
    return {
        "total": len(rows),
        "killed": sum(row["status"] == "KILLED" for row in rows),
        "all_killed": all(row["status"] == "KILLED" for row in rows),
        "sha256": sha(path),
    }


def qa_report(root: Path):
    python_log = root / "python.log"
    gradle_log = root / "gradle.log"
    python_text = python_log.read_text()
    gradle_text = gradle_log.read_text()
    match = re.search(r"Ran ([0-9]+) tests", python_text)
    mutation_paths = {
        "skills": root / "skill-mutations/results.json",
        "native": root / "mutations/results.json",
        "controller": root / "controller-mutations/results.json",
        "building": root / "building-mutations/results.json",
    }
    mutations = {name: mutation_report(path) for name, path in mutation_paths.items()}
    tls = read(root / "tls/interop.json")
    return {
        "python": {"tests": int(match.group(1)) if match else None, "passed": "\nOK\n" in python_text, "sha256": sha(python_log)},
        "gradle": {"passed": "BUILD SUCCESSFUL" in gradle_text, "sha256": sha(gradle_log)},
        "tls": tls,
        "mutations": mutations,
        "mutation_total": sum(row["total"] for row in mutations.values()),
        "all_mutations_killed": all(row["all_killed"] for row in mutations.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rotation-root", type=Path, default=Path("build/rotation-benchmark"))
    parser.add_argument("--movement-root", type=Path, default=Path("build/movement-benchmark/after-rotation-v4"))
    parser.add_argument("--building-result", type=Path, default=Path("build/superflat-benchmark/A19/result.json"))
    parser.add_argument("--verification-root", type=Path, default=Path("build/rotation-benchmark/final-verification"))
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/rotation-benchmark.json"))
    args = parser.parse_args()

    runs = {name: rotation_run(args.rotation_root / run_id) for name, run_id in ROTATION_RUNS.items()}
    identities = {
        (runs[name]["metadata"]["fixture_identity"], runs[name]["metadata"]["scenario_identity"],
         runs[name]["metadata"]["minecraft_version"])
        for name in ("legacy", *FULL_PROFILES)
    }
    current_source = {path: sha(Path(path)) for path in ROTATION_SOURCE_PATHS}
    full_native_paths = tuple(path for path in ROTATION_SOURCE_PATHS if path != "python/src/blockwire/skills/motion.py")
    native_source_match = all(
        runs[name]["metadata"]["source_sha256"].get(path) == current_source[path]
        for name in FULL_PROFILES for path in full_native_paths
    )
    final_smoke_source_match = runs["final_source_smoke"]["metadata"]["source_sha256"] == current_source

    movement = movement_regression(args.movement_root, current_source)
    prior_movement = movement_regression(Path("build/movement-benchmark/after-v4"), current_source)
    movement["versus_pre_rotation_after_v4"] = {
        "game_ticks_change": (movement["game_ticks_total"] - prior_movement["game_ticks_total"]) / prior_movement["game_ticks_total"],
        "full_stop_runs_change": (movement["full_stop_runs"] - prior_movement["full_stop_runs"]) / prior_movement["full_stop_runs"],
        "input_changes_change": (movement["input_changes"] - prior_movement["input_changes"]) / prior_movement["input_changes"],
    }
    building = building_regression(args.building_result)
    retained = [retained_failure(Path(f"build/superflat-benchmark/{run}/result.json")) for run in ("A16", "A17", "A18")]
    qa = qa_report(args.verification_root)
    final_client = read(args.rotation_root / "final-client.json")
    qa["final_client"] = {**final_client, "sha256": sha(args.rotation_root / "final-client.json")}

    smooth = runs["smoothstep"]
    linear = runs["linear"]
    profile_gates = {}
    for name in FULL_PROFILES:
        run = runs[name]
        cancellation = run["categories"]["cancellation"]
        moving = run["categories"]["moving"]
        profile_gates[name] = {
            "all_150_runs_pass": run["aggregate"]["runs"] == 150 == run["aggregate"]["successes"],
            "all_applicable_durations_within_tolerance": run["aggregate"]["duration_applicable_runs"] == 141 == run["aggregate"]["duration_within_tolerance"],
            "zero_instant_snaps": run["aggregate"]["instant_snaps"] == 0,
            "endpoint_errors_at_most_0_25_degrees": run["aggregate"]["completion_final_yaw_error"]["max"] <= .25 and run["aggregate"]["completion_final_pitch_error"]["max"] <= .25,
            "zero_overshoot_within_float_precision": run["aggregate"]["max_overshoot_degrees"]["max"] <= 1e-9,
            "moving_runs_pass_without_full_stops": moving["successes"] == moving["runs"] and moving["full_stop_runs"] == 0,
            "cancellation_is_stable": cancellation["stable"] == cancellation["runs"],
            "no_dropped_tick_telemetry": run["aggregate"]["trace_dropped_samples"] == 0,
        }
    rotation_gates = {
        "identical_full_fixture_scenarios_and_version": len(identities) == 1,
        "linear_profile": all(profile_gates["linear"].values()),
        "smoothstep_profile": all(profile_gates["smoothstep"].values()),
        "current_native_rotation_sources_match_full_profiles": native_source_match,
        "final_source_smoke_8_of_8_and_hash_match": (
            runs["final_source_smoke"]["aggregate"]["runs"] == 8 == runs["final_source_smoke"]["aggregate"]["successes"]
            and runs["final_source_smoke"]["aggregate"]["duration_applicable_runs"] == 7
            and runs["final_source_smoke"]["aggregate"]["duration_within_tolerance"] == 7
            and runs["final_source_smoke"]["aggregate"]["instant_snaps"] == 0
            and final_smoke_source_match
        ),
        "python_gradle_tls_and_mutations_pass": (
            qa["python"]["passed"] and qa["gradle"]["passed"] and qa["tls"].get("status") == "PASS"
            and qa["all_mutations_killed"]
        ),
        "client_world_closed_and_process_exited": bool(
            final_client.get("world_saved_and_closed") and not final_client.get("in_world")
            and final_client.get("client_process_exited_after_native_quit")
            and final_client.get("owned_launcher_wrappers_terminated")
            and final_client.get("bridge_port_closed")
        ),
    }
    movement_gates = {
        "same_fixed_fixture_and_scenarios": (
            movement["fixture_identity"] == prior_movement["fixture_identity"]
            and movement["scenario_identity"] == prior_movement["scenario_identity"]
            and movement["minecraft_version"] == prior_movement["minecraft_version"]
        ),
        "all_211_repetitions_pass": movement["runs"] == 211 == movement["successes"],
        "max_error_at_most_0_3": movement["max_horizontal_error"] <= .3,
        "zero_health_loss": movement["health_loss"] == 0.0,
        "settled_without_trace_loss": movement["all_settled_at_end"] and movement["trace_dropped_samples"] == 0,
        "qualified_sources_match_current": movement["source_matches_current"],
    }
    building_verification = building["verification"]
    building_gates = {
        "fresh_closed_snapshot_run": building["scope"] == "Fresh restored-snapshot trial",
        "objective_verified": building["passed"] and building["objective_verified"],
        "all_71_required_blocks": building_verification["expected_blocks"] == 71 == building_verification["verified_blocks"],
        "no_wrong_missing_or_unknown_required_blocks": all(building_verification[key] == 0 for key in ("incorrect_blocks", "missing_blocks", "unknown_blocks")),
        "access_clearance_roof_floor_and_safe_player": all(building_verification[key] for key in (
            "entrance_clear", "interior_clear", "interior_accessible", "roof_complete", "floor_intact", "safe_player")),
        "zero_failed_actions": building["failed_actions"] == 0,
    }

    fixture_identity, scenario_identity, version = next(iter(identities)) if len(identities) == 1 else (None, None, None)
    source_paths = [
        *map(Path, ROTATION_SOURCE_PATHS),
        Path("python/src/blockwire/skills/item_actions.py"),
        Path("python/src/blockwire/skills/walking.py"),
        Path("tools/rotation_benchmark.py"),
        Path("tools/report_rotation_benchmark.py"),
        Path("python/tests/test_rotation.py"),
        Path("python/tests/test_rotation_benchmark.py"),
        Path("python/tests/test_continuous_motion.py"),
        Path("python/tests/test_placement.py"),
        Path("python/tests/test_controller.py"),
        Path("src/contractTest/java/dev/blockwire/RotationContractTest.java"),
        Path("src/contractTest/java/dev/blockwire/ControllerContractTest.java"),
        Path("tests/run_skill_mutations.py"),
        Path("tests/run_mutations.py"),
        Path("docs/rotation-benchmark.md"),
    ]
    document = {
        "schema_version": 1,
        "scope": "Minecraft 26.3 native timed-camera qualification plus unchanged movement and deterministic construction regressions; no LLM calls in rotation/movement.",
        "architecture": "goal -> existing Python skills -> one actor-bound native RotationController and ordinary input leases -> Minecraft tick updates -> bounded telemetry",
        "fixture": {
            "identity": fixture_identity,
            "scenario_identity": scenario_identity,
            "minecraft_version": version,
            "full_scenarios": 50,
            "repetitions_per_profile": 150,
            "restore_policy": "Each independent cohort restores and byte-validates the same owned closed snapshot.",
        },
        "acceptance": {
            "duration_tolerance_ms": "max(75, requested_duration * 0.35)",
            "endpoint_tolerance_degrees": .25,
            "instant_snap_detector": "For arcs > 5 degrees, one tick may not consume >= 80% of the requested arc.",
            "note": "Receipts never substitute for terminal native rotation state, endpoint orientation, cancellation stability or tick traces.",
        },
        "assessments": {
            "rotation": {"decision": "GO" if all(rotation_gates.values()) else "NO-GO", "gates": rotation_gates, "profile_gates": profile_gates},
            "movement": {"decision": "GO" if all(movement_gates.values()) else "NO-GO", "gates": movement_gates},
            "building": {"decision": "GO" if all(building_gates.values()) else "NO-GO", "gates": building_gates},
            "historical_superflat_test_B": {"decision": "NO-GO", "meaning": "Unchanged historical assessment; this regression does not rerun or relabel B01."},
            "historical_native_movement_parity": {"decision": "NO-GO", "meaning": "Unchanged historical strict tick-parity assessment; correctness regression GO is separate."},
        },
        "rotation_runs": runs,
        "profile_comparison": {
            "selected_default": "smoothstep",
            "selection_reason": "Both profiles meet all gates; smoothstep retains zero-slope eased endpoints while linear remains explicitly selectable.",
            "linear_trajectory_rmse_median_degrees": linear["aggregate"]["trajectory_rmse_degrees"]["median"],
            "smoothstep_trajectory_rmse_median_degrees": smooth["aggregate"]["trajectory_rmse_degrees"]["median"],
        },
        "legacy_comparison": {
            "legacy_successes": runs["legacy"]["aggregate"]["successes"],
            "legacy_runs": runs["legacy"]["aggregate"]["runs"],
            "legacy_duration_within_tolerance": runs["legacy"]["aggregate"]["duration_within_tolerance"],
            "legacy_duration_applicable_runs": runs["legacy"]["aggregate"]["duration_applicable_runs"],
            "legacy_failures": runs["legacy"]["failures"],
        },
        "movement_regression": movement,
        "pre_rotation_movement_reference": prior_movement,
        "building_regression": building,
        "retained_building_failures": retained,
        "qa": qa,
        "qualified_rotation_source_sha256": current_source,
        "artifact_sha256": {
            str(path): sha(path) for path in (
                args.rotation_root / "legacy-v1/summary.json",
                args.rotation_root / "linear-v2/summary.json",
                args.rotation_root / "smoothstep-v2/summary.json",
                args.rotation_root / "smoothstep-final-smoke-v3/summary.json",
                args.movement_root / "summary.json",
                args.building_result,
                args.rotation_root / "final-client.json",
                Path("build/libs/blockwire-0.2.0-alpha.4.jar"),
            )
        },
        "source_sha256": {str(path): sha(path) for path in source_paths},
        "limitations": [
            "One owned deterministic Minecraft 26.3 fixture; this is not general renderer, server or mod-pack qualification.",
            "Requested durations are quantized by actual client ticks; tolerance is explicit and does not promise sub-tick completion.",
            "Combat camera behavior remains separate and was intentionally not migrated by this work.",
            "Movement still does not qualify slabs, fluids, caves, arbitrary collision shapes or hostile unattended Survival.",
            "Construction A19 is a fresh regression, not a replacement for the frozen A11-A13 Test-A cohort or a Test-B rerun.",
            "A16, A17 and A18 remain failures; no debug continuation is counted as a fresh success.",
            "No release, upload or production deployment is authorized by this evidence.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n")
    print(json.dumps({
        "assessments": document["assessments"],
        "rotation": {name: (runs[name]["aggregate"]["successes"], runs[name]["aggregate"]["runs"]) for name in FULL_PROFILES},
        "movement": (movement["successes"], movement["runs"]),
        "building": (building["verification"]["verified_blocks"], building["verification"]["expected_blocks"]),
        "mutation_total": qa["mutation_total"],
    }, indent=2))


if __name__ == "__main__":
    main()
