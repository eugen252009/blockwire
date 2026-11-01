"""Actual TLS session hardening with fake native actor; not gameplay evidence."""
import asyncio,time,unittest
from blockwire import BridgeError
from blockwire.client import NativeRejected
from blockwire.errors import classify,FaultKind
import test_bcl_websocket as setup

class HardeningContracts(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=setup.WebSocketContracts.asyncSetUp
    asyncTearDown=setup.WebSocketContracts.asyncTearDown
    client=setup.WebSocketContracts.client
    disconnected=setup.WebSocketContracts.disconnected
    async def test_GH01_second_controller_denied_observer_reads_without_native_control(self):
        async with self.client('control') as control:
            with self.assertRaises(RuntimeError):
                async with self.client('other'):pass
            async with self.client('watch',role='observer') as watch:
                before=len(self.native.calls);r=await watch.send('I0\nV0')
                self.assertEqual(r['status'],'completed')
                self.assertFalse(any(q['op']=='stop' for q in self.native.calls[before:]))
                denied=await watch.send('M0 1 64 1');self.assertEqual(denied['diagnostics'][0]['code'],'PERMISSION_DENIED')
                self.assertEqual((await control.send('I0'))['status'],'completed')
    async def test_GH02_late_cleanup_reaper_releases_binding_after_grace(self):
        self.gateway.cleanup_grace=.02
        async with self.client() as client:
            self.gateway.jobs.jobs['fake']={'session_id':'session','result':None,'runner':None,'cancelled':False}
        await asyncio.sleep(.06)
        self.assertIn('session',self.gateway.bound)
        self.assertEqual(self.gateway.session_states['session'],'quarantined_until_cleanup')
        self.gateway.jobs.jobs['fake']['result']={'status':'cancelled'}
        await self.disconnected()
        self.assertNotIn('player-a',self.gateway.controllers)
        async with self.client() as client:self.assertEqual((await client.send('S0 ?'))['status'],'completed')
    async def test_GH03_typed_recoverable_rejection_does_not_latch_transport(self):
        outer=self.gateway.player.backend._dispatch
        native_player=next(cell.cell_contents for cell in outer.__closure__ if isinstance(cell.cell_contents,setup.Player))
        dispatch=native_player.backend._dispatch
        native_player.backend._dispatch=lambda q:(_ for _ in ()).throw(NativeRejected('missing_materials'))
        with self.assertRaises(NativeRejected):self.gateway.player.observe()
        self.assertFalse(self.gateway.failed)
        native_player.backend._dispatch=dispatch
        async with self.client() as c:self.assertEqual((await c.send('I0'))['status'],'completed')
        self.assertEqual(classify(NativeRejected('brand_new_recoverable_native_code')),FaultKind.PRECONDITION)
        self.assertEqual(classify(BridgeError('connection_failed')),FaultKind.TRANSPORT)
    async def test_GH04_dead_is_not_transport_failure_and_modal_queries_remain_live(self):
        dispatch=self.gateway.player.backend._dispatch;dead=[False]
        def call(q):
            result=dispatch(q)
            if q['op']=='observe' and dead[0]:result={**result,'alive':False,'health':0.}
            return result
        self.gateway.player.backend._dispatch=call
        async with self.client() as c:
            dead[0]=True;self.gateway.sampled_at=0
            event=await asyncio.wait_for(c.events.get(),2.)
            self.assertEqual(event['event_type'],'player.dead')
            self.assertFalse(self.gateway.failed)
            blocked=await c.send('I0');self.assertEqual(blocked['status'],'blocked')
            self.assertEqual(blocked['result']['diagnostics'][0]['code'],'PLAYER_DEAD')
            self.assertEqual((await c.send('S0 ?'))['status'],'completed')
    async def test_GH05_sender_failure_closes_connection_and_releases_session(self):
        async with self.client() as c:
            ws=next(iter(self.gateway.connections))
            async def broken(*_):raise RuntimeError('fixture sender failed')
            ws.send=broken
            with self.assertRaises(ConnectionError):await c.send('S0 ?')
        await self.disconnected()
    async def test_GH06_slow_sender_times_out_instead_of_stalling_forever(self):
        self.gateway.send_timeout=.05
        async with self.client() as c:
            ws=next(iter(self.gateway.connections));original=ws.send
            async def slow(*args):await asyncio.sleep(10.);await original(*args)
            ws.send=slow
            start=time.monotonic()
            with self.assertRaises(ConnectionError):await c.send('S0 ?')
            self.assertLess(time.monotonic()-start,1.)
        await self.disconnected()
    async def test_GH12_not_in_world_is_distinct_from_dead_and_transport(self):
        dispatch=self.gateway.player.backend._dispatch;left=[False]
        def call(q):
            value=dispatch(q)
            if q['op']=='observe' and left[0]:return {**value,'in_world':False,'alive':False}
            return value
        self.gateway.player.backend._dispatch=call
        async with self.client() as c:
            left[0]=True;self.gateway.sampled_at=0
            event=await asyncio.wait_for(c.events.get(),2.);self.assertEqual(event['event_type'],'player.not_in_world')
            self.assertFalse(self.gateway.failed)
            result=await c.send('I0');self.assertEqual(result['result']['diagnostics'][0]['code'],'PLAYER_NOT_IN_WORLD')
            self.assertEqual((await c.send('S0 ?'))['status'],'completed')

    async def test_GH11_respawn_is_explicit_fenced_and_requires_new_actor_binding(self):
        outer=self.gateway.player.backend._dispatch
        native_player=next(cell.cell_contents for cell in outer.__closure__ if isinstance(cell.cell_contents,setup.Player))
        original=native_player.backend._dispatch;dead=[False];requests=[]
        def call(q):
            if q['op']=='respawn':
                requests.append(q);self.assertEqual(q['actor_session'],'actor-a')
                self.native.actor='respawned';dead[0]=False;return {'text':'submitted'}
            result=original(q)
            if q['op']=='observe' and dead[0]:return {**result,'alive':False,'health':0.}
            return result
        native_player.backend._dispatch=call
        async with self.client() as c:
            denied=await c.respawn();self.assertEqual(denied['diagnostics'][0]['code'],'PERMISSION_DENIED')
            self.gateway.allow_respawn=True;dead[0]=True;self.gateway.sampled_at=0
            response=await c.respawn();self.assertEqual(response['status'],'submitted')
            for _ in range(3):
                e=await asyncio.wait_for(c.events.get(),2.)
                if e['event_type']=='player.respawned':break
            else:self.fail('No respawn event')
        await self.disconnected();self.assertEqual(len(requests),1);self.assertFalse(self.gateway.failed)

    async def test_GH08_worker_base_exception_does_not_strand_session_or_queue(self):
        from blockwire.bcl import Command
        from blockwire.skills import SkillDefinition,SkillParameters
        def crash(c,g):raise SystemExit('fixture plugin termination')
        self.registry.skills.register(SkillDefinition('crash','fixture',SkillParameters,crash))
        self.registry.register(Command('test','I1','fixture.crash','fixture',(),'crash',frozenset({'inventory'})))
        async with self.client() as c:
            result=await c.send('test:I1');self.assertEqual(result['status'],'failed')
            result=await c.send('I0');self.assertEqual(result['status'],'completed')
        await self.disconnected()
    async def test_GH09_watcher_failure_is_supervised_and_socket_cannot_stay_half_alive(self):
        async with self.client() as c:
            accepted=await c.send('S0 async\ntest:I0')
            original=self.gateway.jobs.status
            def broken(*_):raise RuntimeError('fixture watcher failed')
            self.gateway.jobs.status=broken
            try:
                with self.assertRaises(ConnectionError):await c.wait(accepted['task_id'])
            finally:self.gateway.jobs.status=original
        await self.disconnected()
    async def test_GH10_queue_overflow_is_detectable_and_cancels_connection(self):
        from blockwire.controller import Event
        self.gateway.send_timeout=.05
        async with self.client() as c:
            await c.send('E0 player.health')
            ws=next(iter(self.gateway.connections));original=ws.send
            async def slow(*args):await asyncio.sleep(2.);await original(*args)
            ws.send=slow
            with self.assertRaises(RuntimeError):
                for n in range(80):await self.gateway.publish(Event('player.health',{'health':n}))
        await self.disconnected()

    async def test_GH07_respawn_changes_actor_and_requires_explicit_new_binding(self):
        dispatch=self.gateway.player.backend._dispatch;phase=[0]
        def call(q):
            result=dispatch(q)
            if q['op']=='observe' and phase[0]==1:result={**result,'alive':False,'health':0.}
            return result
        self.gateway.player.backend._dispatch=call
        async with self.client() as c:
            phase[0]=1;self.gateway.sampled_at=0
            self.assertEqual((await asyncio.wait_for(c.events.get(),2.))['event_type'],'player.dead')
            phase[0]=2;self.native.actor='new-actor';self.gateway.sampled_at=0
            self.assertEqual((await asyncio.wait_for(c.events.get(),2.))['event_type'],'player.respawned')
        await self.disconnected();self.assertFalse(self.gateway.failed)

if __name__=='__main__':unittest.main()
