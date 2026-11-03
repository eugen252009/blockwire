"""Transactional settings, snapshots, dedup and serial scheduling; no Minecraft claims."""
import tempfile,time,unittest
from pathlib import Path
from dataclasses import replace
from blockwire.bcl import default_commands,BCLError,Command
from blockwire.bcl.registry import Setting
from blockwire.bcl.modal import CoordinateContext,ModalSession,Modal
from blockwire.bcl.runtime import BCLJobs,BCLRunner,BatchDriver
from blockwire import Player,CallableBackend
from blockwire.skills import default_registry,SkillDefinition,SkillParameters,SkillResult
from blockwire.skills.walking import WalkTo
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
        self.assertEqual([o.opcode for o in prepared.program.operations],['S1','S1','M0'])
        self.assertEqual(prepared.contexts,(Modal('async','relative','normal','stop',30.),
            Modal('async','relative','fast','stop',30.),Modal('async','relative','sneak','stop',30.)))
        self.assertEqual([c.status for c in prepared.coordinates],['pending','pending','pending'])
        self.assertEqual([c.home_id for c in prepared.coordinates],[1,2,2])
        self.assertEqual(s.subscriptions,{'player.position'})
        s.prepare('S2 fast\nS1 absolute',2)
        self.assertEqual(prepared.contexts[-1].movement_mode,'sneak')
        self.assertEqual(prepared.contexts[-1].coordinate_mode,'relative')
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

    def test_BS06_relative_home_is_stable_then_explicit_assignment_rehomes_from_actual_position(self):
        from types import SimpleNamespace
        s=self.session();p,_=s.prepare('S1 relative\nS2 fast\nM0 10 0 0 sneak\nM0 0 0 10\nS1 relative\nM0 5 0 0',1)
        d=BatchDriver(p.program,self.r,p.contexts,p.coordinates,
            capture_home=lambda home_id,position,dimension:s.capture_home(1,home_id,position,dimension),
            resolve_home=s.resolve_home)
        d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        c={'observation':{'position':[100.,64.,200.],'dimension':'minecraft:overworld'},'completed_actions':{},'history':[]}
        self.assertEqual(d.decide(c)['kind'],'wait')
        first=d.decide(c)['parameters'];self.assertEqual((first['x'],first['y'],first['z'],first['movement']),(110.,64.,200.,'sneak'))
        c.update(observation={'position':[109.5,64.,199.5],'dimension':'minecraft:overworld'},completed_actions={'walk_to':1},history=[{'status':'succeeded','reason':'arrived'}])
        second=d.decide(c)['parameters'];self.assertEqual((second['x'],second['y'],second['z'],second['movement']),(100.,64.,210.,'run'))
        c.update(observation={'position':[100.,64.,210.],'dimension':'minecraft:overworld'},completed_actions={'walk_to':2},history=[{'status':'succeeded','reason':'arrived'}])
        self.assertEqual(d.decide(c)['kind'],'wait')
        third=d.decide(c)['parameters'];self.assertEqual((third['x'],third['y'],third['z'],third['movement']),(105.,64.,210.,'run'))
        self.assertEqual(s.coordinate_context.home,(100.,64.,210.))
        self.assertEqual(s.modal.movement_mode,'fast')

    def test_BS18_consecutive_explicit_relative_assignments_each_capture_a_fresh_observation(self):
        from types import SimpleNamespace
        s=self.session();prepared,_=s.prepare('S1 relative\nS1 relative',1)
        d=BatchDriver(prepared.program,self.r,prepared.contexts,prepared.coordinates,
            capture_home=lambda home_id,position,dimension:s.capture_home(1,home_id,position,dimension),resolve_home=s.resolve_home)
        d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        context={'observation':{'position':[1.,64.,2.],'dimension':'minecraft:overworld'},'completed_actions':{},'history':[]}
        self.assertEqual(d.decide(context)['kind'],'wait')
        context['observation']={'position':[3.,65.,4.],'dimension':'minecraft:overworld'}
        self.assertEqual(d.decide(context)['kind'],'wait')
        self.assertEqual([r['reason'] for r in d.results],['relative_home_captured','relative_home_captured'])
        self.assertEqual(s.coordinate_context.home,(3.,65.,4.))
        self.assertNotEqual(prepared.coordinates[0].home_id,prepared.coordinates[1].home_id)

    def test_BS19_failed_second_consecutive_home_restores_the_first_captured_home(self):
        from types import SimpleNamespace
        s=self.session();prepared,_=s.prepare('S1 relative\nS1 relative',1)
        d=BatchDriver(prepared.program,self.r,prepared.contexts,prepared.coordinates,
            capture_home=lambda home_id,position,dimension:s.capture_home(1,home_id,position,dimension),resolve_home=s.resolve_home)
        d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        context={'observation':{'position':[8.,64.,9.],'dimension':'minecraft:overworld'},'completed_actions':{},'history':[]}
        self.assertEqual(d.decide(context)['kind'],'wait')
        first=s.resolve_home(prepared.coordinates[0].home_id)
        self.assertEqual(first.home,(8.,64.,9.))
        self.assertTrue(s.fail_homes(1,'failed'))
        self.assertEqual(s.coordinate_context,first)

    def test_BS11_queries_dedup_reconnect_and_invalid_rehome_preserve_the_last_valid_home(self):
        from types import SimpleNamespace
        s=self.session();p,r=s.prepare('S1 relative',1)
        self.assertEqual(r['status'],'accepted');self.assertEqual(r['coordinate_context']['status'],'pending')
        first=s.capture_home(1,p.coordinates[0].home_id,[12.75,64.,-3.25],'minecraft:overworld')
        s.update(1,status='completed')
        _,query=s.prepare('S1 ?',2);_,status=s.prepare('S1 status',3)
        self.assertEqual(query['outputs'][0]['coordinate_context'],status['outputs'][0]['coordinate_context'])
        self.assertEqual(s.coordinate_context,first)
        _,duplicate=s.prepare('S1 relative',1)
        self.assertTrue(duplicate['deduplicated']);self.assertEqual(duplicate['coordinate_context']['home_id'],first.home_id)
        second,_=s.prepare('S1 relative',4)
        d=BatchDriver(second.program,self.r,second.contexts,second.coordinates,
            capture_home=lambda home_id,position,dimension:s.capture_home(4,home_id,position,dimension),resolve_home=s.resolve_home)
        d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        with self.assertRaises(BCLError) as error:d.decide({'observation':{'position':None,'dimension':'minecraft:overworld'},'completed_actions':{},'history':[]})
        self.assertEqual(error.exception.diagnostic.code,'INVALID_COORDINATE_HOME')
        s.fail_homes(4,'failed')
        self.assertEqual(s.coordinate_context.home,first.home)
        s.close();restored=self.session()
        self.assertEqual(restored.coordinate_context.home,first.home)
        self.assertEqual(restored.coordinate_context.voxel_origin,(12,64,-4))

    def test_BS17_pre_homing_modal_journals_fail_closed_instead_of_changing_meaning(self):
        for name,removed in [('legacy.sqlite',('modal_semantics',)),('legacy-minimal.sqlite',('modal_semantics','modal_version','modal_layout'))]:
            with self.subTest(name=name):
                s=self.session(name)
                for key in removed:s.state.pop(key)
                s.store.save(s.state);s.close()
                with self.assertRaisesRegex(ValueError,'S1 coordinate semantics'):
                    ModalSession(self.r,Path(self.tmp.name)/name,self.identity,'actor-a')

    def test_BS20_corrupt_persisted_home_chains_and_active_contexts_fail_closed(self):
        mutations={
            'bad-chain':lambda state,record:record.update(previous_mode='relative',previous_home_id=None),
            'bad-next':lambda state,record:state['coordinate'].update(next_home_id=record['home_id']),
            'absolute-active':lambda state,record:state['modal'].update(coordinate_mode='absolute'),
            'terminal-active':lambda state,record:record.update(status='failed'),
            'pending-with-home':lambda state,record:record.update(status='pending'),
        }
        for name,mutate in mutations.items():
            with self.subTest(name=name):
                s=self.session(name+'.sqlite');prepared,_=s.prepare('S1 relative',1)
                s.capture_home(1,prepared.coordinates[0].home_id,[1.,64.,2.],'minecraft:overworld')
                record=s.state['coordinate']['homes'][str(prepared.coordinates[0].home_id)]
                mutate(s.state,record);s.store.save(s.state);s.close()
                with self.assertRaisesRegex(ValueError,'persisted|Relative mode|Absolute mode'):
                    ModalSession(self.r,Path(self.tmp.name)/(name+'.sqlite'),self.identity,'actor-a')

    def test_BS15_failed_home_commit_never_publishes_a_new_coordinate_origin(self):
        s=self.session();prepared,_=s.prepare('S1 relative',1);save=s.store.save
        def fail(_):raise OSError('fixture disk failure')
        s.store.save=fail
        try:
            with self.assertRaises(OSError):s.capture_home(1,prepared.coordinates[0].home_id,[4.,65.,6.],'minecraft:overworld')
            self.assertEqual(s.coordinate_context.status,'pending')
            self.assertIsNone(s.coordinate_context.home)
        finally:s.store.save=save

    def test_BS12_relative_transform_covers_point_and_voxel_parameters_but_not_omitted_axes(self):
        from types import SimpleNamespace
        s=self.session();home,_=s.prepare('S1 relative',1)
        s.capture_home(1,home.coordinates[0].home_id,[10.75,64.,-2.25],'minecraft:overworld');s.update(1,status='completed')
        cases=[
            ('M0 X1 Y2',{'x':11.75,'y':66.,'z':80.}),
            ('M1 P[1,2,3]',{'position':[11,66,0]}),
            ('M3 T=[[0.1,1,0.2,40,0,3],[0,1,0.3,35,0,8]]',
             {'samples':[[10.85,65.,-2.05,40,0,3],[10.75,65.,-1.95,35,0,8]]}),
            ('M4 E="[[0,0.1,1,0.2,40,0,3],[1,\\"minecraft:cobblestone\\",1,2,3,0,0.25,1,0.25,0.5,1,0.5],[0,0,1,0.3,35,0,8]]"',
             {'events':[[0,10.85,65.,-2.05,40,0,3],
                        [1,'minecraft:cobblestone',11,66,0,0,11.,65.,-2.,11.25,65.,-1.75],
                        [0,10.75,65.,-1.95,35,0,8]]}),
            ('M5 Q[0.1,3,0.2] L[-0.2,0,-0.1] H45 P10 Bforward',
             {'edge':[10.85,67.,-2.05],'landing':[10.55,64.,-2.35]}),
            ('C2 Bminecraft:stone P[1,2,3]',{'position':[11,66,0]}),
            ('C3 P[1,2,3]',{'position':[11,66,0]}),
            ('I3 P[1,2,3] Q[0.25,1.5,-0.5] R[0.5,1,0.5]',{'support':[11,66,0],'recorded_pose':[11.,65.5,-2.75],'recorded_aim':[11.25,65.,-1.75]}),
            ('I4 P[1,2,3]',{'position':[11,66,0]}),
            ('V1 P[1,2,3]',{'position':[11,66,0]}),
            ('V2 1 2 3',{'x':11.75,'y':66.,'z':.75}),
        ]
        for request_id,(source,expected) in enumerate(cases,2):
            with self.subTest(source=source):
                p,_=s.prepare(source,request_id);d=BatchDriver(p.program,self.r,p.contexts,p.coordinates,resolve_home=s.resolve_home)
                d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
                decision=d.decide({'observation':{'position':[50.,70.,80.],'dimension':'minecraft:overworld'},'completed_actions':{},'history':[]})
                for key,value in expected.items():self.assertEqual(decision['parameters'][key],value)
        p,_=s.prepare('V2 1 2 3',20);d=BatchDriver(p.program,self.r,p.contexts,p.coordinates,resolve_home=s.resolve_home)
        d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        with self.assertRaises(BCLError) as error:d.decide({'observation':{'position':[0.,64.,0.],'dimension':'minecraft:the_nether'},'completed_actions':{},'history':[]})
        self.assertEqual(error.exception.diagnostic.code,'COORDINATE_CONTEXT_MISMATCH')
        s.prepare('S1 absolute',21);p,_=s.prepare('V2 1 2 3',22)
        d=BatchDriver(p.program,self.r,p.contexts,p.coordinates);d.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda _:None),_publish=lambda **_:None)
        absolute=d.decide({'observation':{'position':[50.,70.,80.],'dimension':'minecraft:overworld'},'completed_actions':{},'history':[]})
        self.assertEqual((absolute['parameters']['x'],absolute['parameters']['y'],absolute['parameters']['z']),(1.,2.,3.))

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
            result=BCLRunner(p.source,r,Player(CallableBackend(native.call)),Path(folder)/'a.sqlite',s.store.identity,'actor-a',
                contexts=p.contexts,coordinates=p.coordinates,program=p.program).run()
            self.assertEqual([x['status'] for x in result['operations']],['blocked','succeeded'],result)
            self.assertFalse(result['objective_verified']);self.assertEqual(result['reason'],'completed_with_errors')
    def test_BS08_settings_queries_and_queued_homing_stay_responsive_while_action_is_running(self):
        with tempfile.TemporaryDirectory() as folder:
            native=Native();r=default_commands()
            def waiting(c,g):c.pause(.4);return SkillResult(status='succeeded',reason='wait_observed',text='fixture')
            r.skills.register(SkillDefinition('waiting','fixture',SkillParameters,waiting));r.namespace('test')
            r.register(Command('test','I0','fixture.wait','fixture',(),'waiting',frozenset({'inventory'})))
            jobs=BCLJobs(r,Player(CallableBackend(native.call)),folder);self.addCleanup(jobs.close)
            identity={'agent_id':'a','world_id':'w','player_id':'player-a'}
            first=jobs.submit('s','S0 async\ntest:I0',1,identity,'actor-a')
            start=time.monotonic();settings=jobs.submit('s','S2 fast\nS0 ?',2,identity,'actor-a')
            self.assertLess(time.monotonic()-start,.2);self.assertEqual(settings['status'],'completed')
            start=time.monotonic();home=jobs.submit('s','S1 relative',3,identity,'actor-a')
            self.assertLess(time.monotonic()-start,.2);self.assertEqual(home['status'],'accepted')
            query=jobs.submit('s','S1 status',4,identity,'actor-a')
            self.assertEqual(query['outputs'][0]['coordinate_context']['status'],'pending')
            j=jobs.jobs[first['id']];self.assertEqual(j['prepared'].contexts[0],Modal(execution_mode='async'))
            for identifier in (first['id'],home['id']):
                for _ in range(200):
                    if jobs.status(identifier)['status'] in {'succeeded','failed','cancelled','blocked'}:break
                    time.sleep(.01)
                self.assertEqual(jobs.status(identifier)['status'],'succeeded')
            self.assertEqual(jobs.sessions['s'].coordinate_context.home,(.5,64.,.5))

    def test_BS13_async_batches_keep_one_home_across_requests_and_rehome_in_fifo_order(self):
        class MovingNative(Native):
            def __init__(self):super().__init__();self.position=[100.,64.,200.]
            def call(self,q):
                if q['op']=='observe':
                    self.calls.append(dict(q));x,y,z=self.position
                    return {'actor_session':self.actor,'player_uuid':self.uuid,'in_world':True,'alive':True,
                        'health':self.health,'hunger':20,'dimension':'minecraft:overworld','position':self.position[:],
                        'eye_position':[x,y+1.62,z],'visible_interactables':[]}
                return super().call(q)
        with tempfile.TemporaryDirectory() as folder:
            native=MovingNative();targets=[];skills=default_registry()
            def move(c,g):
                c.check();targets.append((g.x,g.y,g.z));native.position=[g.x,g.y,g.z]
                return SkillResult(status='succeeded',reason='arrived',text='fixture',details={'position':native.position[:]})
            skills._definitions['walk_to']=SkillDefinition('walk_to','fixture movement',WalkTo,move,False)
            r=default_commands(skills);jobs=BCLJobs(r,Player(CallableBackend(native.call)),folder);self.addCleanup(jobs.close)
            identity={'agent_id':'a','world_id':'w','player_id':'player-a'}
            def wait(identifier):
                for _ in range(400):
                    result=jobs.status(identifier)
                    if result['status'] in {'succeeded','failed','cancelled','blocked'}:return result
                    time.sleep(.01)
                self.fail('BCL job did not finish')
            first=jobs.submit('s','S0 async\nS1 relative\nM0 10 0 0',1,identity,'actor-a')
            across_frame=jobs.submit('s','M0 20 0 0',2,identity,'actor-a')
            self.assertEqual(wait(first['id'])['status'],'succeeded')
            self.assertEqual(wait(across_frame['id'])['status'],'succeeded')
            self.assertEqual(targets,[(110.,64.,200.),(120.,64.,200.)])
            second=jobs.submit('s','S1 relative\nM0 5 0 0',3,identity,'actor-a')
            self.assertEqual(wait(second['id'])['status'],'succeeded')
            self.assertEqual(targets[-1],(125.,64.,200.))
            third=jobs.submit('s','M0 0 0 5',4,identity,'actor-a')
            self.assertEqual(wait(third['id'])['status'],'succeeded')
            self.assertEqual(targets[-1],(120.,64.,205.))
            absolute_then_home=jobs.submit('s','S1 absolute\nM0 200 64 200\nS1 relative\nM0 5 0 0',5,identity,'actor-a')
            self.assertEqual(wait(absolute_then_home['id'])['status'],'succeeded')
            self.assertEqual(targets[-2:],[(200.,64.,200.),(205.,64.,200.)])
            context=jobs.sessions['s'].coordinate_context
            self.assertEqual(context.home,(200.,64.,200.));self.assertEqual(context.status,'ready')

    def test_BS16_actor_mismatch_rejects_homing_and_restores_absolute_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            native=Native();native.actor='actor-b';jobs=BCLJobs(default_commands(),Player(CallableBackend(native.call)),folder);self.addCleanup(jobs.close)
            identity={'agent_id':'a','world_id':'w','player_id':'player-a'}
            home=jobs.submit('s','S1 relative',1,identity,'actor-a')
            for _ in range(200):
                result=jobs.status(home['id'])
                if result['status'] in {'succeeded','failed','cancelled','blocked'}:break
                time.sleep(.01)
            self.assertEqual(result['diagnostics'][0]['code'],'ACTOR_MISMATCH')
            self.assertEqual(jobs.sessions['s'].coordinate_context,CoordinateContext())

    def test_BS14_cancelled_queued_homing_rolls_back_to_the_previous_coordinate_context(self):
        with tempfile.TemporaryDirectory() as folder:
            native=Native();r=default_commands()
            def waiting(c,g):c.pause(.35);return SkillResult(status='succeeded',reason='wait_observed',text='fixture')
            r.skills.register(SkillDefinition('waiting','fixture',SkillParameters,waiting));r.namespace('test')
            r.register(Command('test','I0','fixture.wait','fixture',(),'waiting',frozenset({'inventory'})))
            jobs=BCLJobs(r,Player(CallableBackend(native.call)),folder);self.addCleanup(jobs.close)
            identity={'agent_id':'a','world_id':'w','player_id':'player-a'}
            active=jobs.submit('s','S0 async\ntest:I0',1,identity,'actor-a')
            home=jobs.submit('s','S1 relative',2,identity,'actor-a');jobs.cancel(home['id'])
            for identifier in (active['id'],home['id']):
                for _ in range(200):
                    if jobs.status(identifier)['status'] in {'succeeded','failed','cancelled','blocked'}:break
                    time.sleep(.01)
            self.assertEqual(jobs.status(home['id'])['status'],'cancelled')
            self.assertEqual(jobs.sessions['s'].modal.coordinate_mode,'absolute')
            self.assertEqual(jobs.sessions['s'].coordinate_context,CoordinateContext())

if __name__=='__main__':unittest.main()
