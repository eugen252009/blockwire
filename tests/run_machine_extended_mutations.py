#!/usr/bin/env python3
"""Isolated extended-envelope mutations. No provider inference or Minecraft."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CASES=[
 ('explicit_opt_in','machine_agent.py','if extended_run else (1800,100,1000)','if True else (1800,100,1000)','Envelope.test_extended_requires_opt_in_before_directory_or_connection'),
 ('extended_duration_bound','machine_agent.py','(86400,1000,1000000)','(864000,1000,1000000)','Envelope.test_extended_requires_opt_in_before_directory_or_connection'),
 ('full_1000_decisions','machine_agent.py','for step in range(max_decisions):','for step in range(min(100,max_decisions)):','Envelope.test_1000_decisions_not_old_100_limit_and_searches_do_not_exhaust_generous_operations'),
 ('search_accounting','machine_agent.py','search_pages+=PAGES','search_pages+=0','Envelope.test_1000_decisions_not_old_100_limit_and_searches_do_not_exhaust_generous_operations'),
 ('post_inference_deadline','machine_agent.py',"if inbox.failure or time.monotonic()>=deadline:raise RuntimeError('Stop before action admission')","if inbox.failure:raise RuntimeError('Stop before action admission')",'Envelope.test_extended_still_checks_deadline_after_inference_before_action'),
 ('mcp_lifetime_bound','machine_mcp.py','if len(owned)>=max_session_tasks:','if False:','MCPBound.test_default_remains_128_and_extended_lifetime_1000_is_bounded'),
 ('mcp_small_default','machine_mcp.py','*,max_session_tasks=128','*,max_session_tasks=1000','MCPBound.test_default_remains_128_and_extended_lifetime_1000_is_bounded'),
 ('mcp_atomic_admission','machine_mcp.py','async with admission_lock:','if True:','MCPBound.test_concurrent_action_and_composition_cannot_overrun_session_bound'),
]
def main():
 bad=[]
 for name,file,old,new,test in CASES:
  with tempfile.TemporaryDirectory(prefix='blockwire-extended-mutation-')as directory:
   root=Path(directory);shutil.copytree(ROOT/'python/src',root/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   p=root/'src/blockwire'/file;source=p.read_text();assert source.count(old)==1,name;changed=source.replace(old,new);compile(changed,str(p),'exec');p.write_text(changed)
   result=subprocess.run([sys.executable,'-m','unittest','test_machine_extended.'+test],cwd=root,env={**os.environ,'PYTHONPATH':str(root/'src')+os.pathsep+str(ROOT/'python/tests')},capture_output=True,text=True,timeout=30)
   killed=result.returncode==1 and 'FAIL: '+test.split('.')[-1]in result.stderr and 'FAILED (failures='in result.stderr and 'ERROR:'not in result.stderr
   print(name,'KILLED'if killed else'INVALID_OR_SURVIVED',flush=True)
   if not killed:bad.append(name);print(result.stdout+result.stderr)
 return bool(bad)
if __name__=='__main__':raise SystemExit(main())
