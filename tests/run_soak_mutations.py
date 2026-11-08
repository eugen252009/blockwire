#!/usr/bin/env python3
"""Isolated campaign-prerequisite safety mutations; no live Minecraft or source edits."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/soak-verification'))/'mutations'
MUTATIONS=[
 ('empty_classification','soak.py',"if error.diagnostic.code!='EMPTY_PROGRAM':raise","raise",'test_soak.Decisions.test_SK01_empty_whitespace_comments_headers_do_not_schedule'),
 ('malformed_not_empty','soak.py',"if error.diagnostic.code!='EMPTY_PROGRAM':raise","if False:raise",'test_soak.Decisions.test_SK03_malformed_full_decision_has_no_effects'),
 ('no_command_dispatch','soak.py','if prepared.program is not None:','if True:','test_soak.Decisions.test_SK01_empty_whitespace_comments_headers_do_not_schedule'),
 ('feedback_not_lost','soak.py','if decision.feedback:','if decision.feedback and prepared.program:','test_soak.Decisions.test_SK02_finish_feedback_without_bcl_is_not_lost'),
 ('no_false_gameplay','soak.py',"'gameplay_verified':False","'gameplay_verified':True",'test_soak.Decisions.test_SK05_valid_multicommand_uses_existing_compiler_and_one_submission'),
 ('memory_bound','soak.py','>8192:raise ValueError(\'Model memory bound\')',">999999:raise ValueError('Model memory bound')",'test_soak.Decisions.test_SK13_frame_memory_and_chat_validated_before_effects'),
 ('idle_budget','soak.py','self.consecutive>=self.maximum','False','test_soak.Decisions.test_SK07_no_command_loop_budget_includes_feedback'),
 ('unknown_transport','soak.py',"raise UnknownNoRetry('UNKNOWN_NO_RETRY: receipt/transport uncertain') from error","return result",'test_soak.Decisions.test_SK09_lost_receipt_is_unknown_without_retry'),
 ('known_task_cancel','soak.py','await client.cancel(identifier)','pass','test_soak.Decisions.test_SK10_cancel_known_task_uses_same_owned_task_once'),
 ('uncertain_cancel','soak.py',"except Exception as error:raise UnknownNoRetry('UNKNOWN_NO_RETRY: cancellation unconfirmed') from error","except Exception as error:cancellation_confirmed=True;raise asyncio.CancelledError()",'test_soak.Decisions.test_SK11_uncertain_cancel_never_claims_cleanup'),
 ('gate_missing','soak.py',"checks.get(name)!='PASS'",'False','test_soak.Lifecycle.test_SK18_skipped_lifecycle_and_missing_gates_block'),
 ('completed_proofs','soak.py','any(proofs.get(k) is not True for k in FINALIZATION_PROOFS)','False','test_soak.Lifecycle.test_SK15_complete_requires_all_independent_artifacts'),
 ('unknown_sticky','soak.py',"uncertain=self.value['unknown'] or unknown",'uncertain=unknown','test_soak.Lifecycle.test_SK16_unknown_is_sticky_and_never_continuable_completion'),
 ('partial_replay','soak.py',"path.suffix!='.mcpr'","False",'test_soak.Lifecycle.test_SK19_partial_replay_is_not_finalization'),
]
def main():
 OUT.mkdir(parents=True,exist_ok=True);results=[]
 for name,file,before,after,test in MUTATIONS:
  with tempfile.TemporaryDirectory(prefix='blockwire-soak-mutation-') as directory:
   package=Path(directory)/'blockwire';shutil.copytree(ROOT/'python/src/blockwire',package,ignore=shutil.ignore_patterns('__pycache__'));path=package/file;source=path.read_text()
   if source.count(before)!=1:results.append({'mutation':name,'status':'INVALID_ANCHOR'});continue
   path.write_text(source.replace(before,after,1));env={k:v for k,v in os.environ.items() if not k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_'))};env.update(PYTHONPATH=str(directory)+os.pathsep+str(ROOT/'python/tests'),PYTHONDONTWRITEBYTECODE='1')
   r=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest',test],cwd=directory,env=env,capture_output=True,text=True,timeout=30);output=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(output);method=test.rsplit('.',1)[1];killed=r.returncode!=0 and ('FAIL: '+method in output or 'ERROR: '+method in output);results.append({'mutation':name,'status':'KILLED' if killed else 'SURVIVED' if r.returncode==0 else 'INVALID_FAILURE'})
 (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2));return int(any(r['status']!='KILLED' for r in results))
if __name__=='__main__':raise SystemExit(main())
