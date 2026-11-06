#!/usr/bin/env python3
"""Isolated auto-reporting safety mutations; no working-source edits or Minecraft."""
import json,os,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('BLOCKWIRE_VERIFICATION_DIR',ROOT/'build/auto-event-verification'))/'mutations'
MUTATIONS=[
 ('source_actor','bcl/auto_events.py',"if frame.get('actor_session')!=self.actor:","if False:",'test_auto_events.ReportingContracts.test_AR04_identity_and_sequence_dedup'),
 ('source_sequence','bcl/auto_events.py','if seq<=self.sequence:return','if False:return','test_auto_events.ReportingContracts.test_AR04_identity_and_sequence_dedup'),
 ('session_actor','bcl/auto_events.py','session is None or session.actor_session!=self.actor','session is None','test_auto_events.ReportingContracts.test_AR08_session_actor_fence'),
 ('chat_subscription','bcl/auto_events.py',"'player.chat' in session.subscriptions and policy.chat",'policy.chat','test_auto_events.ReportingContracts.test_AR05_chat_filter_unsubscribe_and_injection_is_only_data'),
 ('chat_sender_filter','bcl/auto_events.py',"policy.chat(name,data,session.store.identity)",'True','test_auto_events.ReportingContracts.test_AR05_chat_filter_unsubscribe_and_injection_is_only_data'),
 ('truncation_is_unknown','bcl/auto_events.py',"if data.get('truncated'):",'if False:','test_auto_events.ReportingContracts.test_AR02_hostile_independent_and_truncation_not_a_leave'),
 ('bounded_truncated_tracking','bcl/auto_events.py','if len(current)<32:','if True:','test_auto_events.ReportingContracts.test_AR20_repeated_truncation_is_bounded_without_false_leave'),
 ('no_false_eviction_leave','bcl/auto_events.py','uid not in current and uid not in unknown','uid not in current','test_auto_events.ReportingContracts.test_AR20_repeated_truncation_is_bounded_without_false_leave'),
 ('radius','bcl/auto_events.py','distance>policy.radius','False','test_auto_events.ReportingContracts.test_AR03_radius_filters_and_fresh_reentry'),
 ('lifecycle_queue_reserve','bcl/gateway.py','if out.qsize()>=48:','if False:','test_auto_events.AutoGatewayContracts.test_AR16_priority_reserve_reports_drops_and_delivers_lifecycle'),
 ('chat_not_command','client.py',"or message.lstrip().startswith('/')",'','test_auto_events.PolicyAndContext.test_AR11_chat_no_commands_or_unsafe_input_no_retry'),
 ('native_actor','client.py',"reply.get('actor_session')!=self._event_actor or type(seq)",'type(seq)','test_native_auto_stream.NativeStreamContracts.test_NS03_wrong_actor_terminal_no_reconnect'),
]
def main():
 OUT.mkdir(parents=True,exist_ok=True);results=[]
 for name,file,before,after,test in MUTATIONS:
  with tempfile.TemporaryDirectory(prefix='blockwire-auto-event-mutation-') as directory:
   package=Path(directory)/'blockwire';shutil.copytree(ROOT/'python/src/blockwire',package,ignore=shutil.ignore_patterns('__pycache__'));path=package/file;source=path.read_text()
   if source.count(before)!=1:results.append({'mutation':name,'status':'INVALID_ANCHOR'});continue
   path.write_text(source.replace(before,after,1));env={k:v for k,v in os.environ.items() if not k.startswith(('BLOCKWIRE_','BLOCK_BRIDGE_'))};env.update(PYTHONPATH=str(directory)+os.pathsep+str(ROOT/'python/tests'),PYTHONDONTWRITEBYTECODE='1')
   r=subprocess.run([str(ROOT/'.venv/bin/python'),'-m','unittest',test],cwd=directory,env=env,capture_output=True,text=True,timeout=30);output=r.stdout+r.stderr;(OUT/(name+'.log')).write_text(output);method=test.rsplit('.',1)[1];killed=r.returncode!=0 and ('FAIL: '+method in output or 'ERROR: '+method in output);results.append({'mutation':name,'status':'KILLED' if killed else 'SURVIVED' if r.returncode==0 else 'INVALID_FAILURE'})
 (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2));return int(any(r['status']!='KILLED' for r in results))
if __name__=='__main__':raise SystemExit(main())
