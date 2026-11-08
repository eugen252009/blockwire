#!/usr/bin/env python3
"""Isolated builder schema/policy/outcome mutations. No game or model invocation.

Native dispatcher/GUI guard mutations are STATIC wiring checks, not gameplay.
A compilation/import failure is never counted as a killed mutation.
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
BUILDER = 'python/src/blockwire/grounded_build.py'
NATIVE = 'src/main/java/dev/blockwire/CreativeBuild.java'
DISPATCH = 'src/main/java/dev/blockwire/Blockwire.java'
TEST = 'test_grounded_build.GroundedBuildContracts.'
PYTHON = [
    ('mode', "scene.get('game_mode') == 'creative'", "scene.get('game_mode') in {'creative', 'survival'}", 'test_GB07_preflight_mode_identity_version_or_ui_failure_has_no_effects'),
    ('flight', "scene.get('flying') is False", 'True', 'test_GB07_preflight_mode_identity_version_or_ui_failure_has_no_effects'),
    ('actor', 'actor == self.actor and dimension == self.dimension', 'dimension == self.dimension', 'test_GB08_actor_or_damage_change_during_actions_stops'),
    ('cancel_before_read', "self.context.check()\n        need(not self.uncertain", "need(not self.uncertain", 'test_GB06_cancel_before_first_read_has_no_actions'),
    ('material_effect', "selected.get('item') == item and selected.get('count') == 64", 'True', 'test_GB02_receipt_without_material_readback_never_places'),
    ('effect_pending', 'self.pending_effect = True', 'self.pending_effect = False', 'test_GB02_receipt_without_material_readback_never_places'),
    ('placement_effect', 'all(matches(states[p], desired) for p, desired in expected.items())', 'True', 'test_GB03_receipt_without_placement_postcondition_is_not_success'),
    ('all_final_targets', "need(set(states) == expected, 'final_target_observation_incomplete')", "need(True, 'final_target_observation_incomplete')", 'test_GB41_final_read_must_cover_every_door_half'),
    ('final_state', 'return actual == wanted', 'return True', 'test_GB22_final_neighbor_verification_is_not_just_placement'),
    ('properties', "return props == expected['properties']", 'return True', 'test_GB14_full_state_and_only_explicit_deferred_properties'),
    ('consumption', "self.scene().get('holding', {}).get('count') == 64", 'True', 'test_GB13_survival_consumption_is_not_accepted_as_creative'),
    ('interrupt_in_flight', 'except BaseException:', 'except Exception:', 'test_GB39_keyboard_interrupt_during_rpc_is_unknown_without_reconnect'),
    ('durable_parent', 'try: os.fsync(parent)', 'try: pass', 'test_GB40_run_directory_parent_is_durable_before_first_rpc'),
    ('transport_latch', 'if self.lost:', 'if False:', 'test_GB35_transport_fault_cannot_be_reopened_for_reads_or_cleanup'),
    ('socket_identity', 'elif self.backend._socket is not self.connection:', 'elif False:', 'test_GB38_actual_bridge_socket_identity_is_pinned'),
    ('owned_slot', "(old, count) == (self.owned_item, self.owned_count)", 'True', 'test_GB15_owned_hotbar_cannot_replace_foreign_changed_contents'),
    ('input_bound', "1 <= arguments['ticks'] <= 8", "1 <= arguments['ticks'] <= 100", 'test_GB16_motion_is_fenced_bounded_and_not_a_mining_interface'),
    ('scaffold_authorization', 'self.parameters.allow_scaffolds and len(self.scaffolds) < self.parameters.max_scaffolds', 'len(self.scaffolds) < self.parameters.max_scaffolds', 'test_GB18_no_scaffold_authorization_means_none'),
    ('remove_effect', "all(s['id'] == 'minecraft:air' and s['properties'] == {} for s in states.values())", 'True', 'test_GB27_removal_receipt_without_air_postcondition_stops'),
    ('scaffold_owner', "reply.get('placed_by_this_controller') is True", 'True', 'test_GB36_watch_without_controller_ownership_never_removes'),
    ('camera_completion', "rotation.get('active') is False", 'True', 'test_GB32_matching_angles_are_not_completed_camera_plan'),
    ('scaffold_floor', "position in _reachable(self.nav(), True)", 'True', 'test_GB34_unobserved_floor_cannot_authorize_a_scaffold'),
    ('native_support', 'if support not in floors:', 'if False:', 'test_GB37_geometric_nearby_is_not_observed_support'),
    ('prediction', 'if not matches(candidate, state): continue', 'if False: continue', 'test_GB30_mismatched_native_prediction_never_places'),
    ('release_owned', "row.get('remote_owned_inputs') == []", 'True', 'test_GB12_unconfirmed_release_invalidates_success'),
    ('settled_gravity', 'math.hypot(velocity[0], velocity[2]) < .015', 'math.dist(velocity, (0, 0, 0)) < .015', 'test_GB01_full_disclosed_simulation_and_durable_intents'),
]
JAVA = [
    ('mode', NATIVE, 'need(creative,"creative_mode_required")', 'need(true,"creative_mode_required")', 'CB20_creative_only'),
    ('flight', NATIVE, 'need(!flying,"flight_not_allowed")', 'need(true,"flight_not_allowed")', 'CB21_no_flight'),
    ('double_tap', NATIVE, 'nativeDoubleTapTimer==0', 'nativeDoubleTapTimer>=0', 'CB23_native_double_tap_window'),
    ('airborne_jump', NATIVE, '(grounded && nativeDoubleTapTimer==0)', '(nativeDoubleTapTimer==0)', 'CB24_no_airborne_jump_rise'),
    ('actor_dispatch', DISPATCH, 'var request=CreativeBuild.request(q);guardedActor(q);playing();', 'var request=CreativeBuild.request(q);playing();', 'CB34_STATIC_fence_before_effect'),
    ('air_only', NATIVE, 'boolean empty=world.getBlockState(dest).isAir()', 'boolean empty=true', 'CB30_STATIC_no_overwrite'),
    ('owned_remove', NATIVE, 'owner!=null && owner.placed &&', 'owner!=null && true &&', 'CB31_STATIC_owned_scaffold_guards'),
    ('slot_components', NATIVE, 'previous.getComponentsPatch().isEmpty()', 'true', 'CB29_STATIC_inventory_assertions'),
    ('watch_coordinates', NATIVE, 'case "check" -> {Protocol.fields(q,"action","actor_session","ticket");', 'case "check" -> {Protocol.fields(q,"action","actor_session","ticket","position");', 'CB18_no_coordinate_read'),
    ('watch_budget', NATIVE, 'MAX_WATCHES=4096', 'MAX_WATCHES=4097', 'CB44_watch_budget'),
    ('native_ground_gravity', NATIVE, 'getDeltaMovement().horizontalDistanceSqr()<.0025', 'getDeltaMovement().lengthSqr()<.0025', 'CB43_STATIC_grounded_gravity_is_not_horizontal_motion'),
]


def invoke(root, command, output, python=False):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    if python: env['PYTHONPATH'] = str(root/'python/src') + os.pathsep + str(root/'python/tests')
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=180)
    text = result.stdout + result.stderr
    output.write_text(text)
    return result.returncode, text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077); args.output.mkdir(parents=True, exist_ok=False)
    for language in ('python', 'native'):
        command = [sys.executable, '-B', '-m', 'unittest', 'test_grounded_build'] if language=='python' else ['./gradlew','--console=plain','creativeBuildContractTest']
        code, _ = invoke(ROOT, command, args.output/(language+'-baseline.log'), language=='python')
        if code: raise RuntimeError('Baseline failed; no mutation verdict: ' + language)
    cases = [('python', name, BUILDER, old, new, TEST+test) for name, old, new, test in PYTHON]
    cases += [('native', *row) for row in JAVA]
    results = []
    for language, name, filename, old, new, test in cases:
        with tempfile.TemporaryDirectory(prefix='blockwire-grounded-mutation-') as directory:
            root = Path(directory)
            if language=='python':
                shutil.copytree(ROOT/'python/src', root/'python/src', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
                (root/'python/tests').mkdir()
                for file in ('test_schematic.py','test_grounded_build.py'):
                    shutil.copyfile(ROOT/'python/tests'/file, root/'python/tests'/file)
                command=[sys.executable,'-B','-m','unittest',test]
            else:
                for file in ('build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','LICENSE'): shutil.copy2(ROOT/file,root/file)
                for folder in ('gradle','src'): shutil.copytree(ROOT/folder,root/folder)
                command=['./gradlew','--console=plain','creativeBuildContractTest']
            file=root/filename; original=file.read_text()
            if original.count(old)!=1: raise RuntimeError('Non-unique mutation anchor: '+language+'-'+name)
            modified=original.replace(old,new)
            if language=='python': compile(modified,str(file),'exec')
            file.write_text(modified)
            code, text = invoke(root,command,args.output/(language+'-'+name+'.log'),language=='python')
            if language=='python':
                killed=code==1 and 'FAIL: '+test.split('.')[-1] in text and 'ERROR:' not in text and 'FAILED (failures=' in text
            else:
                killed=code!=0 and 'AssertionError: '+test in text and 'Compilation failed' not in text
            results.append({'language':language,'name':name,'test':test,'status':'KILLED' if killed else 'INVALID_OR_SURVIVED'})
            print(language,name,results[-1]['status'],flush=True)
    (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    return int(any(row['status']!='KILLED' for row in results))


if __name__=='__main__': raise SystemExit(main())
