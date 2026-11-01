"""Transactional settings, snapshots, dedup and serial scheduling; no Minecraft claims."""
import tempfile,time,unittest
from pathlib import Path
from dataclasses import replace
from blockwire.bcl import default_commands,BCLError,Command
from blockwire.bcl.registry import Setting
from blockwire.bcl.modal import ModalSession,Modal
from blockwire.bcl.runtime import BCLJobs,BCLRunner,BatchDriver
from blockwire import Player,CallableBackend
from blockwire.skills import default_registry,SkillDefinition,SkillParameters,SkillResult
from test_agent import Native,registry as fixture_skills

class ModalContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=default_commands()
        self.identity={'agent_id':'a','world_id':'w','player_id':'player-a'}
    def session(self,file='modal.sqlite',permissions=None):
        kwargs={} if permissions is None else {'permissions':permissions}
        s=ModalSession(self.r,Path(self.tmp.name)/file,self.identity,'actor-a',**kwargs)
        self.addCleanup(s.close);return s
    def test_BS01_generic_binary_three_and_four_value_cycles_wrap(self):
        self.r.namespace('fixture');self.r.register_setting(Setting('fixture','S9','quad',('a','b','c','d'),'a'))
        s=self.session();n=0
        for opcode,expected in [('S0',['async','sync']),('S2',['fast','sneak','normal']),('fixture:S9',['b','c','d','a'])]:
            for value in expected:
                n+=1;_,r=s.prepare(opcode,n);self.assertEqual(r['outputs'][0]['value'],value)
    def test_BS02_set_get_idempotence_and_failed_transition_never_mutates(self):
        s=self.session()
        for n in (1,2):s.prepare('S0 async',n)
        self.assertEqual(s.modal.execution_mode,'async')
        _,a=s.prepare('S0 ?',3);_,b=s.prepare('S0 status',4)
        self.assertEqual(a['outputs'],b['outputs'])
        old=s.state.copy()
        for source in ['S2 normal\nS0 nonsense','S4 0','S4 121','S4','S6 creative','E100 player.health 18']:
            with self.subTest(source=source),self.assertRaises(BCLError):s.prepare(source,5)
            self.assertEqual(s.state,old)
        denied=self.session('denied.sqlite',{'observe'})
        with self.assertRaises(BCLError):denied.prepare('S0',1)
        self.assertEqual(denied.modal.execution_mode,'sync')
    def test_BS03_addendum_sequence_has_immutable_per_action_snapshots(self):
        s=self.session()
        source='''S0 sync
S1 absolute
S2 normal
S0 ?
S1 ?
S2 ?
S0
S1
S2
S0 ?
S1 ?
S2 ?
S0 async
S1 relative
S2 sneak
M0 10 0 0
E0 player.position'''
        prepared,r=s.prepare(source,1)
        self.assertEqual([x['value'] for x in r['outputs'] if x.get('operation')=='get'],['sync','absolute','normal','async','relative','fast'])
        self.assertEqual(prepared.contexts,(Modal('async','relative','sneak','stop',30.),))
        self.assertEqual(s.subscriptions,{'player.position'})
        s.prepare('S2 fast\nS1 absolute',2)
        self.assertEqual(prepared.contexts[0].movement_mode,'sneak')
        self.assertEqual(prepared.contexts[0].coordinate_mode,'relative')
    def test_BS04_durable_dedup_and_evicted_ids_cannot_repeat_cycles(self):
        s=self.session();_,first=s.prepare('S0',1)
        _,again=s.prepare('S0',1)
        self.assertTrue(again['deduplicated']);self.assertEqual(s.modal.execution_mode,'async')
        with self.assertRaises(BCLError):s.prepare('S2',1)
        for i in range(2,131):s.prepare('S0 ?',i)
        with self.assertRaises(BCLError) as e:s.prepare('S0',1)
        self.assertEqual(e.exception.diagnostic.code,'STALE_REQUEST')
        s.close();other=self.session()
        self.assertEqual(other.modal.execution_mode,'async')
        _,duplicate=other.prepare('S0 ?',130);self.assertTrue(duplicate['deduplicated'])
    def test_BS05_sessions_and_subscriptions_are_isolated_and_pending_work_not_replayed(self):
        a=self.session('a.sqlite');b=self.session('b.sqlite')
        a.prepare('S2 fast\nE0 player.health\nM0 0 0 0',1)
        self.assertEqual(b.modal.movement_mode,'normal');self.assertFalse(b.subscriptions)
        a.close();a=self.session('a.sqlite');_,r=a.prepare('S2 fast\nE0 player.health\nM0 0 0 0',1)
        self.assertEqual(r['status'],'interrupted');self.assertTrue(r['deduplicated'])
        a.prepare('E1 player.health',2);self.assertFalse(a.subscriptions)
        a.prepare('E0 player.position\nE0 inventory.changed\nE2\nE3',3);self.assertFalse(a.subscriptions)
        a.prepare('',4,reset=True);self.assertEqual(a.modal,Modal())
    def test_BS10_completion_mode_belongs_to_enqueued_action_not_later_setting(self):
        s=self.session();p,r=s.prepare('S0 async\nM0 1 64 1\nS0 sync',1)
        self.assertEqual(r['execution_mode'],'async');self.assertEqual(r['modal']['execution_mode'],'sync')
        self.assertEqual(p.contexts[0].execution_mode,'async')

    def test_BS09_failed_durable_commit_never_publishes_modal_transition(self):
        s=self.session();save=s.store.save
        def fail(_):raise OSError('fixture disk failure')
        s.store.save=fail
        try:
            with self.assertRaises(OSError):s.prepare('S0',1)
            self.assertEqual(s.modal.execution_mode,'sync')
            self.assertEqual(s.state['last_request_id'],0)
        finally:s.store.save=save

    def test_BS06_relative_anchor_is_fresh_at_execution_and_explicit_mode_is_one_shot(self):
        from types import SimpleNamespace
        s=self.session();p,_=s.prepare('S1 relative\nS2 fast\nM0 10 0 0 sneak\nM0 0 0 10',1)
        d=BatchDriver(p.program,self.r,p.contexts)
        d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        c={'observation':{'position':[100.,64.,200.]},'completed_actions':{},'history':[]}
        first=d.decide(c)['parameters'];self.assertEqual((first['x'],first['y'],first['z'],first['movement']),(110.,64.,200.,'sneak'))
        c.update(observation={'position':[110.,64.,200.]},completed_actions={'walk_to':1},history=[{'status':'succeeded','reason':'arrived'}])
        second=d.decide(c)['parameters'];self.assertEqual((second['x'],second['z'],second['movement']),(110.,210.,'run'))
        self.assertEqual(s.modal.movement_mode,'fast')

class ModalExecutionContracts(unittest.TestCase):
    def test_BS07_continue_policy_does_not_turn_failed_operation_into_success(self):
        with tempfile.TemporaryDirectory() as folder:
            native=Native();skills=default_registry()
            for d in fixture_skills()._definitions.values():skills.register(d)
            r=default_commands(skills);r.namespace('test')
            for op,name in [('I0','missing'),('I1','effect')]:r.register(Command('test',op,'fixture.'+name,'fixture',(),name,frozenset({'inventory'})))
            s=ModalSession(r,Path(folder)/'m.sqlite',{'agent_id':'a','world_id':'w','player_id':'player-a'},'actor-a')
            self.addCleanup(s.close)
            p,_=s.prepare('S3 continue\ntest:I0\ntest:I1',1)
            result=BCLRunner(p.source,r,Player(CallableBackend(native.call)),Path(folder)/'a.sqlite',s.store.identity,'actor-a',contexts=p.contexts).run()
            self.assertEqual([x['status'] for x in result['operations']],['blocked','succeeded'],result)
            self.assertFalse(result['objective_verified']);self.assertEqual(result['reason'],'completed_with_errors')
    def test_BS08_settings_and_queries_stay_responsive_while_action_is_running(self):
        with tempfile.TemporaryDirectory() as folder:
            native=Native();r=default_commands()
            def waiting(c,g):c.pause(.4);return SkillResult(status='succeeded',reason='wait_observed',text='fixture')
            r.skills.register(SkillDefinition('waiting','fixture',SkillParameters,waiting));r.namespace('test')
            r.register(Command('test','I0','fixture.wait','fixture',(),'waiting',frozenset({'inventory'})))
            jobs=BCLJobs(r,Player(CallableBackend(native.call)),folder);self.addCleanup(jobs.close)
            identity={'agent_id':'a','world_id':'w','player_id':'player-a'}
            first=jobs.submit('s','S0 async\ntest:I0',1,identity,'actor-a')
            start=time.monotonic();response=jobs.submit('s','S1 relative\nS2 fast\nS0 ?',2,identity,'actor-a')
            self.assertLess(time.monotonic()-start,.2);self.assertEqual(response['status'],'completed')
            j=jobs.jobs[first['id']];self.assertEqual(j['prepared'].contexts[0],Modal(execution_mode='async'))
            for _ in range(200):
                if jobs.status(first['id'])['status']=='succeeded':break
                time.sleep(.01)
            self.assertEqual(jobs.status(first['id'])['status'],'succeeded')

if __name__=='__main__':unittest.main()
