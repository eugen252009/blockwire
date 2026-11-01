#!/usr/bin/env python3
"""Isolated BCL parser/dispatch mutations. No working-source edits or Minecraft access."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/bcl-verification'))/'mutations'
OUT.mkdir(parents=True,exist_ok=True)
MUTATIONS=[
 ('modal_cycle','bcl/modal.py','(setting.values.index(current)+1)%len(setting.values)','setting.values.index(current)','test_bcl_modal.ModalContracts.test_BS01_generic_binary_three_and_four_value_cycles_wrap'),
 ('request_dedup','bcl/modal.py',"if key in self.state['requests']:",'if False:','test_bcl_modal.ModalContracts.test_BS04_durable_dedup_and_evicted_ids_cannot_repeat_cycles'),
 ('request_source_conflict','bcl/modal.py',"if record['source_digest']!=digest:",'if False:','test_bcl_modal.ModalContracts.test_BS04_durable_dedup_and_evicted_ids_cannot_repeat_cycles'),
 ('modal_snapshot','bcl/modal.py',"contexts.append(Modal(**{k:staged['modal'][k] for k in Modal.__dataclass_fields__}))",'contexts.append(Modal())','test_bcl_modal.ModalContracts.test_BS03_addendum_sequence_has_immutable_per_action_snapshots'),
 ('commit_before_publish','bcl/modal.py','self.store.save(staged)  # Atomic SQLite commit BEFORE publishing state or accepting actions.\n        self.state=staged','self.state=staged\n        self.store.save(staged)','test_bcl_modal.ModalContracts.test_BS09_failed_durable_commit_never_publishes_modal_transition'),
 ('unsubscribe','bcl/modal.py',"elif op.opcode=='E1':subs.discard(event)","elif op.opcode=='E1':pass",'test_bcl_modal.ModalContracts.test_BS05_sessions_and_subscriptions_are_isolated_and_pending_work_not_replayed'),
 ('relative_anchor','bcl/runtime.py','values[axis]+=position[i]','values[axis]=values[axis]','test_bcl_modal.ModalContracts.test_BS06_relative_anchor_is_fresh_at_execution_and_explicit_mode_is_one_shot'),
 ('continue_policy','bcl/runtime.py',"return mode=='continue'",'return False','test_bcl_modal.ModalExecutionContracts.test_BS07_continue_policy_does_not_turn_failed_operation_into_success'),
 ('websocket_auth','bcl/gateway.py',"not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+self.token)",'False','test_bcl_websocket.WebSocketContracts.test_BW06_auth_certificate_hostname_and_plaintext_fail_closed'),
 ('incoming_events','bcl/compiler.py',"if command.category=='event_out':",'if False:','test_bcl_websocket.WebSocketContracts.test_BW01_single_multiline_settings_and_direction'),
 ('duplicate_assignment','bcl/compiler.py','if param.name in assigned:','if False:','test_bcl.ParserContracts.test_BC03_structured_errors_and_source_locations'),
 ('boolean_lexeme','bcl/compiler.py',"if token.quoted or value not in {'true','false'}:",'if False:','test_bcl.ParserContracts.test_BC07_strings_boolean_integer_positions_and_escaping'),
 ('enum_adapter','bcl/compiler.py','parsed=param.adapter.validate_python(parsed,strict=True)','parsed=parsed','test_bcl.ParserContracts.test_BC03_structured_errors_and_source_locations'),
 ('permissions','bcl/compiler.py','if not command.permissions<=frozenset(permissions):','if False:','test_bcl.ParserContracts.test_BC05_permissions_checked_for_entire_program'),
 ('version','bcl/compiler.py','if version!=VERSION:','if False:','test_bcl.ParserContracts.test_BC04_bounds_whitespace_comments_and_versions'),
 ('batch_bound','bcl/compiler.py','if len(ops)>=32:','if False:','test_bcl.ParserContracts.test_BC04_bounds_whitespace_comments_and_versions'),
 ('protected_core','bcl/registry.py',"if command.namespace=='core':raise",'if False:raise','test_bcl.ParserContracts.test_BC06_namespaces_conflicts_and_resource_ids'),
 ('registry_revision','bcl/runtime.py','if registry_digest(self.registry)!=self.program.registry_digest:','if False:','test_bcl.RuntimeContracts.test_BR07_registry_revision_invalidates_compiled_program'),
 ('no_replay','bcl/runtime.py',"if self.runtime.state.get('bcl_started'):",'if False:','test_bcl.RuntimeContracts.test_BR05_reused_execution_state_is_never_replayed'),
 ('actor_binding','agent.py',"if self.expected_actor_session is not None and scene.get('actor_session')!=self.expected_actor_session:",'if False:','test_bcl.RuntimeContracts.test_BR04_expected_actor_and_player_identity_are_checked_before_foreign_cleanup'),
 ('full_prevalidation','bcl/runtime.py','self.program=compile_bcl(source,registry,permissions=permissions)','self.program=compile_bcl(source.splitlines()[0],registry,permissions=permissions)','test_bcl.RuntimeContracts.test_BR02_late_compile_error_has_no_observation_effect_or_state_file'),
 ('verified_ack','bcl/runtime.py',"if context['completed_actions'].get(skill,0)>baseline:","if context['completed_actions'].get(skill,0)>=baseline:",'test_bcl.RuntimeContracts.test_BR10_discarded_stale_decision_is_not_acknowledged_as_executed'),
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
