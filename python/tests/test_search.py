"""Targeted perception contracts. Simulated backend/TLS, not Minecraft acceptance."""
import asyncio
import copy
import json
import math
import threading
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from blockwire import CallableBackend, Player
from blockwire.client import BridgeError, NativeRejected
from blockwire.skills import default_registry, run_skill
from blockwire.skills.core import SkillStop
from blockwire.skills.search import Search, SearchPage, SearchScan, search_async
import test_machine_profile as wire


def page_reply(q, *, found=True):
    p=q['page'];eye=[.5,1.62,.5];point=[1.,1.62,20.];position=[1,1,20]
    return {'profile':'targeted_surface_search_v1','actor_session':q.get('actor_session','actor-a'),
        'target':q['target'],'range':q['range'],'cone_degrees':q['cone_degrees'], 'page':p,'pages':34,
        'next_page':p+1 if p<33 else None,'view_id':'a'*64,'visited_cells':min(128,4225-128*p),
        'rays_cast':min(128,4225-128*p),'truncated':False,'sampled_at_ms':1000+p,'eye_position':eye,'forward':[0.,0.,1.],
        'matches':[{'id':'minecraft:oak_log','position':position,'aim_position':point,
                    'distance_blocks':math.dist(eye,point),'eye_distance_to_center':math.dist(eye,[v+.5 for v in position]),
                    'face':'north'}] if found and p in (17,18) else []}


class SearchContracts(unittest.TestCase):
    def player(self, alter=lambda q,r:r, found=True):
        self.calls=[]
        def call(q):
            self.calls.append(q)
            if q['op']=='observe':return {'in_world':True,'alive':True,'search_supported':True,'actor_session':'actor-a'}
            self.assertEqual(q['op'],'search')
            self.assertEqual(q['actor_session'],'actor-a')
            return alter(q,page_reply(q,found=found))
        return Player(CallableBackend(call))

    def test_additional_reads_dedup_and_no_ownership_or_actions(self):
        from blockwire.ownership import claim_control,release_control,control_busy
        player=self.player();lease=claim_control(player,lambda:None)
        try:
            try:result=player.search()
            except RuntimeError as error:self.fail('Read-only search attempted to acquire controls: '+str(error))
            self.assertTrue(control_busy(player))
        finally:release_control(player,lease)
        self.assertEqual(result['status'],'succeeded',result)
        self.assertEqual(result['cleanup'],'not_required')
        d=result['details'];self.assertEqual(len(d['matches']),1);self.assertEqual(d['visited_cells'],4225)
        self.assertTrue(d['scan_complete']);self.assertFalse(d['absence_proven']);self.assertFalse(d['pixel_visibility_verified'])
        requests=[q for q in self.calls if q['op']=='search'];self.assertEqual(len(requests),34)
        self.assertEqual([q['page']for q in requests],list(range(34)))
        self.assertNotIn('view_id',requests[0]);self.assertTrue(all(q['view_id']=='a'*64 for q in requests[1:]))

    def test_not_seen_is_not_absent_and_old_mod_does_not_fallback(self):
        result=self.player(found=False).search()
        self.assertEqual(result['reason'],'target_not_seen');self.assertFalse(result['details']['absence_proven'])
        calls=[];p=Player(CallableBackend(lambda q:calls.append(q)or {'in_world':True,'alive':True}))
        self.assertEqual(p.search()['reason'],'search_mod_upgrade_required');self.assertEqual(calls,[{'op':'observe'}])

    def test_strict_requests_precede_any_read(self):
        for args in [{'target':'wood'}, {'target':'oak_log'}, {'target':'minecraft:oak_log;op'}, {'range':True},
                     {'range':65}, {'range':2.}, {'cone_degrees':91}, {'cone_degrees':9}, {'timeout_seconds':float('nan')}, {'x':3}]:
            p=self.player()
            with self.assertRaises(ValidationError):run_skill(default_registry(),p,'search',args)
            self.assertEqual(self.calls,[])
        for args in [{'page':34}, {'page':1}, {'view_id':'bad'}, {'target':'logs','extra':1}]:
            with self.assertRaises(ValidationError):SearchPage.model_validate(args)

    def test_actor_pose_query_sequence_and_output_validation(self):
        changes=[lambda r:r.update(actor_session='other'), lambda r:r.update(view_id='b'*64),
                 lambda r:r.update(eye_position=[1.,1.62,.5]),lambda r:r.update(target='minecraft:stone'),
                 lambda r:r.update(page=20),lambda r:r.update(next_page=33),lambda r:r.update(visited_cells=127),
                 lambda r:r.update(rays_cast=129),lambda r:r.update(forward=[float('nan'),0.,1.])]
        for change in changes:
            def alter(q,r):
                if q['page']==1:change(r)
                return r
            result=self.player(alter).search()
            self.assertEqual(result['status'],'blocked',result);self.assertEqual(len(self.calls),3)
            self.assertNotIn('matches',result['details'])
        for field,value in [('id','minecraft:oak_planks'),('position',[True,1,20]),('distance_blocks',1.),('aim_position',[1.,1.62,-20.])]:
            def alter(q,r):
                if r['matches']:r['matches'][0][field]=value
                return r
            result=self.player(alter).search();self.assertEqual(result['status'],'blocked',result)

    def test_cancel_deadline_and_no_replay_after_native_rejection(self):
        event=threading.Event();event.set();p=self.player()
        result=run_skill(default_registry(),p,'search',{},cancel_event=event)
        self.assertEqual(result.status,'cancelled');self.assertEqual(self.calls,[])
        from blockwire.skills.search import search
        from blockwire.skills.core import SkillContext
        with self.assertRaises(SkillStop):search(SkillContext(p,event,10.,lambda _:None,clock=lambda:0.),Search())
        self.assertEqual(self.calls,[])
        event.clear()
        def alter(q,r):event.set();return r
        p=self.player(alter)
        result=run_skill(default_registry(),p,'search',{},cancel_event=event)
        self.assertEqual(result.status,'cancelled');self.assertEqual(len(self.calls),2)
        ticks=iter([0.,100.]);p=self.player()
        self.assertEqual(run_skill(default_registry(),p,'search',{},clock=lambda:next(ticks,100.)).status,'timed_out')
        self.assertEqual(self.calls,[])
        def reject(q,r):raise NativeRejected('search_view_changed')
        result=self.player(reject).search();self.assertEqual(result['reason'],'search_view_changed');self.assertEqual(len(self.calls),2)

    def test_coherent_hit_outside_cone_or_range_is_rejected(self):
        for position,eye_point,goal in [([20,1,20],[20.,1.62,20.],Search()),([1,1,20],[1.,1.62,20.],Search(range=8))]:
            scan=SearchScan(goal,'actor-a');r=page_reply(scan.request(),found=False)
            r['matches']=[{'id':'minecraft:oak_log','position':position,'aim_position':eye_point,
                'distance_blocks':math.dist(r['eye_position'],eye_point),
                'eye_distance_to_center':math.dist(r['eye_position'],[v+.5 for v in position]),'face':'north'}]
            with self.assertRaises(SkillStop):scan.accept(r)

    def test_result_bound_stops_without_claiming_complete_scan(self):
        scan=SearchScan(Search(),'actor-a');r=page_reply(scan.request(),found=False)
        # 32 distinct target voxels whose surface points/centres are in the cone.
        r['matches']=[{'id':'minecraft:oak_log','position':[0,1,z],'aim_position':[.5,1.62,float(z)],
            'distance_blocks':z-.5,'eye_distance_to_center':math.dist([.5,1.62,.5],[.5,1.5,z+.5]),'face':'north'}for z in range(1,33)]
        scan.accept(r);self.assertTrue(scan.done)
        self.assertEqual(len(scan.result().details['matches']),32)
        self.assertFalse(scan.result().details['scan_complete']);self.assertTrue(scan.result().details['result_limit_reached'])
        with self.assertRaises(ValueError):scan.request()

    def test_cli_and_mcp_thin_dispatch(self):
        from blockwire.cli import main
        from blockwire.mcp_server import create_server
        with patch('blockwire.cli.Bridge.from_env'),patch('blockwire.cli.Player')as factory,patch('sys.stdout'):
            factory.return_value.search.return_value={'status':'succeeded'}
            main(['search','minecraft:oak_log','--range','32','--cone-degrees','45'])
            factory.return_value.search.assert_called_once_with('minecraft:oak_log',range=32,cone_degrees=45,timeout_seconds=10.)
        p=self.player()
        with patch('blockwire.mcp_server.Bridge.from_env'),patch('blockwire.mcp_server.Player',return_value=p):server=create_server()
        async def check():
            from mcp.server.fastmcp.exceptions import ToolError
            schema=server._tool_manager.get_tool('search').parameters
            self.assertFalse(schema.get('additionalProperties',True));self.assertEqual(schema['properties']['range']['maximum'],64)
            for arguments in [{'range':'32'},{'x':100},{'target':'wood'}]:
                with self.assertRaises(ToolError):await server.call_tool('search',arguments)
            self.assertEqual(self.calls,[])
            reply=await server.call_tool('search',{})
            result=reply[1]if isinstance(reply,tuple)else json.loads(reply[0].text)
            self.assertEqual(result['reason'],'targets_observed')
        asyncio.run(check());self.assertEqual(len(self.calls),35)


class SearchAsync(unittest.IsolatedAsyncioTestCase):
    async def test_ordinary_mcp_deadline_retains_single_inflight_read(self):
        from blockwire.mcp_server import create_server
        from mcp.server.fastmcp.exceptions import ToolError
        entered=threading.Event();release=threading.Event();finished=threading.Event();calls=[]
        def native(q):
            calls.append(q);entered.set()
            try:release.wait(3);return {'search_supported':True,'alive':True,'in_world':True,'actor_session':'actor-a'}
            finally:finished.set()
        with tempfile.TemporaryDirectory()as directory:
            with patch('blockwire.mcp_server.Bridge.from_env'),patch('blockwire.mcp_server.Player',return_value=Player(CallableBackend(native))):
                server=create_server(bcl_state_directory=Path(directory)/'bcl')
            try:
                result=await server._tool_manager.call_tool('search',{'timeout_seconds':.1})
                self.assertEqual(result['status'],'timed_out');self.assertTrue(entered.is_set())
                self.assertFalse(finished.is_set())
                with self.assertRaises(ToolError):await server._tool_manager.call_tool('search',{})
                self.assertEqual(calls,[{'op':'observe'}])
            finally:
                release.set();self.assertTrue(await asyncio.to_thread(finished.wait,2));await asyncio.sleep(.01)

    async def test_async_feedback_audits_completion_not_coroutine_creation(self):
        from blockwire.mcp_server import create_server
        from blockwire.feedback import FeedbackStore,InputPolicy
        from mcp.server.fastmcp.exceptions import ToolError
        entered=threading.Event();release=threading.Event()
        def native(q):entered.set();release.wait(3);raise BridgeError('connection_lost')
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory)
            with patch('blockwire.mcp_server.Bridge.from_env'),patch('blockwire.mcp_server.Player',return_value=Player(CallableBackend(native))):
                server=create_server(bcl_state_directory=root/'bcl',feedback_directory=root/'feedback',
                    feedback_identity={'agent_id':'a','world_id':'w','player_id':'p'},input_policy=InputPolicy(allowed_tools=frozenset({'search'})))
            task=asyncio.create_task(server._tool_manager.call_tool('search',{}))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                with FeedbackStore(root/'feedback').db()as db:self.assertEqual(db.execute('SELECT status FROM inputs').fetchone()[0],'received')
            finally:release.set()
            with self.assertRaises(ToolError):await task
            with FeedbackStore(root/'feedback').db()as db:self.assertEqual(db.execute('SELECT status FROM inputs').fetchone()[0],'unknown_no_retry')


class SearchWire(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=wire.MachineWire.asyncSetUp
    asyncTearDown=wire.MachineWire.asyncTearDown
    client=wire.MachineWire.client
    event=wire.MachineWire.event

    async def test_real_tls_mcp_search_is_not_an_action_and_schema_is_strict(self):
        self.native.search_handler=page_reply
        server=wire.create_machine_server(self.client())
        async with server.settings.lifespan(server):
            reply=await server.call_tool('search',{'target':'logs'})
            result=reply[1]if isinstance(reply,tuple)else json.loads(reply[0].text)
            self.assertEqual(result['reason'],'targets_observed',result)
            from mcp.server.fastmcp.exceptions import ToolError
            for arguments in [{'range':True},{'range':'32'},{'x':100},{'target':'wood'}]:
                with self.assertRaises(ToolError):await server.call_tool('search',arguments)
            self.assertEqual(server._tool_manager.get_tool('search').parameters,Search.model_json_schema())
        self.assertEqual(sum(q['op']=='search'for q in self.native.calls),34)
        self.assertFalse(any(q['op']in {'drive','look','action','stop'}for q in self.native.calls))
        self.assertEqual(len(self.gateway.jobs.jobs),0)

    async def test_interrupt_does_not_wait_for_search_and_discards_old_page(self):
        entered=threading.Event();release=threading.Event()
        def slow(q):entered.set();release.wait(3);return page_reply(q)
        self.native.search_handler=slow
        async with self.client()as c:
            scan=asyncio.create_task(c.search_page(SearchPage().model_dump(exclude_none=True)))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                receipt=await asyncio.wait_for(c.interrupt(),.5)
                self.assertTrue(receipt['cancellation_requested']);self.assertFalse(release.is_set())
            finally:release.set()
            with self.assertRaises(SkillStop)as stopped:await scan
            self.assertEqual(stopped.exception.status,'cancelled')
            self.assertEqual(sum(q['op']=='search'for q in self.native.calls),1)

    async def test_concurrent_search_page_is_rejected_before_native_dispatch(self):
        entered=threading.Event();release=threading.Event()
        def slow(q):entered.set();release.wait(3);return page_reply(q)
        self.native.search_handler=slow
        async with self.client()as c:
            pending=asyncio.create_task(c.search_page(SearchPage().model_dump(exclude_none=True)))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,2))
                try:
                    with self.assertRaises(SkillStop):await asyncio.wait_for(c.search_page(SearchPage().model_dump(exclude_none=True)),.5)
                except TimeoutError:self.fail('Second search page admitted while native RPC busy')
                self.assertEqual(sum(q['op']=='search'for q in self.native.calls),1)
            finally:
                release.set();await pending

    async def test_observer_and_permission_fence(self):
        self.native.search_handler=page_reply
        async with self.client(role='observer')as c:
            result=await c.search({});self.assertEqual(result['status'],'succeeded')
            self.gateway.jobs.permissions=frozenset()
            result=await c.search({});self.assertEqual(result['status'],'blocked')
            self.assertIn('observe permission',result['reason'])
        self.assertEqual(sum(q['op']=='search'for q in self.native.calls),34)

    async def test_transport_failure_is_terminal_and_never_retried(self):
        def broken(q):raise BridgeError('connection_lost')
        self.native.search_handler=broken
        async with self.client()as c:
            with self.assertRaises(ConnectionError):await c.search({})
        self.assertTrue(self.gateway.failed)
        self.assertEqual(sum(q['op']=='search'for q in self.native.calls),1)

    async def test_machine_agent_charges_search_budget_before_native_pages(self):
        from blockwire.machine_agent import run
        from test_agent import Model
        self.native.search_handler=page_reply
        model=Model({'kind':'perception','name':'look_around','parameters':{}},
                    {'kind':'perception','name':'search','parameters':{}},{'kind':'finish'})
        result=await run(self.client(),model,'find logs',self.root/'agent',duration=12.,model_timeout=1.,max_actions=34)
        self.assertEqual(result['reserved_search_pages'],34);self.assertEqual(result['reserved_action_operations'],0)
        self.assertEqual(result['cleanup'],'released');self.assertFalse(result['goal_verified'])
        self.assertTrue(model.contexts[1]['recent_requests'][0]['reply']['cached'])
        self.assertEqual(model.contexts[2]['recent_requests'][1]['reply']['reason'],'targets_observed')
        self.assertTrue((self.root/'agent/001-search-intent.json').exists())
        self.assertEqual(sum(q['op']=='search'for q in self.native.calls),34)

    async def test_search_budget_rejection_prevents_native_reads(self):
        from blockwire.machine_agent import run
        from test_agent import Model
        self.native.search_handler=page_reply
        model=Model({'kind':'perception','name':'search','parameters':{}})
        result=await run(self.client(),model,'fixture',self.root/'budget',duration=10.,model_timeout=1.,max_actions=33)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['reserved_search_pages'],0)
        self.assertFalse(any(q['op']=='search'for q in self.native.calls))
