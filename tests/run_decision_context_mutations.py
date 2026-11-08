#!/usr/bin/env python3
"""Isolated feedback/SDK/series corrections, no provider or game requests."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/decision-context-verification'))/'mutations'
MUTATIONS=[
 ('nav_identity','decision_context.py',"navigation.get('actor_session')!=actor",'False','DC02'),
 ('nav_delivery','decision_context.py',"'current_center_access','cells','edges'","'current_center_access'",'DC01'),
 ('history_evidence','decision_context.py',"('command','status','reason','evidence')","('command','status','reason')",'DC04'),
 ('bounded_nav','decision_context.py',">405",'>999999','DC03'),
 ('readonly_not_progress','decision_context.py',"'read_only_success_is_not_world_progress':True","'read_only_success_is_not_world_progress':False",'DC07'),
 ('result_feedback_loss','bcl/evidence.py',"return {**original,**extra}",'return original','DC04'),
 ('evidence_bound','bcl/evidence.py','len(body)>2048','False','DC05'),
 ('driver_feedback_loss','bcl/runtime.py',"diagnostic_evidence(entry.get('details',{}),",'diagnostic_evidence({},','DC06'),
 ('submit_blocks','bcl/client.py','request_id,wait_for_completion=False','request_id,wait_for_completion=True','DC13'),
 ('legacy_mode','bcl/client.py',"if wait_for_completion and accepted.get('status')=='accepted'","if False and accepted.get('status')=='accepted'",'DC14'),
 ('duplicate_wire','bcl/client.py','if identifier in self.responses:', 'if False:','DC15'),
 ('series_duration','model_limits.py',"integer(self.duration_ms,1,7200000,'series duration')","integer(self.duration_ms,1,99999999,'series duration')",'DC12'),
 ('series_agent_bounds','model_limits.py','        OperationalPolicy(**values)\n\n@dataclasses.dataclass(frozen=True)\nclass TwoHourPolicy','        pass\n\n@dataclasses.dataclass(frozen=True)\nclass TwoHourPolicy','DC12'),
 ('history_bound','decision_context.py','>max_bytes:break','>99999999:break','DC08'),
]
def main():
 OUT.mkdir(parents=True,exist_ok=True);results=[]
 for name,file,before,after,prefix in MUTATIONS:
  with tempfile.TemporaryDirectory(prefix='blockwire-context-mutation-') as directory:
   package=Path(directory)/'blockwire';shutil.copytree(ROOT/'python/src/blockwire',package,ignore=shutil.ignore_patterns('__pycache__'));path=package/file;source=path.read_text()
   if source.count(before)!=1:results.append({'mutation':name,'status':'INVALID_ANCHOR'});continue
   path.write_text(source.replace(before,after,1));env={k:v for k,v in os.environ.items() if not k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_'))};env.update(PYTHONPATH=str(directory)+os.pathsep+str(ROOT/'python/tests'),PYTHONDONTWRITEBYTECODE='1')
   r=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest','discover','-s',str(ROOT/'python/tests'),'-p','test_decision_context.py','-k',prefix],cwd=directory,env=env,capture_output=True,text=True,timeout=40);output=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(output);killed=r.returncode!=0 and ('FAIL: test_'+prefix in output or 'ERROR: test_'+prefix in output);results.append({'mutation':name,'status':'KILLED' if killed else 'SURVIVED' if r.returncode==0 else 'INVALID_FAILURE'})
 (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2));return int(any(r['status']!='KILLED' for r in results))
if __name__=='__main__':raise SystemExit(main())
