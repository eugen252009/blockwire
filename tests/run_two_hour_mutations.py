#!/usr/bin/env python3
"""Isolated two-hour policy/scheduling mutations. No model/native processes."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/two-hour-verification'))/'mutations'
MUTATIONS=[
 ('duration_cap','model_limits.py',"('duration_ms',9000000)","('duration_ms',9000001)",'TH02'),
 ('request_cap','model_limits.py',"('requests_per_agent',720)","('requests_per_agent',721)",'TH02'),
 ('global_request_cap','model_limits.py',"('total_requests',1440)","('total_requests',1441)",'TH02'),
 ('request_timeout','model_limits.py',"integer(self.request_timeout_ms,1,90000,'request timeout')","integer(self.request_timeout_ms,1,180000,'request timeout')",'TH02'),
 ('audit_too_small','model_limits.py','return 8192 if isinstance(self.policy,TwoHourPolicy) else 2000','return 2000','TH06'),
 ('persisted_profile_identity','model_limits.py',"if isinstance(policy,TwoHourPolicy):configuration['profile']='two_hour_v1'","if False:configuration['profile']='two_hour_v1'",'TH24'),
 ('legacy_audit_widened','model_limits.py','return 8192 if isinstance(self.policy,TwoHourPolicy) else 2000','return 8192','TH07'),
 ('cleanup_envelope','session_policy.py','needed=(self.gameplay_seconds+self.finalization_seconds)*1000','needed=self.gameplay_seconds*1000','TH03'),
 ('play_deadline','session_policy.py','return now_ms+self.gameplay_seconds*1000','return now_ms+self.gameplay_seconds*1000+1','TH03'),
 ('repeat_permit','session_policy.py','self.failures.get(action_key(prepared,state_key),0)<self.profile.identical_failure_limit','True','TH11'),
 ('uncertainty_retry','session_policy.py','if not known_terminal:self.terminal=True;raise','if False:self.terminal=True;raise','TH16'),
 ('blocked_backoff','session_policy.py','delay=self.profile.blocked_backoff_seconds','delay=self.profile.minimum_decision_interval','TH10'),
 ('idle_backoff','session_policy.py','delay=self.profile.idle_backoff_seconds','delay=self.profile.minimum_decision_interval','TH19'),
 ('deadline_boundary','session_policy.py','if now>=self.deadline:','if now>self.deadline:','TH18'),
 ('actor_consistency','session_policy.py',"or inventory.get('actor_session')!=actor or navigation.get('actor_session')!=actor",'','TH15'),
 ('ignore_compiler_location','session_policy.py',"row.pop('line');row.pop('column');",'','TH12'),
 ('failure_memory_cap','session_policy.py','len(self.failures)>=720','False','TH22'),
 ('clock_regression','session_policy.py','self.last_time is not None and now<self.last_time','False','TH17'),
 ('record_failure','session_policy.py','self.failures[key]=self.failures.get(key,0)+1','self.failures[key]=0','TH11'),
 ('observed_state_key','session_policy.py','[state_key,operations]','[operations]','TH13'),
 ('gateway_operation_cap','session_policy.py','max_session_operations=9000','max_session_operations=300','TH05'),
 ('gateway_allowlist','session_policy.py','allowed_opcodes=allowed_opcodes','allowed_opcodes=None','TH05'),
]
def main():
 OUT.mkdir(parents=True,exist_ok=True);results=[]
 for name,file,before,after,prefix in MUTATIONS:
  with tempfile.TemporaryDirectory(prefix='blockwire-two-hour-mutation-')as directory:
   package=Path(directory)/'blockwire';shutil.copytree(ROOT/'python/src/blockwire',package,ignore=shutil.ignore_patterns('__pycache__'));p=package/file;source=p.read_text()
   if source.count(before)!=1:results.append({'mutation':name,'status':'INVALID_ANCHOR'});continue
   p.write_text(source.replace(before,after,1));env={k:v for k,v in os.environ.items()if not k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_'))};env.update(PYTHONPATH=directory+os.pathsep+str(ROOT/'python/tests'),PYTHONDONTWRITEBYTECODE='1')
   r=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest','discover','-s',str(ROOT/'python/tests'),'-p','test_two_hour_sessions.py','-k',prefix],cwd=directory,env=env,capture_output=True,text=True,timeout=60);out=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(out);killed=r.returncode!=0 and ('FAIL: test_'+prefix in out or 'ERROR: test_'+prefix in out);results.append({'mutation':name,'status':'KILLED'if killed else 'SURVIVED'if r.returncode==0 else 'INVALID_FAILURE'})
 (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2));return int(any(x['status']!='KILLED'for x in results))
if __name__=='__main__':raise SystemExit(main())
