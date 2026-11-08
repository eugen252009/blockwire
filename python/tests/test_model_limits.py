"""Deterministic subscription operational limits; no model/network/Minecraft calls."""
import concurrent.futures,dataclasses,hashlib,json,os,tempfile,unittest
from pathlib import Path
from blockwire.model_limits import ModelLimits,OperationalPolicy,LimitedDecider,LimitExceeded,RequestConflict
PROOF={'provider':'openai-codex','model':'gpt-6-luna','oauth':True,'subscription':True,'api':'openai-codex-responses','base_url':'https://chatgpt.com/backend-api'}
DIGEST=hashlib.sha256(b'private isolated context').hexdigest()

def process_reserve(args):
    directory,policy,identifier=args
    try:return ModelLimits(directory,policy,subscription_proof=PROOF).reserve('a',identifier,DIGEST)['new']
    except LimitExceeded:return False

class Adapter:
    timeout=90.
    def __init__(self,answer=None,error=None):self.calls=0;self.answer={} if answer is None else answer;self.error=error
    def decide(self,context):
        self.calls+=1
        if self.error:raise self.error
        return self.answer

class Limits(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'ledger';self.now=1000000
        self.policy=OperationalPolicy('qualification',('a','b'))
        self.manager=self.new();self.manager.start()
    def tearDown(self):self.tmp.cleanup()
    def new(self,policy=None,clock=True):return ModelLimits(self.root,policy or self.policy,subscription_proof=PROOF,clock_ms=(lambda:self.now) if clock else None)
    def reserve(self,agent='a',rid='r',**kw):return self.manager.reserve(agent,rid,DIGEST,**kw)
    def complete(self,agent='a',rid='r',elapsed=1,**kw):self.manager.dispatch(agent,rid);self.manager.finish(agent,rid,elapsed_ms=elapsed,**kw)
    def test_ML01_exact_global_contention_atomic_threads(self):
        # Check the read/check fence itself, not only scheduler-dependent races.
        with self.manager.db() as db:self.assertTrue(db.in_transaction,'Admission reads require an already-held transaction')
        self.tmp.cleanup();self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'ledger';self.policy=dataclasses.replace(self.policy,total_requests=1);self.manager=self.new();self.manager.start()
        def call(i):
            try:return self.new().reserve('a' if i%2 else 'b','r'+str(i),DIGEST)['new']
            except LimitExceeded:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:answers=list(pool.map(call,range(40)))
        self.assertEqual(sum(answers),1);self.assertEqual(self.manager.snapshot()['requests'],1)
    def test_ML02_independent_agent_exhaustion(self):
        for i in range(30):self.reserve(rid='r'+str(i));self.complete(rid='r'+str(i))
        with self.assertRaisesRegex(LimitExceeded,'agent_request_budget'):self.reserve(rid='over')
        self.assertTrue(self.reserve('b','other')['new']);self.assertEqual(self.manager.snapshot()['agents']['a']['requests'],30)
    def test_ML03_global_exhaustion_no_provider_dispatch(self):
        self.tmp.cleanup();self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'ledger';self.policy=dataclasses.replace(self.policy,total_requests=1);self.manager=self.new();self.manager.start();self.reserve();self.complete()
        provider=Adapter();wrapped=LimitedDecider(self.manager,'b',provider)
        with self.assertRaises(LimitExceeded):wrapped.decide({'budget':999999,'model':'unauthorized'})
        self.assertEqual(provider.calls,0)
        with self.manager.db() as db:self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='REJECTED'").fetchone()[0],1)
    def test_ML04_concurrency_slots_include_uncertain(self):
        self.reserve();self.manager.dispatch('a','r');self.manager.finish('a','r',elapsed_ms=10,state='UNCERTAIN',reason='timeout')
        self.reserve('b','b1')
        with self.assertRaisesRegex(LimitExceeded,'model_concurrency_budget'):self.reserve('b','b2')
        self.complete('b','b1');self.assertTrue(self.reserve('b','b3')['new'])
    def test_ML05_timeout_no_refund_no_retry(self):
        provider=Adapter(error=TimeoutError('injected'));wrapped=LimitedDecider(self.manager,'a',provider)
        with self.assertRaises(TimeoutError):wrapped.decide({})
        snap=self.manager.snapshot()['agents']['a'];self.assertEqual(snap['inference_ms_charged'],90000);self.assertTrue(snap['halted'])
        with self.assertRaises(LimitExceeded):wrapped.decide({})
        self.assertEqual(provider.calls,1);self.assertTrue(self.reserve('b','peer')['new'])
    def test_ML06_missing_usage_is_optional_not_zero_requests(self):
        provider=Adapter({'source':'','finish':False});answer=LimitedDecider(self.manager,'a',provider).decide({})
        self.assertEqual(answer,provider.answer);self.assertEqual(self.manager.snapshot()['requests'],1);self.assertEqual(self.manager.snapshot()['agents']['a']['states'],{'COMPLETED':1})
    def test_ML07_partial_malformed_provider_response_halts(self):
        for answer in [[],{'oversized':'x'*17000},{'nonfinite':float('nan')}]:
            with tempfile.TemporaryDirectory() as root:
                manager=ModelLimits(Path(root)/'ledger',self.policy,subscription_proof=PROOF);manager.start();provider=Adapter(answer)
                with self.assertRaises(ValueError):LimitedDecider(manager,'a',provider).decide({})
                self.assertTrue(manager.snapshot()['agents']['a']['halted'])
    def test_ML08_duplicate_reservation_no_second_dispatch(self):
        self.assertTrue(self.reserve()['new']);self.assertFalse(self.reserve()['dispatch_allowed']);self.manager.dispatch('a','r')
        with self.assertRaises(RequestConflict):self.manager.dispatch('a','r')
        self.assertFalse(self.reserve()['dispatch_allowed']);self.assertEqual(self.manager.snapshot()['requests'],1)
    def test_ML09_duplicate_reconciliation_no_rewrite(self):
        self.reserve();self.complete(elapsed=3,usage={'input':11,'output':2})
        self.assertFalse(self.manager.finish('a','r',elapsed_ms=3,usage={'input':11,'output':2}))
        with self.assertRaises(RequestConflict):self.manager.finish('a','r',elapsed_ms=0,usage={'input':11,'output':2})
        self.assertEqual(self.manager.snapshot()['agents']['a']['inference_ms_charged'],3)
    def test_ML10_restart_keeps_deadline_configuration_consumption(self):
        deadline=self.manager.start();self.reserve();self.complete();self.now+=100
        reopened=self.new();self.assertEqual(reopened.start(),deadline);self.assertEqual(reopened.snapshot()['requests'],1)
        with self.assertRaises(RequestConflict):self.new(dataclasses.replace(self.policy,total_requests=59))
    def test_ML11_crash_reserved_dispatched_after_response_unknown(self):
        self.reserve();self.reserve('b','b');self.manager.dispatch('b','b')
        reopened=self.new();self.assertEqual(reopened.recover_interrupted(),2);self.assertEqual(reopened.recover_interrupted(),0)
        for agent in ('a','b'):
            self.assertTrue(reopened.snapshot()['agents'][agent]['halted'])
            self.assertEqual(reopened.snapshot()['agents'][agent]['states'],{'UNCERTAIN':1})
            with self.assertRaises(LimitExceeded):reopened.reserve(agent,'new'+agent,DIGEST)
        self.assertEqual(reopened.snapshot()['requests'],2)
    def test_ML12_cancel_before_dispatch_releases_slot_not_request_count(self):
        self.reserve();self.manager.finish('a','r',elapsed_ms=0,state='CANCELLED_BEFORE_DISPATCH')
        self.assertEqual(self.manager.snapshot()['requests'],1);self.assertTrue(self.reserve(rid='next')['new'])
        with self.assertRaises(RequestConflict):self.manager.dispatch('a','r')
    def test_ML13_cancel_after_dispatch_retains_charge(self):
        self.reserve();self.manager.dispatch('a','r')
        with self.assertRaises(RequestConflict):self.manager.finish('a','r',elapsed_ms=0,state='CANCELLED_BEFORE_DISPATCH')
        self.manager.finish('a','r',elapsed_ms=1,state='UNCERTAIN',reason='cancelled_after_dispatch')
        self.assertEqual(self.manager.snapshot()['agents']['a']['inference_ms_charged'],90000)
    def test_ML14_global_agent_inference_exact_boundary(self):
        self.tmp.cleanup();self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'ledger';self.policy=dataclasses.replace(self.policy,inference_ms_per_agent=6,total_inference_ms=10,request_timeout_ms=6);self.manager=self.new();self.manager.start()
        self.reserve();self.complete(elapsed=6)
        with self.assertRaisesRegex(LimitExceeded,'agent_inference_time_budget'):self.reserve(rid='over',timeout_ms=1)
        with self.assertRaisesRegex(LimitExceeded,'global_inference_time_budget'):self.reserve('b','b',timeout_ms=5)
        self.reserve('b','exact',timeout_ms=4);self.complete('b','exact',elapsed=4)
        self.assertEqual(sum(x['inference_ms_charged'] for x in self.manager.snapshot()['agents'].values()),10)
    def test_ML15_native_operation_limits_and_idempotency(self):
        for i in range(10):self.assertTrue(self.manager.admit_operations('a','frame'+str(i),'M0 1 0 0',30))
        self.assertFalse(self.manager.admit_operations('a','frame0','M0 1 0 0',30))
        with self.assertRaises(LimitExceeded):self.manager.admit_operations('a','extra','M0 1 0 0',1)
        self.assertTrue(self.manager.admit_operations('b','peer','M0 1 0 0',1));self.assertEqual(self.manager.snapshot()['operations'],301)
        with self.assertRaises(ValueError):self.manager.admit_operations('b','empty','',0)
    def test_ML16_foreign_agent_identity_conflicts(self):
        self.reserve();self.manager.dispatch('a','r')
        with self.assertRaises(RequestConflict):self.reserve('b','r')
        with self.assertRaises(RequestConflict):self.manager.finish('b','r',elapsed_ms=1)
        with self.assertRaises(RequestConflict):self.manager.reserve('a','r','f'*64)
        for bad in ['foreign','../a','',None]:
            with self.assertRaises(ValueError):self.manager.reserve(bad,'rid',DIGEST)
    def test_ML17_runtime_stop_and_clock_rollback(self):
        self.now-=1
        with self.assertRaisesRegex(LimitExceeded,'clock_regressed'):self.reserve()
        self.now+=1;self.now+=self.policy.duration_ms
        with self.assertRaisesRegex(LimitExceeded,'deadline'):self.reserve()
        self.manager.stop('operator');self.now=1000000
        with self.assertRaises(LimitExceeded):self.manager.start()
        with self.assertRaises(LimitExceeded):self.manager.check('a')
    def test_ML18_invalid_limits_overflow_and_bools(self):
        for field,value in [('total_requests',-1),('total_requests',0),('duration_ms',2**63),('requests_per_agent',True),('concurrent_requests',3),('model','fallback'),('agents',('a','a'))]:
            with self.assertRaises(ValueError):dataclasses.replace(self.policy,**{field:value})
    def test_ML19_metered_unknown_route_rejected(self):
        for changed in [{'oauth':False},{'subscription':False},{'base_url':'https://api.openai.com/v1'},{'model':'gpt-6.1-sol'}]:
            with self.assertRaises(ValueError):ModelLimits(Path(self.tmp.name)/'bad',self.policy,subscription_proof={**PROOF,**changed})
    def test_ML20_persistence_process_concurrency(self):
        # Real independent processes, production wall clock, no network/backend.
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ledger';policy=dataclasses.replace(self.policy,total_requests=1);manager=ModelLimits(path,policy,subscription_proof=PROOF);manager.start()
            with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:answers=list(pool.map(process_reserve,[(path,policy,'p'+str(i)) for i in range(16)]))
            self.assertEqual(sum(answers),1);self.assertEqual(manager.snapshot()['requests'],1)
    def test_ML21_request_timeout_bound_no_new_native_work(self):
        self.reserve(timeout_ms=1);self.manager.dispatch('a','r');self.manager.finish('a','r',elapsed_ms=2)
        self.assertTrue(self.manager.snapshot()['agents']['a']['halted'])
        with self.assertRaises(LimitExceeded):self.manager.admit_operations('a','frame','S2 ?',1)
    def test_ML22_pre_dispatch_validation_and_adapter_timeout(self):
        provider=Adapter();wrapped=LimitedDecider(self.manager,'a',provider)
        with self.assertRaises(ValueError):wrapped.decide({'oversized':'x'*140000})
        self.assertEqual(provider.calls,0);self.assertEqual(self.manager.snapshot()['requests'],0)
        provider.timeout=181
        with self.assertRaises(ValueError):LimitedDecider(self.manager,'a',provider)
    def test_ML23_private_files_and_symlink_refusal(self):
        self.assertEqual(self.manager.path.stat().st_mode&0o077,0)
        link=Path(self.tmp.name)/'link';link.symlink_to(self.root)
        with self.assertRaises(ValueError):ModelLimits(link,self.policy,subscription_proof=PROOF)
    def test_ML25_stop_survives_full_audit(self):
        with self.manager.db() as db:db.executemany('INSERT INTO events(kind) VALUES(?)',[('fixture',)]*2000)
        with self.assertRaisesRegex(LimitExceeded,'event_capacity'):self.reserve()
        self.manager.stop('emergency');self.assertEqual(self.manager.snapshot()['state'],'STOPPED')
        with self.assertRaises(LimitExceeded):self.manager.check('a')
    def test_ML24_known_provider_failure_is_local_halt(self):
        self.reserve();self.manager.dispatch('a','r');self.manager.finish('a','r',elapsed_ms=1,state='PROVIDER_ERROR',reason='429_usage_limit')
        with self.assertRaises(LimitExceeded):self.reserve(rid='retry')
        self.assertTrue(self.reserve('b','peer')['new'])

if __name__=='__main__':unittest.main()
