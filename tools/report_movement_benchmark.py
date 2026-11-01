#!/usr/bin/env python3
"""Finalize retained movement benchmark evidence; never opens Minecraft or replays input."""
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
CANONICAL = {"native": "vanilla-v2", "before": "before-v1", "after": "after-v4"}
HISTORY = ("after-v1", "after-v2", "after-v3", "after-v4")
METRICS = ("game_ticks", "path_length", "target_horizontal_error", "full_stop_runs",
           "input_changes", "horizontal_collision_ticks", "health_loss", "max_horizontal_speed")


def read(path: Path):
    return json.loads(path.read_text())


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def change(current, baseline):
    return None if not baseline else (current-baseline)/baseline


def wilson(successes, total, z=1.959963984540054):
    if not total:
        return [None, None]
    p = successes/total
    denominator = 1+z*z/total
    centre = (p+z*z/(2*total))/denominator
    margin = z*math.sqrt((p*(1-p)+z*z/(4*total))/total)/denominator
    return [centre-margin, centre+margin]


def run_files(directory: Path):
    pattern = re.compile(r".+-[0-9]{2}\.json$")
    return sorted(path for path in directory.iterdir() if pattern.fullmatch(path.name))


def artifact_set(directory: Path):
    files = sorted([*directory.glob("*.json"), *directory.glob("*.csv")], key=lambda p: p.name)
    entries = [f"{sha(path)}  {path.name}" for path in files]
    return {"files": len(files), "json_files": sum(path.suffix == ".json" for path in files),
            "csv_files": sum(path.suffix == ".csv" for path in files),
            "sha256": hashlib.sha256(("\n".join(entries)+"\n").encode()).hexdigest(),
            "summary_sha256": sha(directory/"summary.json"),
            "ended_world_manifest_sha256": sha(directory/"ended-world.manifest.json")}


def compact_scenario(summary):
    result = {}
    for name, row in summary["scenarios"].items():
        result[name] = {"runs": row["runs"], "successes": row["successes"],
                        "success_rate": row["success_rate"],
                        **{key+"_median": row[key]["median"] for key in METRICS}}
    return result


def run_report(root: Path, run_id: str):
    directory = root/run_id
    summary = read(directory/"summary.json")
    rows = [read(path) for path in run_files(directory)]
    if len(rows) != summary["runs"]:
        raise ValueError(f"{run_id}: {len(rows)} raw runs != {summary['runs']} summary runs")
    if sum(bool(row["metrics"]["success"]) for row in rows) != summary["successes"]:
        raise ValueError(f"{run_id}: raw success count disagrees with summary")
    categories = defaultdict(list)
    for row in rows:
        categories[row["scenario"]["category"]].append(row["metrics"])
    aggregate = {"runs": len(rows), "successes": sum(row["metrics"]["success"] for row in rows),
                 "success_rate": sum(row["metrics"]["success"] for row in rows)/len(rows),
                 "success_wilson_95": wilson(sum(row["metrics"]["success"] for row in rows), len(rows)),
                 "trace_dropped_samples": sum(row.get("trace_dropped_samples", 0) for row in rows),
                 "all_settled_at_end": all(row["metrics"]["settled_at_end"] for row in rows),
                 "trace_profiles": sorted({row.get("trace_profile") for row in rows})}
    for key in METRICS:
        values = [row["metrics"][key] for row in rows]
        aggregate[key] = {"total": sum(values), "median": statistics.median(values),
                          "min": min(values), "max": max(values)}
    category_report = {}
    for name, values in sorted(categories.items()):
        category_report[name] = {"runs": len(values), "successes": sum(v["success"] for v in values),
                                 "game_ticks_total": sum(v["game_ticks"] for v in values),
                                 "game_ticks_median": statistics.median(v["game_ticks"] for v in values)}
    failures = [{"scenario": row["scenario"]["name"], "repeat": row["repeat"],
                 "skill_status": row["outcome"].get("status"), "skill_reason": row["outcome"].get("reason"),
                 "settled_horizontal_error": row["metrics"]["target_horizontal_error"],
                 "settled_vertical_error": row["metrics"]["target_vertical_error"],
                 "acceptance_radius": row["metrics"]["acceptance_radius"]}
                for row in rows if not row["metrics"]["success"]]
    return {"id": run_id, "variant": summary["metadata"]["variant"], "metadata": summary["metadata"],
            "aggregate": aggregate, "categories": category_report,
            "scenarios": compact_scenario(summary), "failures": failures,
            "artifacts": artifact_set(directory)}


def mutation_report(path: Path):
    rows = read(path)
    return {"total": len(rows), "killed": sum(row["status"] == "KILLED" for row in rows),
            "all_killed": all(row["status"] == "KILLED" for row in rows), "sha256": sha(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("build/movement-benchmark"))
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/movement-benchmark.json"))
    args = parser.parse_args()
    root = args.root
    runs = {name: run_report(root, run_id) for name, run_id in CANONICAL.items()}
    identities = {(run["metadata"]["fixture_identity"], run["metadata"]["scenario_identity"],
                   run["metadata"]["minecraft_version"]) for run in runs.values()}
    identical_inputs = len(identities) == 1

    native, before, after = (runs[name] for name in ("native", "before", "after"))
    before_scenarios, after_scenarios, native_scenarios = (run["scenarios"] for run in (before, after, native))
    recovered = [name for name in before_scenarios
                 if before_scenarios[name]["successes"] < before_scenarios[name]["runs"] and
                 after_scenarios[name]["successes"] == after_scenarios[name]["runs"]]
    matched = [name for name in before_scenarios
               if before_scenarios[name]["successes"] == before_scenarios[name]["runs"] and
               after_scenarios[name]["successes"] == after_scenarios[name]["runs"]]
    faster = [name for name in matched if after_scenarios[name]["game_ticks_median"] < before_scenarios[name]["game_ticks_median"]]
    equal = [name for name in matched if after_scenarios[name]["game_ticks_median"] == before_scenarios[name]["game_ticks_median"]]
    slower = [name for name in matched if after_scenarios[name]["game_ticks_median"] > before_scenarios[name]["game_ticks_median"]]

    comparison = {
        "success_rate_change": after["aggregate"]["success_rate"]-before["aggregate"]["success_rate"],
        "total_game_ticks_change": change(after["aggregate"]["game_ticks"]["total"], before["aggregate"]["game_ticks"]["total"]),
        "full_stop_runs_change": change(after["aggregate"]["full_stop_runs"]["total"], before["aggregate"]["full_stop_runs"]["total"]),
        "input_changes_change": change(after["aggregate"]["input_changes"]["total"], before["aggregate"]["input_changes"]["total"]),
        "after_total_ticks_vs_native": change(after["aggregate"]["game_ticks"]["total"], native["aggregate"]["game_ticks"]["total"]),
        "after_median_ticks_vs_native": change(after["aggregate"]["game_ticks"]["median"], native["aggregate"]["game_ticks"]["median"]),
        "previously_failing_scenarios_recovered": recovered,
        "fully_passing_before_and_after_scenarios": len(matched),
        "median_tick_wins": len(faster), "median_tick_ties": len(equal), "median_tick_regressions": len(slower),
        "median_tick_regression_scenarios": slower,
        "representative": {name: {variant: {key: runs[variant]["scenarios"][name][key] for key in
                            ("runs", "successes", "game_ticks_median", "full_stop_runs_median", "input_changes_median",
                             "path_length_median", "target_horizontal_error_median")}
                            for variant in ("native", "before", "after")}
                           for name in ("linear_x_positive_short", "linear_x_negative_long", "turn_90_left", "curve_s",
                                        "parkour_level2_gap", "parkour_level4_platforms", "roof_overhang_recovery", "step_x_descend")}}

    production = after["metadata"]["source_sha256"]
    current_hashes = {path: sha(Path(path)) for path in production}
    source_match = current_hashes == production
    python_log = root/"final-python.log"
    gradle_log = root/"final-gradle-check.log"
    python_text, gradle_text = python_log.read_text(), gradle_log.read_text()
    test_match = re.search(r"Ran ([0-9]+) tests", python_text)
    mutation_paths = {"skills": root/"final-verification/skill-mutations/results.json",
                      "native": root/"final-verification/mutations/results.json",
                      "controller": root/"final-verification/controller-mutations/results.json",
                      "building": root/"final-verification/building-mutations/results.json"}
    mutations = {name: mutation_report(path) for name, path in mutation_paths.items()}
    tls = read(root/"final-verification/interop.json")
    building = read(Path("build/superflat-benchmark/A15/result.json"))
    final_client = read(root/"final-client.json")
    qa = {"python": {"tests": int(test_match.group(1)) if test_match else None, "passed": "\nOK\n" in python_text,
                     "sha256": sha(python_log)},
          "gradle": {"passed": "BUILD SUCCESSFUL" in gradle_text, "sha256": sha(gradle_log)},
          "TLS": tls, "mutations": mutations, "mutation_total": sum(row["total"] for row in mutations.values()),
          "all_mutations_killed": all(row["all_killed"] for row in mutations.values()),
          "superflat_A15_regression": {**{key: building.get(key) for key in
              ("passed", "objective_verified", "elapsed_seconds", "executed_operations", "failed_actions",
               "verified_native_placement_events", "ended_snapshot_identity")},
              "verification": {key: building.get("verification", {}).get(key) for key in
                  ("expected_blocks", "verified_blocks", "incorrect_blocks", "missing_blocks", "unknown_blocks",
                   "entrance_clear", "interior_clear", "interior_accessible", "roof_complete", "floor_intact",
                   "safe_player", "objective_verified")}},
          "superflat_A15_result_sha256": sha(Path("build/superflat-benchmark/A15/result.json")),
          "final_client": final_client,
          "installed_test_jar_sha256": sha(Path("build/libs/blockwire-0.2.0-alpha.4.jar"))}

    history = []
    for run_id in HISTORY:
        summary = read(root/run_id/"summary.json")
        history.append({"id": run_id, "runs": summary["runs"], "successes": summary["successes"],
                        "success_rate": summary["success_rate"],
                        "failed_scenarios": [{"name": name, "successes": row["successes"], "runs": row["runs"]}
                            for name, row in summary["scenarios"].items() if row["successes"] < row["runs"]],
                        "summary_sha256": sha(root/run_id/"summary.json")})

    optimized_gates = {
        "same_fixture_scenarios_and_version": identical_inputs,
        "all_211_repetitions_pass_independent_settled_predicate": after["aggregate"]["successes"] == 211 == after["aggregate"]["runs"],
        "blockwire_max_horizontal_error_at_most_0_3": after["aggregate"]["target_horizontal_error"]["max"] <= .3,
        "zero_health_loss": after["aggregate"]["health_loss"]["total"] == 0.,
        "all_runs_settled_and_no_trace_loss": after["aggregate"]["all_settled_at_end"] and after["aggregate"]["trace_dropped_samples"] == 0,
        "improves_total_ticks_stops_and_input_changes": all(comparison[key] < 0 for key in
            ("total_game_ticks_change", "full_stop_runs_change", "input_changes_change")),
        "all_before_failure_scenarios_recovered": len(recovered) == 9,
        "final_source_matches_qualified_after_run": source_match,
        "python_gradle_tls_and_mutations_pass": qa["python"]["passed"] and qa["gradle"]["passed"] and
            tls.get("status") == "PASS" and qa["all_mutations_killed"],
        "fresh_superflat_A15_regression_passes": bool(building.get("passed") and building.get("objective_verified")),
        "client_world_closed": bool(final_client.get("world_saved_and_closed") and not final_client.get("in_world"))}
    optimized_go = all(optimized_gates.values())
    assessments = {
        "native_reference": {"decision": "GO" if native["aggregate"]["successes"] == native["aggregate"]["runs"] else "NO-GO",
                             "meaning": "The declared ordinary-input reference completes every scenario at its separate 1.0-block endpoint radius."},
        "unchanged_controller": {"decision": "GO" if before["aggregate"]["successes"] == before["aggregate"]["runs"] else "NO-GO",
                                 "meaning": "The preserved pre-optimization controller does not complete the fixed cohort."},
        "optimized_controller": {"decision": "GO" if optimized_go else "NO-GO", "gates": optimized_gates,
                                 "meaning": "Final Blockwire source completes every repetition at 0.3 blocks and passes the retained safety/regression gates."},
        "native_performance_parity": {"decision": "GO" if after["aggregate"]["game_ticks"]["total"] <= native["aggregate"]["game_ticks"]["total"] else "NO-GO",
                                      "meaning": "Strict parity requires no more aggregate game ticks than the ordinary-input reference; this is not required for optimized-controller GO."}}

    fixture_identity, scenario_identity, version = next(iter(identities)) if identical_inputs else (None, None, None)
    artifact_paths = [root/"private/baseline.manifest.json", root/"private/controller-before.sha256", root/"final-client.json",
                      python_log, gradle_log, root/"final-tls-interop.log", root/"final-native-mutations.log",
                      root/"final-skill-mutations.log", root/"final-controller-mutations.log", root/"final-building-mutations.log"]
    source_paths = [Path("python/src/blockwire/skills/motion.py"), Path("python/src/blockwire/skills/walking.py"),
                    Path("src/main/java/dev/blockwire/NavigationView.java"), Path("src/main/java/dev/blockwire/MotionTrace.java"),
                    Path("src/main/java/dev/blockwire/BridgeServer.java"), Path("src/main/java/dev/blockwire/Protocol.java"),
                    *sorted(Path("tests/movement").glob("*.py")), Path("tools/movement_benchmark.py"),
                    Path("tools/report_movement_benchmark.py"), Path("tests/run_skill_mutations.py"),
                    Path("python/tests/test_movement_benchmark.py"), Path("python/tests/test_motion_trace.py"),
                    Path("python/tests/test_continuous_motion.py"), Path("python/tests/test_walking_continuous.py"),
                    Path("python/tests/test_terrain.py"), Path("python/tests/test_skills.py"),
                    Path("src/contractTest/java/dev/blockwire/MotionTraceContractTest.java"),
                    Path("src/contractTest/java/dev/blockwire/TerrainContractTest.java"),
                    Path("README.md"), Path("python/README.md"), Path("docs/movement-benchmark.md"), Path("docs/motion.md"),
                    Path("docs/architecture.md"), Path("docs/protocol.md"), Path("docs/skills.md"), Path("docs/extensions.md"),
                    Path("docs/autonomous-survival.md")]
    document = {
        "schema_version": 1,
        "scope": "Deterministic Minecraft 26.3 native-input movement benchmark; no LLM, teleportation, custom physics or second controller.",
        "architecture": "goal -> existing Python route/motor -> actor-fenced native look/drive/jump leases -> Minecraft physics -> end-of-client-tick telemetry",
        "fixture": {"identity": fixture_identity, "scenario_identity": scenario_identity, "minecraft_version": version,
                    "scenario_count": len(after_scenarios), "repetitions": after["aggregate"]["runs"],
                    "baseline_manifest_sha256": sha(root/"private/baseline.manifest.json"),
                    "restore_policy": "Each independent cohort restores and validates the same owned closed snapshot."},
        "acceptance": {"native_reference_horizontal_radius": 1.0, "blockwire_horizontal_radius": .3,
                       "settled_measurement": True,
                       "note": "Receipts and skill-level arrived never override the independent settled tick trace."},
        "assessments": assessments,
        "canonical_runs": runs,
        "comparison": comparison,
        "optimization_history": history,
        "qa": qa,
        "qualified_source_sha256": production,
        "current_source_sha256": current_hashes,
        "private_evidence_root": str(root),
        "artifact_sha256": {str(path): sha(path) for path in artifact_paths if path.exists()},
        "source_sha256": {str(path): sha(path) for path in source_paths if path.exists()},
        "limitations": ["One owned deterministic fixture and one Minecraft version; not general terrain coverage.",
                        "Slabs, fluids, caves, unknown-height long routes and arbitrary non-full-block geometry remain unsupported.",
                        "Known-hazard avoidance is best effort, not immunity; hostile Survival reliability is not qualified.",
                        "Native reference and Blockwire use different declared endpoint radii, so endpoint error/path length are not direct parity metrics.",
                        "Strict native tick parity is NO-GO, principally including the Level-4 platform route.",
                        "Historical construction Test B remains NO-GO; movement results never retroactively requalify it.",
                        "No release, upload or deployment is authorized by this evidence."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2)+"\n")
    print(json.dumps({"assessments": assessments, "after": {"successes": after["aggregate"]["successes"],
          "runs": after["aggregate"]["runs"]}, "mutation_total": qa["mutation_total"]}, indent=2))


if __name__ == "__main__":
    main()
