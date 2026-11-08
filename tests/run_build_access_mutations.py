#!/usr/bin/env python3
"""Isolated observed-route policy mutations. No game, GUI, model or live transport.

Only an assertion failure in the designated passing contract kills a mutation.
Compilation/import/runtime errors do not count. Each variant has a fresh copy.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ACCESS = 'python/src/blockwire/skills/build_access.py'
BUILDER = 'python/src/blockwire/grounded_build.py'
G = 'test_build_access.AccessGraphContracts.'
I = 'test_build_access.AccessIntegrationContracts.'
CASES = [
    ('no_gap', ACCESS, "if kind == 'gap_jump': continue", "if kind == 'gap_jump':\n                fresh[key] = Edge('flat', frame); continue", G+'test_GA01_only_explicit_native_edges_no_blueprint_or_gap_invention'),
    ('own_floor', ACCESS, "else floor(p) in changes", 'else False', G+'test_GA02_removing_bridge_cannot_cut_observed_return'),
    ('diagonal_floor', ACCESS, 'return {floor(p) for p in {a, b} | corners(a, b, kind)}', 'return {floor(p) for p in {a, b}}', G+'test_GA03_diagonal_needs_both_corner_floors_after_removal'),
    ('headroom', ACCESS, "return {p, (p[0], p[1]+1, p[2])}", 'return {p}', G+'test_GA04_headroom_and_both_door_cells_protect_return'),
    ('step_arc', ACCESS, "top = low + (3 if kind == 'step' else 1)", "top = low + (2 if kind == 'step' else 1)", G+'test_GA05_step_jump_clearance_not_just_endpoint_bodies'),
    ('unknown_refresh', ACCESS, 'if not inside(p)}', 'if True}', G+'test_GA06_missing_cells_in_refreshed_window_become_unknown'),
    ('hazard_corner', ACCESS, 'if {a, b} | corners(a, b, kind) <= safe:', 'if {a, b} <= safe:', G+'test_GA07_hazardous_diagonal_corner_cannot_be_used'),
    ('border_history', ACCESS, 'not all(inside(p) for p in dependencies)', 'not any(inside(p) for p in dependencies)', G+'test_GA08_overlap_keeps_border_edges_historical_not_fresh'),
    ('no_synthetic_landing', ACCESS, 'self.nodes, self.edges = self.projected(kind, changes)', "self.nodes, self.edges = self.projected(kind, changes)\n        if kind == 'remove': self.nodes.update({cell(p): self.frame for p in changes})", G+'test_GA09_subtraction_never_predicts_new_air_floor_or_edges'),
    ('actor', ACCESS, "nav.get('actor_session') == self.actor", 'True', G+'test_GA10_schema_actor_geometry_and_indices_fail_without_partial_update'),
    ('node_budget', ACCESS, 'len(nodes) <= MAX_NODES', 'True', G+'test_GA11_bounded_history_edges_and_route'),
    ('edge_budget', ACCESS, 'len(retained) <= MAX_EDGES', 'True', G+'test_GA11_bounded_history_edges_and_route'),
    ('frame_budget', ACCESS, 'max(len(edges), len(transitions)) <= MAX_FRAME_EDGES', 'True', G+'test_GA11_bounded_history_edges_and_route'),
    ('route_budget', ACCESS, 'len(path)-1 <= MAX_ROUTE', 'True', G+'test_GA11_bounded_history_edges_and_route'),
    ('body_width', ACCESS, '0 < b[3]-b[0] <= .7', '0 < b[3]-b[0] <= 2', G+'test_GA12_native_body_envelope_is_required'),
    ('body_actor', ACCESS, "trace.get('actor_session') == actor", 'True', G+'test_GA12_native_body_envelope_is_required'),
    ('fresh_stance', ACCESS, 'self.nodes.get(stand) == self.frame', 'True', G+'test_GA13_retreat_stance_must_be_from_latest_mesh'),
    ('bfs_cancel', ACCESS, 'while queue:\n            self.check()', 'while queue:', G+'test_GA14_cancellation_and_deadline_checks_inside_graph_work'),
    ('scaffold_children', BUILDER, 'if any(position in self.scaffold_parents.get(child, set()) for child in remaining): continue', 'if False: continue', I+'test_GA16_real_mocked_side_attachment_records_child_before_parent'),
    ('place_retreat', BUILDER, "if self.retreat_plan('place', expected) is None: continue", 'if False: continue', I+'test_GA18_placement_without_retreat_never_dispatches'),
    ('remove_retreat', BUILDER, "if self.retreat_plan('remove', [position]) is None: continue", 'if False: continue', I+'test_GA19_final_retreat_guard_is_required_even_after_successful_approach'),
    ('owner_after_approach', BUILDER, 'states = self.scaffold_state(position)', 'states = {position: SCAFFOLD}', I+'test_GA20_owner_is_rechecked_after_approach'),
    ('body_read_fence', BUILDER, 'upright_body(self.player.motion_trace(limit=1, actor_session=self.guard.actor)', 'upright_body(self.player.motion_trace(limit=1)', I+'test_GA21_new_body_reads_are_actor_fenced_and_not_reset'),
    ('home_clearance', BUILDER, 'not body(self.access.home).intersection(self.targets)', 'True', I+'test_GA22_home_must_be_centered_and_outside_target_clearance'),
    ('home_center', ACCESS, 'math.dist(position, center) <= .15', 'True', I+'test_GA22_home_must_be_centered_and_outside_target_clearance'),
    ('shared_deadline', BUILDER, 'deadline=min(self.context.deadline, self.context.clock()+30.)', 'deadline=self.context.deadline', I+'test_GA23_walking_legs_share_one_child_deadline'),
    ('account_placement_before_cancel', BUILDER, "self.verify_effect(ticket, expected, receipt['actor_tick'])", "self.verify_effect(ticket, expected, receipt['actor_tick'])\n            self.context.check()", I+'test_GA24_cancel_after_verified_placement_keeps_scaffold_accounted'),
    ('account_removal_before_cancel', BUILDER, 'self.removed.add(position); remaining.remove(position)', 'self.context.check(); self.removed.add(position); remaining.remove(position)', I+'test_GA25_cancel_after_verified_removal_keeps_air_accounted'),
    ('door_support', BUILDER, "need(position not in self.door_floors, 'scaffold_would_support_permanent_door')", "need(True, 'scaffold_would_support_permanent_door')", I+'test_GA26_temporary_floor_cannot_be_permanent_door_support'),
    ('durable_plan', BUILDER, "self.ledger.append('retreat_plan', **plan.json())", 'pass', I+'test_GA28_retreat_plan_is_durable_before_native_world_dispatch'),
    ('fresh_walk_edge', BUILDER, 'edge is not None and edge.frame == self.access.frame', 'True', I+'test_GA29_stale_edge_fault_is_denied_before_motor_dispatch'),
    ('current_pose', ACCESS, "current[1] == origin[1] and abs(position[0]-current[0]-.5) <= .8\n                and abs(position[2]-current[2]-.5) <= .8", 'True', G+'test_GA30_reported_current_cell_must_match_actual_native_pose'),
    ('pending_until_accounted', BUILDER, 'return states  # Caller commits ownership/accounting before clearing pending.', 'self.guard.pending_effect = False\n                    return states', I+'test_GA31_hard_interrupt_before_accounting_retains_uncertainty'),
]


def run(root, test, output):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(root/'python/src')+os.pathsep+str(root/'python/tests'))
    result = subprocess.run([sys.executable,'-B','-m','unittest',test],cwd=root,env=env,capture_output=True,text=True,timeout=90)
    log = result.stdout + result.stderr
    output.write_text(log)
    return result.returncode, log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args(); os.umask(0o077)
    output = args.output.resolve(); output.mkdir(parents=True,exist_ok=False)
    code,_ = run(ROOT,'test_build_access',output/'baseline.log')
    if code: raise RuntimeError('Baseline failed; no mutation verdict')
    rows=[]
    for name,path,old,new,test in CASES:
        with tempfile.TemporaryDirectory(prefix='isolated-',dir=output) as directory:
            root=Path(directory)
            shutil.copytree(ROOT/'python/src',root/'python/src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
            (root/'python/tests').mkdir()
            for filename in ('test_build_access.py','test_grounded_build.py','test_schematic.py'):
                shutil.copyfile(ROOT/'python/tests'/filename,root/'python/tests'/filename)
            file=root/path; original=file.read_text()
            if original.count(old)!=1: raise RuntimeError('Non-unique mutation anchor: '+name)
            changed=original.replace(old,new); compile(changed,str(file),'exec'); file.write_text(changed)
            code,log=run(root,test,output/(name+'.log'))
            killed=code==1 and 'FAIL: '+test.split('.')[-1] in log and 'ERROR:' not in log and 'FAILED (failures=' in log
            row={'name':name,'test':test,'status':'KILLED' if killed else 'INVALID_OR_SURVIVED'}
            rows.append(row); print(name,row['status'],flush=True)
    (output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    return int(any(row['status']!='KILLED' for row in rows))


if __name__=='__main__': raise SystemExit(main())
