"""Virtual clocks / isolated SQLite only. NOT two-hour Minecraft acceptance."""
import dataclasses,hashlib,json,tempfile,unittest
from pathlib import Path
from blockwire.model_limits import OperationalPolicy,TwoHourPolicy,ModelLimits,LimitExceeded,RequestConflict
from blockwire.session_policy import TwoHourSessionProfile,SessionPacing,observed_state_key,action_key
from blockwire.soak import prepare_decision,UnknownNoRetry
from blockwire.bcl import default_commands
PROOF={'provider':'openai-codex','model':'gpt-6-luna','oauth':True,'subscription':True,'api':'openai-codex-responses','base_url':'https://chatgpt.com/backend-api'}
DIGEST='a'*64
class Profile(unittest.TestCase):
 def test_TH01_opt_in_legacy_limits_unchanged(self):
  old=OperationalPolicy('old',('a','b'));p=TwoHourPolicy('new',('a','b'));self.assertEqual((old.duration_ms,old.requests_per_agent,old.operations_per_agent),(1800000,30,300));self.assertEqual((p.duration_ms,p.requests_per_agent,p.total_requests,p.operations_per_agent,p.total_operations),(9000000,720,1440,9000,18000));self.assertEqual((p.request_timeout_ms,p.concurrent_requests),(90000,2))
 def test_TH02_bounded_policy_no_provider_or_timeout_relaxation(self):
  p=TwoHourPolicy('new',('a','b'))
  for field,value in [('duration_ms',9000001),('requests_per_agent',721),('total_requests',1441),('operations_per_agent',9001),('total_operations',18001),('request_timeout_ms',90001),('concurrent_requests',3),('inference_ms_per_agent',7200001),('total_inference_ms',14400001),('requests_per_agent',True),('model','fallback'),('agents',('a','b','c'))]:
   with self.subTest(field=field),self.assertRaises(ValueError):dataclasses.replace(p,**{field:value})
 def test_TH03_gameplay_clock_starts_after_admission_preserves_cleanup(self):
  p=TwoHourSessionProfile();self.assertEqual(p.play_deadline_ms(9000000,900000),8100000)
  with self.assertRaises(RuntimeError):p.play_deadline_ms(9000000,900001)
  with self.assertRaises(ValueError):p.play_deadline_ms(9000000,True)
 def test_TH04_model_cannot_extend_profile(self):
  for kw in [{'gameplay_seconds':7201},{'minimum_decision_interval':0},{'identical_failure_limit':999},{'max_frame_operations':32},{'preparation_seconds':True}]:
   with self.assertRaises(ValueError):TwoHourSessionProfile(**kw)
 def test_TH05_gateway_caps_match_inference_frame_budget(self):
  p=TwoHourSessionProfile();limits=p.model_policy('new',('a','b'));gateway=p.input_policy(frozenset({'core:I0'}));self.assertEqual(gateway.max_session_operations,limits.operations_per_agent);self.assertEqual(gateway.max_actor_operations,9000);self.assertLess(720*12+7,gateway.max_session_operations);self.assertEqual(gateway.allowed_opcodes,frozenset({'core:I0'}));self.assertEqual(gateway.max_frame_operations,12)
 def test_TH06_full_1440_request_audit_and_budgets_fit_without_reset(self):
  with tempfile.TemporaryDirectory()as root:
   p=TwoHourPolicy('two-hour',('a','b'));m=ModelLimits(Path(root)/'ledger',p,subscription_proof=PROOF,clock_ms=lambda:1000000);deadline=m.start()
   for i in range(720):
    for agent in p.agents:
     rid=agent+str(i);m.reserve(agent,rid,DIGEST);m.dispatch(agent,rid);m.finish(agent,rid,elapsed_ms=1);m.admit_operations(agent,'f'+rid,'I0',12)
   self.assertEqual(m.snapshot()['requests'],1440);self.assertEqual(m.snapshot()['operations'],17280)
   with m.db()as db:self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],4320)
   with self.assertRaisesRegex(LimitExceeded,'global_request_budget'):m.reserve('a','overflow',DIGEST)
   same=ModelLimits(m.directory,p,subscription_proof=PROOF,clock_ms=lambda:1000000);self.assertEqual(same.start(),deadline);self.assertEqual(same.snapshot()['requests'],1440);self.assertLess(m.path.stat().st_size,16*1024**2);m.stop('done');self.assertEqual(m.snapshot()['state'],'STOPPED')
 def test_TH07_no_existing_ledger_upgrade_or_reset(self):
  with tempfile.TemporaryDirectory()as root:
   path=Path(root)/'ledger';old=OperationalPolicy('same',('a','b'));m=ModelLimits(path,old,subscription_proof=PROOF);deadline=m.start()
   with self.assertRaises(RequestConflict):ModelLimits(path,TwoHourPolicy('same',('a','b')),subscription_proof=PROOF)
   self.assertEqual(ModelLimits(path,old,subscription_proof=PROOF).start(),deadline);self.assertEqual(m.audit_capacity,2000)
 def test_TH24_profile_identity_cannot_upgrade_legacy_with_equal_quotas(self):
  with tempfile.TemporaryDirectory()as root:
   old=OperationalPolicy('same',('a','b'));path=Path(root)/'ledger';ModelLimits(path,old,subscription_proof=PROOF)
   lowered=TwoHourPolicy(**dataclasses.asdict(old))
   with self.assertRaises(RequestConflict):ModelLimits(path,lowered,subscription_proof=PROOF)
 def test_TH08_two_hour_audit_full_still_allows_stop(self):
  with tempfile.TemporaryDirectory()as root:
   m=ModelLimits(Path(root)/'ledger',TwoHourPolicy('new',('a',)),subscription_proof=PROOF);m.start();self.assertEqual(m.audit_capacity,8192)
   with m.db()as db:db.executemany('INSERT INTO events(kind) VALUES(?)',[('fixture',)]*8192)
   with self.assertRaisesRegex(LimitExceeded,'event_capacity'):m.reserve('a','overflow',DIGEST)
   m.stop('F8');self.assertEqual(m.snapshot()['state'],'STOPPED')
 def test_TH09_uncertainty_halts_only_own_agent_not_peer(self):
  with tempfile.TemporaryDirectory()as root:
   m=ModelLimits(Path(root)/'ledger',TwoHourPolicy('new',('a','b')),subscription_proof=PROOF);m.start();m.reserve('a','lost',DIGEST);m.dispatch('a','lost');m.finish('a','lost',elapsed_ms=1,state='UNCERTAIN')
   with self.assertRaises(LimitExceeded):m.reserve('a','retry',DIGEST)
   m.reserve('b','healthy',DIGEST);self.assertEqual(m.snapshot()['agents']['a']['inference_ms_charged'],90000)

class Pacing(unittest.TestCase):
 def setUp(self):
  self.registry=default_commands();self.prepared=prepare_decision({'source':'C1 3 true'},self.registry);self.scene={'actor_session':'actor','position':[.6,98,.6],'visible_blocks':{'palette':['minecraft:dirt'],'runs':[[0,0,-1,0,1]],'origin':[0,98,0]}};self.inv={'actor_session':'actor','items':[]};self.nav={'actor_session':'actor','profile':'stepped_full_blocks_v1','cells':[],'edges':[]};self.key=observed_state_key(self.scene,self.inv,self.nav)
 def test_TH10_known_failure_backoff_then_fresh_decision(self):
  p=SessionPacing(7200);self.assertTrue(p.permit(self.prepared,self.key,0));p.record(self.prepared,self.key,0,known_terminal=True,successful=False);self.assertEqual(p.delay(1),29)
  with self.assertRaises(RuntimeError):p.permit(self.prepared,self.key,29)
  self.assertTrue(p.permit(self.prepared,self.key,30))
 def test_TH11_same_failed_state_blocked_after_two_no_native_replay(self):
  p=SessionPacing(7200)
  for now in [0,30]:self.assertTrue(p.permit(self.prepared,self.key,now));p.record(self.prepared,self.key,now,known_terminal=True,successful=False)
  self.assertFalse(p.permit(self.prepared,self.key,60));p.rejected(60);self.assertEqual(p.delay(60),120);self.assertEqual(p.known_failures,2)
 def test_TH12_comments_spacing_not_distinct_action(self):
  other=prepare_decision({'source':'# comment\n   C1   3 true\n'},self.registry);self.assertEqual(action_key(self.prepared,self.key),action_key(other,self.key))
 def test_TH13_partial_inventory_gain_is_new_observed_state(self):
  p=SessionPacing(7200)
  for now in [0,30]:p.record(self.prepared,self.key,now,known_terminal=True,successful=False)
  self.inv['items']=[{'item':'minecraft:spruce_log','count':2}];new=observed_state_key(self.scene,self.inv,self.nav);self.assertNotEqual(self.key,new);self.assertTrue(p.permit(self.prepared,new,60))
 def test_TH14_timestamp_or_tiny_position_noise_not_progress(self):
  self.scene.update(sampled_at_ms=999,health=20);self.scene['position'][0]+=.001;self.nav['sampled_at_ms']=444;self.assertEqual(self.key,observed_state_key(self.scene,self.inv,self.nav))
 def test_TH15_actor_mismatch_or_unbounded_data_rejected(self):
  self.inv['actor_session']='other'
  with self.assertRaises(ValueError):observed_state_key(self.scene,self.inv,self.nav)
  self.inv['actor_session']='actor';self.scene['visible_blocks']={'large':'x'*140000}
  with self.assertRaises(ValueError):observed_state_key(self.scene,self.inv,self.nav)
 def test_TH16_unknown_is_sticky_never_backoff_and_retry(self):
  p=SessionPacing(7200)
  with self.assertRaises(UnknownNoRetry):p.record(self.prepared,self.key,0,known_terminal=False,successful=False)
  with self.assertRaises(UnknownNoRetry):p.permit(self.prepared,self.key,120)
  self.assertEqual(p.known_failures,0)
 def test_TH17_monotonic_clock_regression_latches_closed(self):
  p=SessionPacing(7200);p.check(10)
  with self.assertRaises(UnknownNoRetry):p.check(9)
  with self.assertRaises(UnknownNoRetry):p.check(11)
 def test_TH18_virtual_two_hour_window_over_old_thirty_decisions(self):
  p=SessionPacing(7200);prepared=prepare_decision({'source':'I0'},self.registry);calls=0
  for now in range(0,7200,10):
   self.assertTrue(p.permit(prepared,self.key,now));p.record(prepared,self.key,now,known_terminal=True,successful=True);calls+=1
  self.assertEqual(calls,720)
  with self.assertRaises(TimeoutError):p.permit(prepared,self.key,7200)
 def test_TH19_empty_decisions_can_idle_without_bcl_submission(self):
  p=SessionPacing(7200);empty=prepare_decision({'source':''},self.registry)
  for now in range(0,7200,30):
   self.assertTrue(p.permit(empty,self.key,now));p.record(empty,self.key,now,known_terminal=True,successful=False);self.assertEqual(p.next_due,now+30)
  self.assertEqual(p.idle_decisions,240);self.assertEqual(p.known_failures,0)
 def test_TH20_bad_terminal_boolean_not_coerced(self):
  with self.assertRaises(ValueError):SessionPacing(7200).record(self.prepared,self.key,0,known_terminal='yes',successful=False)
 def test_TH21_more_than_eight_known_blocks_do_not_end_session(self):
  p=SessionPacing(7200)
  for i in range(100):
   key=hashlib.sha256(str(i).encode()).hexdigest();self.assertTrue(p.permit(self.prepared,key,i*30));p.record(self.prepared,key,i*30,known_terminal=True,successful=False)
  self.assertEqual(p.known_failures,100);self.assertFalse(p.terminal)
 def test_TH22_fixed_failure_memory_capacity(self):
  p=SessionPacing(100000);p.failures={str(i):1 for i in range(720)}
  with self.assertRaisesRegex(RuntimeError,'capacity'):p.record(self.prepared,self.key,0,known_terminal=True,successful=False)
 def test_TH23_nonfinite_time_and_position_rejected(self):
  for bad in [True,float('nan'),float('inf')]:
   with self.assertRaises(ValueError):SessionPacing(bad)
  self.scene['position'][0]=float('nan')
  with self.assertRaises(ValueError):observed_state_key(self.scene,self.inv,self.nav)
if __name__=='__main__':unittest.main()
