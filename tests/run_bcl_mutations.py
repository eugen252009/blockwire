#!/usr/bin/env python3
"""Isolated BCL parser/dispatch mutations. No working-source edits or Minecraft access."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/bcl-verification'))/'mutations'
OUT.mkdir(parents=True,exist_ok=True)
MUTATIONS=[
 ('verified_dispatch_reuse','agent.py',"if self.reuse_verified_observation and outcome['status'] == 'succeeded':","if False:",'test_bcl.RuntimeContracts.test_BR13_verified_snapshot_reuse_only_reduces_dispatch_observations'),
 ('reused_snapshot_requires_fresh_preaction','agent.py','current, _ = self._observe()  # Never act on stale model-time resources/health.','current = observation  # MUTATION: stale dispatch state must not authorize an action.','test_bcl.RuntimeContracts.test_BR14_reused_dispatch_snapshot_never_authorizes_replacement_actor'),
 ('terminal_source_bound','bcl/cli.py','if len(source) > 16384:','if False:','test_bcl_cli.FileContracts.test_utf8_bom_multiline_and_bounds'),
 ('terminal_frame_bound','bcl/cli.py',"if len(json.dumps(frame, allow_nan=False).encode('utf-8')) > 32768:",'if False:','test_bcl_cli.FileContracts.test_utf8_bom_multiline_and_bounds'),
 ('terminal_wait_async','bcl/cli.py',"if result.get('status') == 'accepted':\n        result = await client.wait(result['task_id'])", "if False:\n        result = await client.wait(result['task_id'])",'test_bcl_cli.TerminalContracts.test_file_waits_for_async_terminal_and_failure_exit'),
 ('terminal_uncertain_stop','bcl/cli.py','                            task.result()','                            pass','test_bcl_cli.TerminalContracts.test_uncertain_transport_stops_without_replay'),
 ('terminal_private_token','bcl/cli.py','    if path.is_symlink():','    if False:','test_bcl_cli.FileContracts.test_gateway_token_file_is_private_regular_and_bounded'),
 ('terminal_redirected_output','bcl/cli.py','    return sys.stdin.isatty() and sys.stdout.isatty()','    return sys.stdin.isatty()','test_bcl_cli.TerminalContracts.test_redirected_stdout_keeps_tty_input_cancellable_and_json_clean'),
 ('terminal_redirected_tty_cancel','bcl/cli.py',"            is_cancellable_stream = os.name == 'posix' and not stat.S_ISREG(mode)","            is_cancellable_stream = os.name == 'posix' and stat.S_ISFIFO(mode)",'test_bcl_cli.TerminalContracts.test_redirected_stdout_keeps_tty_input_cancellable_and_json_clean'),
 ('modal_cycle','bcl/modal.py','(setting.values.index(current)+1)%len(setting.values)','setting.values.index(current)','test_bcl_modal.ModalContracts.test_BS01_generic_binary_three_and_four_value_cycles_wrap'),
 ('request_dedup','bcl/modal.py',"if key in self.state['requests']:",'if False:','test_bcl_modal.ModalContracts.test_BS04_durable_dedup_and_evicted_ids_cannot_repeat_cycles'),
 ('request_source_conflict','bcl/modal.py',"if record['source_digest']!=digest:",'if False:','test_bcl_modal.ModalContracts.test_BS04_durable_dedup_and_evicted_ids_cannot_repeat_cycles'),
 ('modal_snapshot','bcl/modal.py',"def _modal_from(self,state):return Modal(**{k:state['modal'][k] for k in Modal.__dataclass_fields__})","def _modal_from(self,state):return Modal()",'test_bcl_modal.ModalContracts.test_BS03_addendum_sequence_has_immutable_per_action_snapshots'),
 ('commit_before_publish','bcl/modal.py','self.store.save(staged)  # Atomic SQLite commit BEFORE publishing state or accepting actions.\n        self.state=staged','self.state=staged\n        self.store.save(staged)','test_bcl_modal.ModalContracts.test_BS09_failed_durable_commit_never_publishes_modal_transition'),
 ('unsubscribe','bcl/modal.py',"elif op.opcode=='E1':subs.discard(event)","elif op.opcode=='E1':pass",'test_bcl_modal.ModalContracts.test_BS05_sessions_and_subscriptions_are_isolated_and_pending_work_not_replayed'),
 ('explicit_relative_rehomes','bcl/modal.py',"if value=='relative':\n                                home_id=self._allocate_home(staged,request_id)","if value=='relative' and current!='relative':\n                                home_id=self._allocate_home(staged,request_id)",'test_bcl_modal.ModalContracts.test_BS06_relative_home_is_stable_then_explicit_assignment_rehomes_from_actual_position'),
 ('relative_point_home','bcl/runtime.py','else:values[name]+=coordinate.home[axes[kind]]',"else:values[name]+=observation['position'][axes[kind]]",'test_bcl_modal.ModalContracts.test_BS06_relative_home_is_stable_then_explicit_assignment_rehomes_from_actual_position'),
 ('relative_voxel_home','bcl/runtime.py',"origin=coordinate.voxel_origin if kind=='voxel' else coordinate.home","origin=coordinate.home",'test_bcl_modal.ModalContracts.test_BS12_relative_transform_covers_point_and_voxel_parameters_but_not_omitted_axes'),
 ('relative_vector_point_home','bcl/runtime.py',"origin=coordinate.voxel_origin if kind=='voxel' else coordinate.home","origin=coordinate.voxel_origin",'test_bcl_modal.ModalContracts.test_BS12_relative_transform_covers_point_and_voxel_parameters_but_not_omitted_axes'),
 ('relative_recorded_path_points','bcl/runtime.py',"elif kind=='point_samples':","elif False:",'test_bcl_modal.ModalContracts.test_BS12_relative_transform_covers_point_and_voxel_parameters_but_not_omitted_axes'),
 ('relative_recorded_sequence_points','bcl/runtime.py',"elif kind=='recorded_sequence':","elif False:",'test_bcl_modal.ModalContracts.test_BS12_relative_transform_covers_point_and_voxel_parameters_but_not_omitted_axes'),
 ('home_execution_barrier','bcl/runtime.py',"return {'kind':'wait','wait_seconds':.1}","return {'kind':'finish'}",'test_bcl_modal.ModalContracts.test_BS06_relative_home_is_stable_then_explicit_assignment_rehomes_from_actual_position'),
 ('home_commit_before_publish','bcl/modal.py','self.store.save(staged)  # The home is durable before any following coordinate-bearing operation.\n        self.state=staged;return context','self.state=staged\n        self.store.save(staged)\n        return context','test_bcl_modal.ModalContracts.test_BS15_failed_home_commit_never_publishes_a_new_coordinate_origin'),
 ('failed_home_rollback','bcl/modal.py',"if state['modal']['coordinate_mode']=='relative' and any(r['home_id']==current for r in changed):","if False:",'test_bcl_modal.ModalExecutionContracts.test_BS14_cancelled_queued_homing_rolls_back_to_the_previous_coordinate_context'),
 ('failed_home_fallback_chain','bcl/modal.py',"if previous['status'] in {'pending','ready'}:return 'relative',home_id","if previous['status']=='pending':return 'relative',home_id",'test_bcl_modal.ModalContracts.test_BS19_failed_second_consecutive_home_restores_the_first_captured_home'),
 ('legacy_semantics_fence','bcl/modal.py',"existing=any(key in self.state for key in ('modal_version','modal_layout','modal','coordinate'))","existing='modal_version' in self.state or 'modal_layout' in self.state",'test_bcl_modal.ModalContracts.test_BS17_pre_homing_modal_journals_fail_closed_instead_of_changing_meaning'),
 ('home_chain_validation','bcl/modal.py',"if identifier>=coordinate['next_home_id'] or (record['previous_mode']=='absolute')!=(previous is None):","if False:",'test_bcl_modal.ModalContracts.test_BS20_corrupt_persisted_home_chains_and_active_contexts_fail_closed'),
 ('active_home_validation','bcl/modal.py',"if mode=='absolute' and current is not None:raise ValueError('Absolute mode cannot retain an active S1 home')","if False:raise ValueError('Absolute mode cannot retain an active S1 home')",'test_bcl_modal.ModalContracts.test_BS20_corrupt_persisted_home_chains_and_active_contexts_fail_closed'),
 ('pending_home_validation','bcl/modal.py',"if record['status']=='pending' and any(record.get(name) is not None for name in ('home','voxel_origin','dimension')):","if False:",'test_bcl_modal.ModalContracts.test_BS20_corrupt_persisted_home_chains_and_active_contexts_fail_closed'),
 ('home_dimension_fence','bcl/runtime.py',"if observation.get('dimension')!=coordinate.dimension:self.error_at('COORDINATE_CONTEXT_MISMATCH','Relative home belongs to a different dimension.',op)","if False:self.error_at('COORDINATE_CONTEXT_MISMATCH','Relative home belongs to a different dimension.',op)",'test_bcl_modal.ModalContracts.test_BS12_relative_transform_covers_point_and_voxel_parameters_but_not_omitted_axes'),
 ('observer_home_actor_fence','bcl/gateway.py',"self.sampled_at=0.;sample=await self.observe()\n                                            if sample['actor_session']!=session.actor_session or sample['player_uuid']!=session.store.identity['player_id']:\n                                                raise BridgeError('actor_session_changed')","self.sampled_at=0.;sample=await self.observe()\n                                            if False:\n                                                raise BridgeError('actor_session_changed')",'test_bcl_websocket.WebSocketContracts.test_BW11_observer_homing_rechecks_actor_identity_before_capture'),
 ('continue_policy','bcl/runtime.py',"return mode=='continue'",'return False','test_bcl_modal.ModalExecutionContracts.test_BS07_continue_policy_does_not_turn_failed_operation_into_success'),
 ('websocket_auth','bcl/gateway.py',"not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+self.token)",'False','test_bcl_websocket.WebSocketContracts.test_BW06_auth_certificate_hostname_and_plaintext_fail_closed'),
 ('incoming_events','bcl/compiler.py',"if command.category=='event_out':",'if False:','test_bcl_websocket.WebSocketContracts.test_BW01_single_multiline_settings_and_direction'),
 ('duplicate_assignment','bcl/compiler.py','if param.name in assigned:','if False:','test_bcl.ParserContracts.test_BC03_structured_errors_and_source_locations'),
 ('boolean_lexeme','bcl/compiler.py',"if token.quoted or value not in {'true','false'}:",'if False:','test_bcl.ParserContracts.test_BC07_strings_boolean_integer_positions_and_escaping'),
 ('quoted_json_scalar','bcl/compiler.py',"parsed=(strict_json('{\"v\":'+value+'}')['v'] if not token.quoted or value[:1] in '[{' else value)","parsed=strict_json('{\"v\":'+value+'}')['v']",'test_bcl.ParserContracts.test_BC07_strings_boolean_integer_positions_and_escaping'),
 ('enum_adapter','bcl/compiler.py','parsed=param.adapter.validate_python(parsed,strict=True)','parsed=parsed','test_bcl.ParserContracts.test_BC03_structured_errors_and_source_locations'),
 ('permissions','bcl/compiler.py','if not command.permissions<=frozenset(permissions):','if False:','test_bcl.ParserContracts.test_BC05_permissions_checked_for_entire_program'),
 ('version','bcl/compiler.py','if version!=VERSION:','if False:','test_bcl.ParserContracts.test_BC04_bounds_whitespace_comments_and_versions'),
 ('batch_bound','bcl/compiler.py','if len(ops)>=32:','if False:','test_bcl.ParserContracts.test_BC04_bounds_whitespace_comments_and_versions'),
 ('protected_core','bcl/registry.py',"if command.namespace=='core':raise",'if False:raise','test_bcl.ParserContracts.test_BC06_namespaces_conflicts_and_resource_ids'),
 ('registry_revision','bcl/runtime.py','if registry_digest(self.registry)!=self.program.registry_digest:','if False:','test_bcl.RuntimeContracts.test_BR07_registry_revision_invalidates_compiled_program'),
 ('no_replay','bcl/runtime.py',"if self.runtime.state.get('bcl_started'):",'if False:','test_bcl.RuntimeContracts.test_BR05_reused_execution_state_is_never_replayed'),
 ('actor_binding','agent.py',"if self.expected_actor_session is not None and scene.get('actor_session')!=self.expected_actor_session:",'if False:','test_bcl.RuntimeContracts.test_BR04_expected_actor_and_player_identity_are_checked_before_foreign_cleanup'),
 ('full_prevalidation','bcl/runtime.py','compiled=compile_bcl(source,registry,permissions=permissions)','compiled=compile_bcl(source.splitlines()[0],registry,permissions=permissions)','test_bcl.RuntimeContracts.test_BR02_late_compile_error_has_no_observation_effect_or_state_file'),
 ('verified_ack','bcl/runtime.py',"if context['completed_actions'].get(skill,0)>baseline:","if context['completed_actions'].get(skill,0)>=baseline:",'test_bcl.RuntimeContracts.test_BR10_discarded_stale_decision_is_not_acknowledged_as_executed'),
 ('composite_placement_evidence','bcl/runtime.py',"('block','position','item','target','placements')","('block','position','item','target')",'test_bcl.RuntimeContracts.test_BR12_composite_verified_placement_count_is_retained_as_typed_evidence'),
 ('height_hazards','bcl/runtime.py',"if not c['hazards']",'if True','test_bcl.RuntimeContracts.test_BR09_auto_height_uses_only_safe_connected_cells_not_highest_surface'),
 ('height_unknown','bcl/runtime.py',"if not candidates:raise ValueError('Target height is unobserved or unreachable')","if not candidates:return 64.",'test_bcl.RuntimeContracts.test_BR09_auto_height_uses_only_safe_connected_cells_not_highest_surface'),
]

def main():
 results=[]
 for name,file,before,after,test in MUTATIONS:
  with tempfile.TemporaryDirectory(prefix='blockwire-bcl-mutation-') as directory:
   package=Path(directory)/'blockwire';shutil.copytree(ROOT/'python/src/blockwire',package,ignore=shutil.ignore_patterns('__pycache__'))
   path=package/file;source=path.read_text()
   if source.count(before)!=1:results.append({'mutation':name,'status':'INVALID_ANCHOR'});continue
   path.write_text(source.replace(before,after,1))
   env={**os.environ,'PYTHONPATH':str(directory)+os.pathsep+str(ROOT/'python/tests'),'PYTHONDONTWRITEBYTECODE':'1'}
   for k in list(env):
    if k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_')):env.pop(k)
   result=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest',test],cwd=directory,env=env,capture_output=True,text=True,timeout=30)
   output=result.stdout+result.stderr;(OUT/(name+'.log')).write_text(output)
   # Require an actual named test failure/error, not import/syntax failures.
   killed=result.returncode!=0 and ('FAIL: '+test.rsplit('.',1)[1] in output or 'ERROR: '+test.rsplit('.',1)[1] in output)
   results.append({'mutation':name,'status':'KILLED' if killed else 'SURVIVED' if result.returncode==0 else 'INVALID_FAILURE'})
 (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
 return int(any(r['status']!='KILLED' for r in results))
if __name__=='__main__':raise SystemExit(main())
