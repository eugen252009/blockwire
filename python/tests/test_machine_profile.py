"""Machine separation contracts. Simulated backend, real authenticated TLS; NOT gameplay."""
import asyncio,json,subprocess,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from blockwire import Player,CallableBackend
from blockwire.bcl import compile_bcl,BCLError
from blockwire.bcl.machine import machine_commands,encode_action
from blockwire.bcl.gateway import BCLGateway,server_tls
from blockwire.bcl.client import BCLClient
from blockwire.machine_actions import KEYS,action_registry,released
from blockwire.machine_mcp import EventInbox,create_machine_server
from test_agent import Native


class MachineNative(Native):
    def __init__(self):
        super().__init__();self.tick=0;self.held=[];self.yaw=0.;self.pitch=0.;self.selected=0;self.opened=False
        self.freeze_tick=False;self.deny_release=False
    def call(self,q):
        op=q['op']
        if op=='menu':return super().call(q)
        if op=='observe':return {**super().call(q),'yaw':self.yaw,'pitch':self.pitch}
        if op=='inventory':return {**super().call(q),'selected_hotbar':self.selected,'container_open':self.opened,'menu_id':1,'state_id':1,'slots':[],**getattr(self,'inventory_extra',{})}
        if op=='stop':
            if not self.deny_release:self.held=[]
            return super().call(q)
        self.calls.append(dict(q))
        if op=='search' and hasattr(self,'search_handler'):return self.search_handler(q)
        if op=='navigation':return {'actor_session':self.actor,'ready':True,'profile':'stepped_full_blocks_v1','cells':[],'edges':[]}
        if op=='motion_trace':
            if not self.freeze_tick:self.tick+=1
            return {'profile':'native_player_motion_ticks_v1','actor_session':self.actor,'samples':[{'actor_session':self.actor,'client_tick':self.tick,'remote_owned_inputs':self.held[:],'inputs':{k:k in self.held for k in KEYS}}]}
        if op=='drive':self.held=q['buttons'];return {'submitted':True}
        if op=='look':self.yaw=q['yaw'];self.pitch=q['pitch'];return {'submitted':True}
        if op=='hotbar':self.selected=q['slot'];return {'submitted':True}
        if op=='open_inventory':self.opened=True;return {'submitted':True}
        if op=='close_screen':self.opened=False;return {'submitted':True}
        if op in {'action','click_slot'}:return {'submitted':True}
        raise AssertionError(op)


class MachineSyntax(unittest.TestCase):
    def test_action_only_no_queries_or_planners_or_settings(self):
        registry=machine_commands()
        for source in ['V0','I0','C1 N1','C0 I"minecraft:stick"','E0 player.health','S0 async','S1 relative']:
            with self.subTest(source=source),self.assertRaises(BCLError):compile_bcl(source,registry)
        program=compile_bcl(encode_action(registry,'pulse',{'buttons':['forward'],'seconds':.1})+'\nG2 Y=90 P=0\nM1 A="use"',registry)
        self.assertEqual(len(program.operations),3)
        self.assertEqual(set(registry.skills._definitions),{'pulse','turn','press','hold','select_slot','inventory_screen','click_slot','input_sequence','slot_program'})
        with self.assertRaises(BCLError):compile_bcl('M1 A="attack"',registry,permissions={'inventory'})
        with self.assertRaises(BCLError):compile_bcl('M5 M1 I1 S1',registry,permissions={'inventory'})

    def test_json_action_validated_before_encoding_no_injection(self):
        registry=machine_commands()
        for name,args in [('gather_wood',{}),('pulse',{'buttons':['forward','back']}),('pulse',{'buttons':['forward'],'seconds':99}),
                          ('press',{'action':'use\nV0'}),('select_slot',{'slot':True}),('click_slot',{'menu_id':1,'state_id':1,'slot':-999})]:
            with self.subTest(name=name,args=args),self.assertRaises(ValueError):encode_action(registry,name,args)
        source=encode_action(registry,'press',{'action':'use'})
        self.assertEqual(len(compile_bcl(source,registry).operations),1)

    def test_long_hold_has_continuity_budget_without_long_native_leases(self):
        from types import SimpleNamespace
        from blockwire.bcl.runtime import BatchDriver
        from blockwire.bcl.modal import Modal
        registry=machine_commands()
        program=compile_bcl(encode_action(registry,'hold',{'action':'attack','seconds':30.}),registry)
        driver=BatchDriver(program,registry,(Modal(timeout_seconds=35.),))
        driver.runtime=SimpleNamespace(state={},store=SimpleNamespace(save=lambda state:None),_publish=lambda **kw:None)
        decision=driver.decide({'completed_actions':{},'observation':{}})
        self.assertEqual(decision['parameters']['seconds'],30.)
        self.assertEqual(decision['parameters']['timeout_seconds'],35.)
        with self.assertRaises(ValueError):action_registry().prepare('hold',{'action':'use','seconds':30.01})

    def test_every_primitive_roundtrips_through_the_real_bcl_compiler(self):
        from blockwire.bcl.compiler import arguments
        registry=machine_commands()
        examples={'pulse':{'buttons':['forward','sneak'],'seconds':.2},
                  'turn':{'yaw':90.,'pitch':0.,'duration_ms':200},'press':{'action':'use'},
                  'hold':{'action':'attack','seconds':.2},'select_slot':{'slot':2},
                  'inventory_screen':{'opened':True},
                  'click_slot':{'menu_id':1,'state_id':2,'slot':3,'button':1,'mode':'pickup'}}
        for name,params in examples.items():
            with self.subTest(name=name):
                operation=compile_bcl(encode_action(registry,name,params),registry).operations[0]
                decoded=arguments(operation,registry.resolve(operation.namespace,operation.opcode))
                for key,value in params.items():self.assertEqual(decoded[key],value)

    def test_native_motion_trace_uses_client_tick_not_invented_tick(self):
        from blockwire.machine_actions import trace
        from types import SimpleNamespace
        row={'actor_session':'actor-a','client_tick':42}
        def player(sample):return SimpleNamespace(motion_trace=lambda **kw:{'profile':'native_player_motion_ticks_v1','actor_session':'actor-a','samples':[sample]})
        self.assertEqual(trace(player(row),'actor-a')['tick'],42)
        for sample in [{'actor_session':'actor-a','tick':42},{**row,'client_tick':True},{**row,'client_tick':-1}]:
            with self.assertRaises(ValueError):trace(player(sample),'actor-a')

    def test_release_requires_complete_false_native_input_map(self):
        good={'remote_owned_inputs':[],'inputs':{k:False for k in KEYS}}
        self.assertTrue(released(good))
        for row in [{}, {**good,'inputs':{}}, {**good,'remote_owned_inputs':['forward']},
                    {**good,'inputs':{**good['inputs'],'forward':0}},
                    {**good,'inputs':{**good['inputs'],'forward':True}}]:self.assertFalse(released(row))

    def test_pulses_keep_short_leases_and_actor_replacement_stops_renewal(self):
        from blockwire.skills.core import run_skill
        native=MachineNative();player=Player(CallableBackend(native.call))
        result=run_skill(action_registry(),player,'pulse',{'buttons':['forward'],'seconds':.5})
        self.assertEqual(result.status,'succeeded')
        drives=[q for q in native.calls if q['op']=='drive']
        self.assertTrue(drives)
        self.assertTrue(all(q['actor_session']=='actor-a' and 1<=q['ticks']<=6 for q in drives))
        native=MachineNative()
        def replace(q):
            result=native.call(q)
            if q['op']=='drive':native.actor='replacement'
            return result
        result=run_skill(action_registry(),Player(CallableBackend(replace)),'pulse',{'buttons':['forward'],'seconds':.3})
        self.assertEqual(result.reason,'actor_session_changed')
        self.assertEqual(sum(q['op']=='drive' for q in native.calls),1)

    def test_mcp_exposes_only_primitives_and_separate_control(self):
        client=BCLClient('wss://127.0.0.1:8880/v1','a'*64,'unused.pem',session_id='s',agent_id='a',world_id='w',player_uuid='p',actor_session='actor',profile='machine-v1')
        server=create_machine_server(client)
        names={t.name for t in server._tool_manager.list_tools()}
        self.assertEqual(names,set(action_registry()._definitions)|{'reporting','events','look_around','search','interrupt','resume','task_result','compose','remember_plan'})
        inbox=EventInbox('actor')
        for i in range(100):inbox.receive({'type':'event','event_type':'state.scene','data':{'actor_session':'actor','value':i}})
        self.assertEqual(inbox.drain()['coalesced_state_updates'],99)
        for i in range(64):inbox.receive({'type':'event','event_type':'command.completed','data':{}})
        with self.assertRaises(RuntimeError):inbox.receive({'type':'event','event_type':'command.completed','data':{}})


class MachineWire(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cert=self.root/'cert.pem';key=self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-keyout',str(key),'-out',str(self.cert),'-days','1','-subj','/CN=block-bridge.invalid','-addext','subjectAltName=DNS:block-bridge.invalid'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);key.chmod(0o600)
        self.native=MachineNative();self.gateway=BCLGateway(Player(CallableBackend(self.native.call)),'a'*64,self.root/'state',profile='machine-v1')
        self.server=await self.gateway.listen('127.0.0.1',0,server_tls(self.cert,key))
        self.url=f'wss://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/v1'
    async def asyncTearDown(self):
        self.server.close();await self.server.wait_closed();await self.gateway.aclose()
    def client(self,**kwargs):
        return BCLClient(self.url,'a'*64,self.cert,session_id=kwargs.pop('session_id','fixture'),agent_id='a',world_id='w',player_uuid='player-a',actor_session='actor-a',timeout=5.,profile=kwargs.pop('profile','machine-v1'),**kwargs)
    async def event(self,client,name):
        async def find():
            while True:
                row=await client.events.get()
                if row['event_type']==name:return row
        return await asyncio.wait_for(find(),4)
    async def test_event_fed_agent_uses_no_observation_opcodes_and_preserves_results(self):
        from blockwire.machine_agent import run
        from test_agent import Model
        model=Model({'kind':'act','skill':'press','parameters':{'action':'use'}},{'kind':'finish'})
        result=await run(self.client(),model,'fixture',self.root/'agent',duration=10.,model_timeout=1.,max_decisions=2)
        self.assertEqual(result['reason'],'planner_finished_unverified')
        self.assertEqual(result['cleanup'],'released')
        self.assertFalse(result['goal_verified'])
        self.assertEqual(sum(q['op']=='action' for q in self.native.calls),1)
        self.assertEqual(set(model.contexts[0]['events']['state']),{'state.scene','state.inventory','state.navigation','state.crafting'})
        self.assertNotIn('observation',model.contexts[0])
        self.assertTrue(any(e['event_type']=='command.completed' for e in model.contexts[1]['events']['events']))
        self.assertTrue((self.root/'agent/000-request.json').exists())
        with self.assertRaises((ValueError,FileExistsError)):await run(self.client(session_id='other'),model,'fixture',self.root/'agent')

    def typed_model(self):
        from blockwire.tool_decider import OpenAIToolDecider
        registry=action_registry()
        return OpenAIToolDecider('http://127.0.0.1/unused','fixture',registry=registry,
            allowed_skills=set(registry._definitions),control_tools=True,composition_tools=True)

    async def test_known_schema_rejection_is_charged_and_new_decision_is_not_replay(self):
        from blockwire.machine_agent import run
        from test_tool_decider import reply
        model=self.typed_model()
        invalid=reply('compose',json.dumps({'actions':[
            {'name':'press','parameters':{'action':'use'}},
            {'name':'wait_for_observation','parameters':{'seconds':1}}]}))
        with patch.object(model,'_request',side_effect=[invalid,reply('press','{"action":"use"}'),
                reply('finish_session','{"reason":"Fixture only; no objective evidence"}')]) as requests:
            result=await run(self.client(),model,'fixture',self.root/'schema-feedback',duration=10.,model_timeout=1.,max_decisions=4)
        self.assertEqual(requests.call_count,3);self.assertEqual(result['model_calls'],3)
        self.assertEqual(result['reserved_action_operations'],1)
        self.assertEqual(sum(q['op']=='action'for q in self.native.calls),1)
        next_context=json.loads(requests.call_args_list[1].args[0]['messages'][1]['content'])
        self.assertEqual(next_context['recent_requests'][-1]['reply']['status'],'rejected_before_dispatch')
        self.assertEqual(next_context['recent_requests'][-1]['reply']['native_actions_dispatched'],0)
        self.assertEqual(result['cleanup'],'released');self.assertFalse(result['goal_verified'])
        self.assertIn('no objective evidence',result['model_stop_reason'])

    async def test_three_consecutive_schema_rejections_stop_without_effects(self):
        from blockwire.machine_agent import run
        from test_tool_decider import reply
        model=self.typed_model()
        with patch.object(model,'_request',return_value=reply('pulse','{"buttons":["forward"],"seconds":"bad"}')) as requests:
            result=await run(self.client(),model,'fixture',self.root/'invalid-limit',duration=10.,model_timeout=1.,max_decisions=5)
        self.assertEqual(requests.call_count,3);self.assertEqual(result['reason'],'repeated_invalid_tool_arguments')
        self.assertEqual(result['reserved_action_operations'],0)
        self.assertFalse(any(q['op']in {'action','drive'}for q in self.native.calls))
        self.assertEqual(result['cleanup'],'released')

    async def test_provider_refusal_never_enters_schema_feedback_loop(self):
        from blockwire.machine_agent import run
        from test_tool_decider import reply
        model=self.typed_model();response=reply('press','{"action":"use"}')
        response['choices'][0]['message']['refusal']='refused'
        with patch.object(model,'_request',return_value=response) as requests:
            result=await run(self.client(),model,'fixture',self.root/'refusal',duration=10.,model_timeout=1.,max_decisions=5)
        self.assertEqual(requests.call_count,1);self.assertEqual(result['reason'],'RuntimeError')
        self.assertTrue(result['no_retry']);self.assertEqual(result['reserved_action_operations'],0)
        self.assertFalse(any(q['op']in {'action','drive'}for q in self.native.calls))

    async def test_mcp_lifespan_starts_reporting_without_observation_tool_calls(self):
        server=create_machine_server(self.client())
        async with server.settings.lifespan(server):
            events=await server._tool_manager.get_tool('events').run({})
            self.assertEqual(set(events['state']),{'state.scene','state.inventory','state.navigation','state.crafting'})
            await server._tool_manager.get_tool('remember_plan').run({'notes':'A model-authored blueprint, not a built house.'})
            events=await server._tool_manager.get_tool('events').run({})
            self.assertTrue(events['plan_is_unverified'])
            self.assertIn('blueprint',events['plan']['notes'])
            self.assertFalse(any(q['op'] in {'action','drive','click_slot'} for q in self.native.calls))

    async def test_mcp_nested_input_sequence_survives_real_json_transport(self):
        client=self.client();server=create_machine_server(client)
        async with server.settings.lifespan(server):
            receipt=await server._tool_manager.get_tool('input_sequence').run({'phases':[
                {'buttons':['forward'],'seconds':.1,'look':{'yaw':90.,'pitch':0.}}]})
            result=await client.wait(receipt['task_id'])
            self.assertEqual(result['status'],'completed')
            self.assertTrue(any(q['op']=='drive' and 'forward' in q['buttons'] for q in self.native.calls))
            self.assertTrue(any(q['op']=='look' for q in self.native.calls))
            self.assertEqual(self.native.held,[])

    async def test_uncertain_slot_effect_halts_queued_work(self):
        from test_machine_manipulation import planks_steps
        self.native.inventory_extra={'guarded_inventory':True,'container_open':True,'carried':{'empty':True},
            'slots':[{'slot':36,'active':True,'empty':False,'item':'minecraft:oak_log','count':2}]}
        async with self.client() as client:
            accepted=await client.action('slot_program',{'menu_id':1,'steps':planks_steps()[:1]})
            tail=await client.action('press',{'action':'use'})
            result=await client.wait(accepted['task_id'])
            self.assertNotEqual(result['status'],'completed')
            self.assertEqual((await client.wait(tail['task_id']))['status'],'cancelled')
            self.assertTrue(self.gateway.jobs.halted)
            self.assertEqual(sum(q['op']=='click_slot' for q in self.native.calls),1)
            self.assertFalse(any(q['op']=='action' for q in self.native.calls))

    async def test_model_notes_persist_as_data_without_dispatch(self):
        from blockwire.machine_agent import run
        from test_agent import Model
        model=Model({'kind':'plan','notes':'My own blueprint: wall coordinates are intentions, not evidence.'},{'kind':'finish'})
        result=await run(self.client(),model,'fixture',self.root/'notes',duration=10.,model_timeout=1.,max_decisions=2)
        self.assertEqual(model.contexts[1]['plan']['notes'],result['plan']['notes'])
        self.assertTrue(model.contexts[1]['plan_is_unverified'])
        self.assertEqual(result['reserved_action_operations'],0)
        self.assertFalse(any(q['op'] in {'action','drive','click_slot'} for q in self.native.calls))

    async def test_model_can_interrupt_its_composition_while_events_continue(self):
        from blockwire.machine_agent import run
        from test_agent import Model
        model=Model({'kind':'compose','actions':[
            {'name':'pulse','parameters':{'buttons':['forward'],'seconds':2.}},
            {'name':'hold','parameters':{'action':'attack','seconds':2.}},
            {'name':'press','parameters':{'action':'use'}}]},
            {'kind':'control','control':'interrupt'},{'kind':'finish'})
        result=await run(self.client(),model,'fixture',self.root/'composing-agent',duration=15.,model_timeout=1.,max_decisions=3)
        self.assertEqual(result['reserved_action_operations'],3)
        self.assertEqual(result['cleanup'],'released')
        self.assertTrue(any(not t['terminal'] for t in model.contexts[1]['active_tasks']))
        self.assertFalse(any(q['op']=='action' for q in self.native.calls))

    async def test_entire_composition_validated_before_first_effect(self):
        async with self.client() as client:
            with self.assertRaises(ValueError):await client.compose([
                {'name':'press','parameters':{'action':'use'}},
                {'name':'pulse','parameters':{'buttons':['forward','back']}}])
            self.assertFalse(any(q['op']=='action' for q in self.native.calls))

    async def test_observer_cannot_interrupt_or_act(self):
        async with self.client(role='observer') as client:
            self.assertEqual((await client.interrupt())['status'],'failed')
            self.assertEqual((await client.action('press',{'action':'use'}))['status'],'failed')
            self.assertEqual((await client.report(['state.scene']))['status'],'completed')
            await self.event(client,'state.scene')
            self.assertFalse(any(q['op']=='action' for q in self.native.calls))

    async def test_unchanged_state_has_fresh_heartbeat_not_permanent_stale_cache(self):
        async with self.client() as client:
            await client.report(['state.scene'])
            first=(await self.event(client,'state.scene'))['data']
            fresh=(await self.event(client,'state.scene'))['data']
            self.assertTrue(first['changed']);self.assertFalse(fresh['changed'])
            self.assertEqual(first['value'],fresh['value'])
            self.assertGreater(fresh['observed_monotonic_ns'],first['observed_monotonic_ns'])
            self.assertGreater(fresh['sample_id'],first['sample_id'])

    async def test_explicit_reconnect_never_implicitly_resumes(self):
        async with self.client() as client:
            self.assertEqual(client.control_state,'ready')
        for _ in range(100):
            if 'fixture' not in self.gateway.bound:break
            await asyncio.sleep(.02)
        async with self.client() as client:
            self.assertEqual(client.control_state,'requested')
            self.assertEqual((await client.action('press',{'action':'use'}))['status'],'failed')
            await self.event(client,'control.released')
            self.assertEqual(client.control_state,'released')
            self.assertEqual((await client.resume())['control_state'],'ready')
            self.assertFalse(any(q['op']=='action' for q in self.native.calls))

    async def test_wire_sequence_gap_fails_closed(self):
        client=self.client()
        class Socket:
            closed=False
            async def close(self):self.closed=True
            async def __aiter__(self):
                for sequence,kind in [(1,'response'),(3,'progress')]:
                    yield json.dumps({'language':'BCL/1','session_id':'fixture','connection_id':'connection',
                        'sequence':sequence,'type':kind,'request_id':0,'status':'bound'})
        client.ws=Socket()
        with self.assertRaises(RuntimeError):await client._read()
        self.assertTrue(client.ws.closed)
        self.assertTrue(client.progress.empty())

    async def test_emergency_interrupt_bypasses_failed_audit_admission(self):
        from types import SimpleNamespace
        async with self.client() as client:
            running=await client.action('pulse',{'buttons':['forward'],'seconds':2.})
            await asyncio.sleep(.05)
            def unavailable(*args,**kwargs):raise RuntimeError('audit full')
            with patch.object(self.gateway,'feedback',SimpleNamespace(audit=unavailable)):
                response=await client.interrupt()
                self.assertTrue(response['cancellation_requested'])
                await client.wait(running['task_id'])
                await self.event(client,'control.released')
                self.assertEqual((await client.action('press',{'action':'use'}))['status'],'failed')
            self.assertFalse(any(q['op']=='action' for q in self.native.calls))

    async def test_interrupt_during_resume_invalidates_the_pending_release_proof(self):
        from blockwire.bcl.machine_control import MachineControl
        control=MachineControl(self.gateway.jobs,'not-yet-bound','actor-a',self.gateway.player)
        control.state='released'
        task=asyncio.create_task(control.resume());await asyncio.sleep(.01)
        control.interrupt()
        with self.assertRaises(ValueError):await task
        self.assertEqual(control.state,'requested')

    async def test_profile_mismatch_before_any_native_action(self):
        with self.assertRaises(RuntimeError):
            async with self.client(profile='legacy'):pass
        self.assertFalse(self.native.calls)
    async def test_reporting_during_action_and_priority_cancel_flushes_queue(self):
        async with self.client() as client:
            response=await client.report(['state.scene','state.inventory','command.completed'])
            self.assertEqual(response['status'],'completed')
            initial=await self.event(client,'state.scene');self.assertIn('sample_id',initial['data'])
            a=await client.action('pulse',{'buttons':['forward'],'seconds':2.})
            b=await client.action('press',{'action':'use'})
            self.assertEqual((await client.cancel(a['task_id']))['status'],'failed')
            self.assertEqual((await client.reset())['status'],'failed')
            self.assertEqual((await client.respawn())['status'],'failed')
            await asyncio.sleep(.1);self.native.yaw=45.
            changed=await self.event(client,'state.scene')
            self.assertEqual(changed['data']['value']['yaw'],45.)
            self.assertIsNone(self.gateway.jobs.jobs[a['task_id']]['result'])
            start=time.monotonic();reply=await client.interrupt();self.assertLess(time.monotonic()-start,.3)
            self.assertTrue(reply['cancellation_requested']);self.assertFalse(reply['released'])
            refused=await client.action('press',{'action':'use'});self.assertEqual(refused['status'],'failed')
            await client.wait(a['task_id']);await client.wait(b['task_id'])
            await self.event(client,'control.released')
            self.assertEqual((await client.action('press',{'action':'use'}))['status'],'failed')
            self.assertFalse(any(q['op']=='action' for q in self.native.calls))
            self.assertEqual((await client.resume())['control_state'],'ready')
            c=await client.action('press',{'action':'use'});done=await client.wait(c['task_id'])
            self.assertEqual(done['status'],'completed',done)
            self.assertFalse(done['result']['objective_verified'])
            self.assertEqual(sum(q['op']=='action' for q in self.native.calls),1)
    async def test_stale_release_quarantines_without_replay(self):
        async with self.client() as client:
            self.native.freeze_tick=True
            await client.interrupt();event=await self.event(client,'control.quarantined')
            self.assertEqual(event['data']['reason'],'UNKNOWN_NO_RETRY')
            self.assertTrue(self.gateway.jobs.halted)
            response=await client.action('press',{'action':'use'})
            self.assertEqual(response['status'],'failed')
            self.assertFalse(any(q['op']=='action' for q in self.native.calls))
    async def test_query_rejection_and_receipt_without_release_is_not_completion(self):
        async with self.client() as client:
            self.assertEqual((await client.send('V0'))['status'],'failed')
            self.native.freeze_tick=True
            response=await client.action('press',{'action':'use'})
            queued=await client.action('press',{'action':'attack'})
            done=await client.wait(response['task_id'])
            self.assertNotEqual(done['status'],'completed')
            queued_result=await client.wait(queued['task_id'])
            self.assertEqual(queued_result['status'],'cancelled')
            self.assertTrue(self.gateway.jobs.halted)
            self.assertEqual(sum(q['op']=='action' for q in self.native.calls),1)

if __name__=='__main__':unittest.main()
