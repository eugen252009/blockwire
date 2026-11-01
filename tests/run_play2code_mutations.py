#!/usr/bin/env python3
"""Isolated Play2Code exporter mutations. Never contacts or controls Minecraft."""
import os
import run_bcl_mutations as runner
from pathlib import Path

runner.OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',runner.ROOT/'build/play2code-verification'))/'mutations'
runner.OUT.mkdir(parents=True,exist_ok=True)
runner.MUTATIONS=[
 ('remote_manifest_guard','play2code.py',"if capture.get('no_remote_controller_interference') is not True:","if False:",'test_play2code.Play2CodeContracts.test_P2C04_remote_interference_actor_and_sequence_fail_closed'),
 ('remote_tick_guard','play2code.py','if owned != []:','if False:','test_play2code.Play2CodeContracts.test_P2C04_remote_interference_actor_and_sequence_fail_closed'),
 ('stop_lifecycle_guard','play2code.py','if len(stop_requests) != 1:','if False:','test_play2code.Play2CodeContracts.test_P2C08_completed_capture_requires_one_explicit_stop_request'),
 ('stable_mutation_guard','play2code.py','type(stable) is not int or stable < 3','type(stable) is not int or stable < 0','test_play2code.Play2CodeContracts.test_P2C03_unsupported_effects_are_explicit_and_never_guessed'),
 ('no_path_smoothing','play2code.py','math.dist(position, previous_position) > .005','math.dist(position, previous_position) > .3','test_play2code.Play2CodeContracts.test_P2C02_every_eligible_tick_is_retained_and_batches_stay_bounded'),
 ('first_tick_origin','play2code.py',"previous_position = _vector(recording.capture['origin_position_absolute'], 'origin player position')",'previous_position = None','test_play2code.Play2CodeContracts.test_P2C06_first_grounded_checkpoint_is_measured_from_capture_origin'),
 ('airborne_not_M0','play2code.py',"if event.get('on_ground') is True:",'if True:','test_play2code.Play2CodeContracts.test_P2C03_unsupported_effects_are_explicit_and_never_guessed'),
 ('main_hand_only','play2code.py',"intent.get('type') != 'use_on_block' or event.get('hand') != 'main_hand' or intent.get('hand') != 'main_hand'",'False','test_play2code.Play2CodeContracts.test_P2C03_unsupported_effects_are_explicit_and_never_guessed'),
 ('absolute_coordinate_mode','play2code.py',"BATCH_PREFIX = ('BCL/1', 'S0 sync', 'S1 absolute', 'S3 stop')","BATCH_PREFIX = ('BCL/1', 'S0 sync', 'S1 relative', 'S3 stop')",'test_play2code.Play2CodeContracts.test_P2C01_export_preserves_raw_events_and_compiles_conservative_BCL'),
 ('registry_admission','play2code.py','valid, diagnostic = _group_is_valid(lines, registry)','valid, diagnostic = True, None','test_play2code.Play2CodeContracts.test_P2C03_unsupported_effects_are_explicit_and_never_guessed'),
 ('native_intent_position','play2code.py','if position not in candidates:','if False:','test_play2code.Play2CodeContracts.test_P2C07_confirmed_mutations_must_match_their_native_intents'),
 ('break_air_postcondition','play2code.py',"if event.get('after_block') not in AIR_BLOCKS:",'if False:','test_play2code.Play2CodeContracts.test_P2C07_confirmed_mutations_must_match_their_native_intents'),
 ('replay_not_claimed','play2code.py',"'replay': {'attempted': False, 'qualified': False, 'status': 'NOT_RUN',","'replay': {'attempted': True, 'qualified': False, 'status': 'NOT_RUN',",'test_play2code.Play2CodeContracts.test_P2C01_export_preserves_raw_events_and_compiles_conservative_BCL'),
 ('artifact_hash','play2code.py','return hashlib.sha256(path.read_bytes()).hexdigest()','return "0"*64','test_play2code.Play2CodeContracts.test_P2C01_export_preserves_raw_events_and_compiles_conservative_BCL'),
]

if __name__=='__main__':raise SystemExit(runner.main())
