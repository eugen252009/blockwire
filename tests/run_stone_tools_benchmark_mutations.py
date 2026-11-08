#!/usr/bin/env python3
"""Isolated recipe/benchmark guard mutations. No Minecraft, world or model calls."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BENCH = 'examples/stone_tools_benchmark.py'
TEST = 'test_stone_tools_benchmark.BenchmarkContracts.'
CASES = [
    ('nine_not_eight', BENCH, 'STONE_GOAL = 9', 'STONE_GOAL = 8', TEST+'test_complete_sequence_materials_and_nine_distinct_stone_targets'),
    ('stone_pickup', BENCH, 'require(evidence and after - before >= 1,', 'require(True,', TEST+'test_receipts_without_wood_craft_descent_stone_or_ascent_never_pass'),
    ('mining_evidence', BENCH, 'require(evidence and after - before >= 1,', 'require(after - before >= 1,', TEST+'test_pickup_without_mining_evidence_cannot_count_as_nine_stone'),
    ('held_pick', BENCH, "scene['holding'].get('item') == WOOD and ", '', TEST+'test_wrong_held_tool_prevents_stone_dispatch'),
    ('depth_bound', BENCH, 'MAX_DEPTH = 8', 'MAX_DEPTH = 9', TEST+'test_no_stone_stops_at_depth_bound_without_fake_return_or_tools'),
    ('material_reserve', BENCH, 'and sum(counts.get(i, 0) for i in PLANKS) >= MAX_DEPTH', 'and True', TEST+'test_return_materials_reserved_before_any_descent'),
    ('protected_stairs', BENCH, 't[1] not in protected | used', 't[1] not in used', TEST+'test_three_step_return_and_protected_stair_supports'),
    ('surface_proof', BENCH, "and math.dist(scene['position'], self.surface) <= .3", 'and True', TEST+'test_surface_and_final_inventory_are_required_not_model_finish'),
    ('final_tools', BENCH, 'all(counts.get(i, 0) >= 1 for i in TOOLS)', 'True', TEST+'test_surface_and_final_inventory_are_required_not_model_finish'),
    ('release_barrier', BENCH, "and self.cleanup == 'released',", 'and True,', TEST+'test_unconfirmed_release_is_terminal_unknown_without_retry'),
    ('cancel', BENCH, "require(not self.cancelled.is_set(), 'cancel_requested')", "require(True, 'cancel_requested')", TEST+'test_actor_damage_cancel_and_deadline_stop_after_one_frame'),
    ('deadline', BENCH, "require(self.clock() < self.deadline, 'deadline_exceeded')", "require(True, 'deadline_exceeded')", TEST+'test_expired_deadline_forbids_even_new_observations'),
    ('actor_fence', BENCH, "actor == self.actor and scene['dimension'] == self.dimension", "scene['dimension'] == self.dimension", TEST+'test_actor_damage_cancel_and_deadline_stop_after_one_frame'),
    ('fresh_directory', BENCH, 'parents=True, exist_ok=False', 'parents=True, exist_ok=True', TEST+'test_authorization_describe_limits_and_fresh_ledger'),
    ('durable_intent', BENCH, "record(self.directory, stem + '-intent.json',", "(lambda *args: None)(self.directory, stem + '-intent.json',", TEST+'test_audit_failure_prevents_dispatch_and_no_used_run_is_resumed'),
    ('frame_cap', BENCH, 'self.frames < MAX_FRAMES', 'True', TEST+'test_deadline_and_cancel_before_action_and_frame_bound'),
    ('shovel_recipe', 'python/src/blockwire/recipes.py', "Recipe('minecraft:stone_shovel', 1, (('minecraft:cobblestone',), ('minecraft:stick',), ('minecraft:stick',)))", "Recipe('minecraft:stone_shovel', 1, (('minecraft:cobblestone',), ('minecraft:cobblestone',), ('minecraft:stick',)))", 'test_crafting.CraftContracts.test_CF12_stone_shovel_and_sword_require_native_result_and_exact_consumption'),
    ('sword_recipe', 'python/src/blockwire/recipes.py', "Recipe('minecraft:stone_sword', 1, (('minecraft:cobblestone',), ('minecraft:cobblestone',), ('minecraft:stick',)))", "Recipe('minecraft:stone_sword', 1, (('minecraft:cobblestone',), ('minecraft:stick',), ('minecraft:stick',)))", 'test_crafting.CraftContracts.test_CF12_stone_shovel_and_sword_require_native_result_and_exact_consumption'),
]


def execute(root, names, log):
    env = {**os.environ, 'PYTHONPATH': str(root/'python/src')+os.pathsep+str(root/'python/tests'),
           'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', *names], cwd=root, env=env,
                            capture_output=True, text=True, timeout=120)
    log.write_text(result.stdout+result.stderr)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077); args.output.mkdir(parents=True, exist_ok=False)
    baseline = execute(ROOT, ['test_stone_tools_benchmark', 'test_crafting'], args.output/'baseline.log')
    if baseline.returncode:
        raise RuntimeError('Baseline failed; no valid mutation verdict')
    results = []
    for name, file, old, new, test in CASES:
        with tempfile.TemporaryDirectory(prefix='isolated-', dir=args.output) as directory:
            root = Path(directory)
            shutil.copytree(ROOT/'python/src', root/'python/src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (root/'python/tests').mkdir(); (root/'examples').mkdir()
            for filename in ('test_stone_tools_benchmark.py', 'test_crafting.py'):
                shutil.copyfile(ROOT/'python/tests'/filename, root/'python/tests'/filename)
            shutil.copyfile(ROOT/BENCH, root/BENCH)
            path = root/file; original = path.read_text()
            if original.count(old) != 1:
                raise RuntimeError('Invalid unique mutation anchor: '+name)
            changed = original.replace(old, new)
            compile(changed, str(path), 'exec'); path.write_text(changed)
            result = execute(root, [test], args.output/(name+'.log'))
            killed = (result.returncode == 1 and 'FAIL: '+test.split('.')[-1] in result.stderr
                      and 'FAILED (failures=' in result.stderr and 'ERROR:' not in result.stderr)
            status = 'KILLED' if killed else 'INVALID_OR_SURVIVED'
            results.append({'name': name, 'test': test, 'status': status})
            print(name, status, flush=True)
    (args.output/'results.json').write_text(json.dumps(results, indent=2)+'\n')
    return int(any(row['status'] != 'KILLED' for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
