#!/usr/bin/env python3
"""Isolated machine action/report/interrupt mutations. No external model or game."""
import os
from pathlib import Path
import shutil,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
CASES=[
 ('action_only','bcl/machine.py','    return registry',"    from .registry import default_commands\n    registry._commands['core','V0']=default_commands().resolve('core','V0')\n    return registry",'MachineSyntax.test_action_only_no_queries_or_planners_or_settings'),
 ('lease_bound','machine_actions.py','ticks=min(6,','ticks=min(100,','MachineSyntax.test_pulses_keep_short_leases_and_actor_replacement_stops_renewal'),
 ('actor_fence','machine_actions.py','(actor is not None and session!=actor)','False','MachineSyntax.test_pulses_keep_short_leases_and_actor_replacement_stops_renewal'),
 ('fresh_release','machine_actions.py',"current['tick']>before['tick']","current['tick']>=before['tick']",'MachineWire.test_stale_release_quarantines_without_replay'),
 ('strict_release_map','machine_actions.py','and set(inputs)==KEYS','', 'MachineSyntax.test_release_requires_complete_false_native_input_map'),
 ('owned_release','machine_actions.py',"row.get('remote_owned_inputs')==[]","True",'MachineSyntax.test_release_requires_complete_false_native_input_map'),
 ('interrupt_queue','bcl/machine_control.py','self.jobs.close_session(self.sid)','self.jobs.cancel(self.jobs.active) if self.jobs.active else None','MachineWire.test_reporting_during_action_and_priority_cancel_flushes_queue'),
 ('no_implicit_resume','bcl/machine_control.py',"self.state='released'","self.state='ready'",'MachineWire.test_reporting_during_action_and_priority_cancel_flushes_queue'),
 ('report_concurrent','bcl/gateway.py',"if not wanted:continue","if not wanted or self.jobs.active:continue",'MachineWire.test_reporting_during_action_and_priority_cancel_flushes_queue'),
 ('resume_generation','bcl/machine_control.py',"if generation!=self.generation:raise ValueError('Interrupted during resume')","pass # lost interrupt race",'MachineWire.test_interrupt_during_resume_invalidates_the_pending_release_proof'),
 ('audit_independent_cancel','bcl/gateway.py',"if kind=='interrupt':","if kind=='interrupt' and self.feedback is None:",'MachineWire.test_emergency_interrupt_bypasses_failed_audit_admission'),
 ('fresh_heartbeat','bcl/gateway.py',"if not changed and time.monotonic()-report_sent.get(name,0.)<2.:continue","if not changed:continue",'MachineWire.test_unchanged_state_has_fresh_heartbeat_not_permanent_stale_cache'),
 ('wire_gap','bcl/client.py',"message['sequence']!=self.wire_sequence+1","False",'MachineWire.test_wire_sequence_gap_fails_closed'),
 ('unknown_queue_halt','bcl/runtime.py',"self.halted=True\n                        for queued in self.queue:self.jobs[queued]['cancelled']=True","self.halted=False # unsafe continuation",'MachineWire.test_query_rejection_and_receipt_without_release_is_not_completion'),
]

def main():
 bad=[]
 for name,filename,before,after,test in CASES:
  with tempfile.TemporaryDirectory(prefix='blockwire-machine-mutation-')as folder:
   root=Path(folder);shutil.copytree(ROOT/'python/src',root/'src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   path=root/'src/blockwire'/filename;source=path.read_text();assert source.count(before)==1,name;source=source.replace(before,after);compile(source,str(path),'exec');path.write_text(source)
   env={**os.environ,'PYTHONPATH':str(root/'src')+os.pathsep+str(ROOT/'python/tests')}
   result=subprocess.run([sys.executable,'-m','unittest','test_machine_profile.'+test],cwd=root,env=env,capture_output=True,text=True,timeout=30)
   killed=result.returncode!=0 and ('FAIL: '+test.split('.')[-1] in result.stderr or 'ERROR: '+test.split('.')[-1] in result.stderr)
   print(name,'KILLED'if killed else'NOT_KILLED',flush=True)
   if not killed:bad.append(name);print(result.stdout+result.stderr)
 return bool(bad)
if __name__=='__main__':sys.exit(main())
