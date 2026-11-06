#!/usr/bin/env python3
"""Isolated feedback/input-policy safety mutations; never edit working sources."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/feedback-verification'))/'mutations'
MUTATIONS=[
 ('strict_proposal','feedback.py',"extra='forbid'","extra='ignore'",'test_feedback.FeedbackContracts.test_FB04_strict_bounded_schema'),
 ('proposal_conflict','feedback.py','if old[1]!=digest:','if False:','test_feedback.FeedbackContracts.test_FB02_durable_dedup_and_conflict'),
 ('proposal_scope','feedback.py','SELECT ticket,status,body,review FROM feedback WHERE owner=? AND session=? AND feedback_id=?','SELECT ticket,status,body,review FROM feedback WHERE ? IS NOT NULL AND ? IS NOT NULL AND feedback_id=?','test_feedback.FeedbackContracts.test_FB03_scope_cannot_read_other_agent_or_session'),
 ('proposal_budget','feedback.py','count>=self.policy.max_feedback_per_session','False','test_feedback.FeedbackContracts.test_FB06_proposal_budget_does_not_reset_on_duplicate'),
 ('session_budget','feedback.py','used+count>p.max_session_operations','False','test_feedback.FeedbackContracts.test_FB08_operation_budget_and_replay'),
 ('aggregate_budget','feedback.py','or total+count>p.max_actor_operations','','test_feedback.FeedbackContracts.test_FB09_total_budget_cannot_be_reset_with_new_labels'),
 ('opcode_allowlist','feedback.py','not opcodes<=p.allowed_opcodes','False','test_feedback.FeedbackContracts.test_FB10_opcode_and_frame_allowlist'),
 ('audit_capacity','feedback.py','>=self.MAX_AUDIT','>=1000000','test_feedback.FeedbackContracts.test_FB11_audit_preserves_source_and_bounded_capacity'),
 ('private_store','feedback.py','self.directory.stat().st_mode&0o077','False','test_feedback.FeedbackContracts.test_FB05_private_permissions_and_symlink_rejection'),
 ('operator_review','feedback.py',"status not in {'planned','declined'}","False",'test_feedback.FeedbackContracts.test_FB07_operator_review_does_not_implement'),
 ('mcp_tool_policy','mcp_server.py','name not in allowed','False','test_feedback.FeedbackMCP.test_FB18_default_control_profile_denies_commands_before_native'),
 ('mcp_bound_identity','mcp_server.py','identity!=feedback_identity','False','test_feedback.FeedbackMCP.test_FB21_configured_identity_cannot_be_forged'),
 ('mcp_actor','mcp_server.py',"scene.get('actor_session')!=actor_session",'False','test_feedback.FeedbackMCP.test_FB17_mcp_feedback_live_binding_and_no_operator_review_tool'),
 ('mcp_sensitive_text','mcp_server.py',"if name in {'type_menu_text','run_command','send_chat'}:",'if False:','test_feedback.FeedbackMCP.test_FB19_raw_sensitive_text_is_not_persisted'),
 ('gateway_admission','bcl/gateway.py',"await asyncio.to_thread(self.feedback.admit_bcl,session.store.identity,sid,request_id,msg['source'],program)",'pass','test_feedback.FeedbackGateway.test_FB14_budget_blocks_before_effects_and_survives_reconnect'),
 ('cancel_escape','bcl/gateway.py',"if kind not in {'cancel','feedback_status'}:",'if True:','test_feedback.FeedbackGateway.test_FB15_cancel_remains_available_with_full_audit'),
]
def main():
 OUT.mkdir(parents=True,exist_ok=True);results=[]
 for name,file,before,after,test in MUTATIONS:
  with tempfile.TemporaryDirectory(prefix='blockwire-feedback-mutation-') as directory:
   package=Path(directory)/'blockwire';shutil.copytree(ROOT/'python/src/blockwire',package,ignore=shutil.ignore_patterns('__pycache__'));path=package/file;source=path.read_text()
   if source.count(before)!=1:results.append({'mutation':name,'status':'INVALID_ANCHOR'});continue
   path.write_text(source.replace(before,after,1));env={k:v for k,v in os.environ.items() if not k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_'))};env.update(PYTHONPATH=str(directory)+os.pathsep+str(ROOT/'python/tests'),PYTHONDONTWRITEBYTECODE='1')
   r=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest',test],cwd=directory,env=env,capture_output=True,text=True,timeout=30);output=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(output);method=test.rsplit('.',1)[1];killed=r.returncode!=0 and ('FAIL: '+method in output or 'ERROR: '+method in output);results.append({'mutation':name,'status':'KILLED' if killed else 'SURVIVED' if r.returncode==0 else 'INVALID_FAILURE'})
 (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2));return int(any(r['status']!='KILLED' for r in results))
if __name__=='__main__':raise SystemExit(main())
