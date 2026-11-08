#!/usr/bin/env python3
"""Isolated subscription operational-limit mutations; no provider/native requests."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/model-limit-verification'))/'mutations'
MUTATIONS=[
 ('global_requests','total[0]>=self.policy.total_requests','False','ML01'),
 ('non_atomic_admission',"db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');yield db;db.commit()","db.execute('PRAGMA synchronous=FULL');yield db;db.commit()",'ML01'),
 ('agent_requests','own[0]>=self.policy.requests_per_agent','False','ML02'),
 ('concurrency','active>=self.policy.concurrent_requests','False','ML04'),
 ('global_inference_time','total[1]+timeout>self.policy.total_inference_ms','False','ML14'),
 ('agent_inference_time','own[1]+timeout>self.policy.inference_ms_per_agent','False','ML14'),
 ('timeout_refund',"spent=row[2] if state=='UNCERTAIN' else elapsed_ms",'spent=elapsed_ms','ML05'),
 ('restart_reset',"return deadline\n            if state!='CREATED'","deadline=self.clock()+self.policy.duration_ms;return deadline\n            if state!='CREATED'",'ML10'),
 ('duplicate_dispatch',"or row[1]!='RESERVED'",'','ML08'),
 ('duplicate_reconcile',"raise RequestConflict('Terminal model outcome cannot be rewritten')",'return False','ML09'),
 ('restart_unknown',"SET state='UNCERTAIN',spent_ms=?", "SET state='COMPLETED',spent_ms=?",'ML11'),
 ('operation_limit','total+count>self.policy.total_operations or own+count>self.policy.operations_per_agent','False','ML15'),
 ('foreign_agent',"if not row or row[0]!=agent:raise RequestConflict('Not this agent request')", "if not row:raise RequestConflict('Not this agent request')",'ML16'),
 ('stop_deadline',"state!='RUNNING' or now>=deadline",'False','ML17'),
 ('provider_exhaustion',"if agent is not None and self._agent(db,agent)","if False",'ML05'),
 ('subscription_route',"any(subscription_proof.get(k)!=v for k,v in expected.items())",'False','ML19'),
 ('pre_dispatch_admission',"reservation=self.manager.reserve(self.agent,request_id,hashlib.sha256(body).hexdigest())", "answer=self.decider.decide(context);reservation=self.manager.reserve(self.agent,request_id,hashlib.sha256(body).hexdigest())",'ML03'),
]
def main():
 OUT.mkdir(parents=True,exist_ok=True);results=[]
 for name,before,after,prefix in MUTATIONS:
  with tempfile.TemporaryDirectory(prefix='blockwire-model-limits-mutation-') as directory:
   package=Path(directory)/'blockwire';shutil.copytree(ROOT/'python/src/blockwire',package,ignore=shutil.ignore_patterns('__pycache__'));path=package/'model_limits.py';source=path.read_text()
   if source.count(before)!=1:results.append({'mutation':name,'status':'INVALID_ANCHOR'});continue
   path.write_text(source.replace(before,after,1));env={k:v for k,v in os.environ.items() if not k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_'))};env.update(PYTHONPATH=str(directory)+os.pathsep+str(ROOT/'python/tests'),PYTHONDONTWRITEBYTECODE='1')
   r=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest','discover','-s',str(ROOT/'python/tests'),'-p','test_model_limits.py','-k',prefix],cwd=directory,env=env,capture_output=True,text=True,timeout=40);output=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(output);killed=r.returncode!=0 and ('FAIL: test_'+prefix in output or 'ERROR: test_'+prefix in output);results.append({'mutation':name,'status':'KILLED' if killed else 'SURVIVED' if r.returncode==0 else 'INVALID_FAILURE'})
 (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2));return int(any(r['status']!='KILLED' for r in results))
if __name__=='__main__':raise SystemExit(main())
