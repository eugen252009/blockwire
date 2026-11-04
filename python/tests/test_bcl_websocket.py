"""Real authenticated TLS/WebSocket transport + simulated native backend, NOT Minecraft."""
import asyncio,json,os,subprocess,tempfile,time,unittest
from pathlib import Path
from websockets.asyncio.client import connect
from blockwire import Player,CallableBackend,Bridge
from blockwire.bcl import default_commands,Command
from blockwire.bcl.client import BCLClient
from blockwire.bcl.gateway import BCLGateway,server_tls
from blockwire.skills import SkillDefinition,SkillParameters,SkillResult
from test_agent import Native

class WebSocketContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cert=self.root/'certificate.pem';self.key=self.root/'key.pem'
        command=['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-keyout',str(self.key),'-out',str(self.cert),'-days','1','-subj','/CN=block-bridge.invalid','-addext','subjectAltName=DNS:block-bridge.invalid']
        subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True);self.key.chmod(0o600)
        self.native=Native();self.registry=default_commands();self.registry.namespace('test');self.starts=0
        def waiting(c,g):
            self.starts+=1;c.pause(.6);return SkillResult(status='succeeded',reason='wait_observed',text='fixture')
        self.registry.skills.register(SkillDefinition('waiting','fixture',SkillParameters,waiting))
        self.registry.register(Command('test','I0','fixture.wait','fixture',(),'waiting',frozenset({'inventory'})))
        self.gateway=BCLGateway(Player(CallableBackend(self.native.call)),'a'*64,self.root/'state',registry=self.registry)
        self.server=await self.gateway.listen('127.0.0.1',0,server_tls(self.cert,self.key))
        self.url=f'wss://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/v1'
    async def asyncTearDown(self):
        self.server.close();await self.server.wait_closed();self.gateway.jobs.close()
    def client(self,sid='session',**kwargs):
        return BCLClient(self.url,kwargs.pop('token','a'*64),kwargs.pop('cert',self.cert),session_id=sid,
            agent_id='agent',world_id='fixture',player_uuid=kwargs.pop('player_uuid','player-a'),actor_session='actor-a',timeout=5.,**kwargs)
    async def disconnected(self,sid='session'):
        for _ in range(200):
            if sid not in self.gateway.bound:return
            await asyncio.sleep(.01)
        self.fail('Session cleanup never finished')
    async def test_terminal_file_sender_uses_real_tls_and_waits(self):
        from blockwire.bcl.cli import read_source, send_file
        path = self.root / 'human program.bcl'
        path.write_text('S0 async\nI0', encoding='utf-8')
        output = []
        async with self.client() as client:
            self.assertEqual(await send_file(client, read_source(path), output.append), 0)
        self.assertEqual([r['status'] for r in output], ['accepted', 'completed'])

    async def test_unified_module_file_runner_process_and_exit_code(self):
        import sys
        path = self.root / 'recorded program.bcl'
        path.write_text('S0 async\nI0', encoding='utf-8')
        (self.root / 'token').write_text('a' * 64, encoding='utf-8')
        if os.name == 'posix':(self.root / 'token').chmod(0o600)
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'blockwire', 'run', str(path),
            '--url', self.url, '--certificate', str(self.cert),
            '--token-file', str(self.root / 'token'), '--world-id', 'fixture',
            '--player-uuid', 'player-a', '--actor-session', 'actor-a',
            '--session-id', 'subprocess', '--timeout', '5', '--json',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), 10)
        self.assertEqual(process.returncode, 0, stderr.decode())
        self.assertEqual([json.loads(line)['status'] for line in stdout.splitlines()], ['accepted', 'completed'])

    async def test_terminal_repl_modal_invalid_bcl_and_request_correlation(self):
        from blockwire.bcl.cli import repl
        # Correlation requires draining submitted requests. Explicit :quit is
        # intentionally immediate cancellation, NOT an implicit response barrier.
        # EOF exercises the documented drain contract without scheduling sleeps.
        lines = iter(['S2 sneak', 'S2 ?', 'INVALID', 'S2 ?'])
        output = []
        async def read_line(prompt):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError
        async with self.client() as client:
            self.assertEqual(await repl(client, read_line, output.append), 1)
        replies = [r for r in output if r.get('type') == 'response']
        self.assertEqual([r['request_id'] for r in replies], [1, 2, 3, 4])
        self.assertEqual(replies[2]['status'], 'failed')
        self.assertEqual(replies[1]['outputs'][0]['value'], 'sneak')
        self.assertEqual(replies[3]['outputs'][0]['value'], 'sneak')

    async def test_BW01_single_multiline_settings_and_direction(self):
        async with self.client() as client:
            r=await client.send('S0 sync\nS1 absolute\nS2 normal\nS0\nS1\nS2\nS0 ?\nS1 ?\nS2 ?')
            self.assertEqual([o['value'] for o in r['outputs'][-3:]],['async','relative','fast'])
            r=await client.send('E100 player.position 1 2 3')
            self.assertEqual(r['diagnostics'][0]['code'],'DIRECTION_DENIED')
            r=await client.send('S0 sync\nI0')
            self.assertEqual(r['status'],'completed');self.assertEqual(r['result']['operations'][0]['output']['inventory'],{})
    async def test_BW02_events_queries_unsubscribe_and_connection_correlation(self):
        async with self.client() as client:
            subscribed=await client.send('E0 player.health\nE0 player.position\nE2')
            self.assertEqual(subscribed['outputs'][-1]['subscriptions'],['player.health','player.position'])
            events=[await asyncio.wait_for(client.events.get(),2.) for _ in range(2)]
            self.assertEqual({e['event_type'] for e in events},{'player.health','player.position'})
            self.assertTrue(all(e['type']=='event' and e['direction']=='server_to_client' and e['session_id']=='session' for e in events))
            self.assertNotEqual(events[0]['sequence'],events[1]['sequence'])
            await client.send('E1 player.health\nE3');self.native.health=18.
            with self.assertRaises(asyncio.TimeoutError):await asyncio.wait_for(client.events.get(),.7)
    async def test_BW03_async_does_not_parallelize_actions_and_cancel_stays_responsive(self):
        async with self.client() as client:
            start=time.monotonic();a=await client.send('S0 async\nE0 command.completed\ntest:I0')
            self.assertLess(time.monotonic()-start,.5);self.assertEqual(a['status'],'accepted')
            b=await client.send('test:I0');await client.send('S2 sneak\nS2 ?')
            await asyncio.sleep(.1);self.assertEqual(self.starts,1)
            await client.cancel(b['task_id']);await client.cancel(a['task_id'])
            results=await asyncio.gather(client.wait(a['task_id']),client.wait(b['task_id']))
            self.assertTrue(all(r['status']=='cancelled' for r in results),results)
            self.assertEqual(self.starts,1)
    async def test_BW04_reconnect_deduplicates_cycles_and_preserves_modals(self):
        async with self.client() as client:
            first=await client.send('S0',request_id=1);self.assertEqual(first['modal']['execution_mode'],'async')
        await self.disconnected()
        async with self.client() as client:
            duplicate=await client.send('S0',request_id=1)
            self.assertTrue(duplicate['deduplicated']);self.assertEqual(duplicate['modal']['execution_mode'],'async')
            conflict=await client.send('S2',request_id=2)
            self.assertEqual(conflict['outputs'][0]['value'],'fast')
    async def test_BW10_s1_home_persists_across_frames_reconnect_and_request_dedup(self):
        async with self.client() as client:
            homed=await client.send('S1 relative',request_id=1)
            self.assertEqual(homed['status'],'completed')
            context=homed['coordinate_context']
            self.assertEqual(context['status'],'ready');self.assertEqual(context['home_position'],[.5,64.,.5])
            query=await client.send('S1 status',request_id=2)
            self.assertEqual(query['outputs'][0]['coordinate_context'],context)
        await self.disconnected()
        async with self.client() as client:
            self.assertEqual(client.coordinate_context,context)
            duplicate=await client.send('S1 relative',request_id=1)
            self.assertTrue(duplicate['deduplicated']);self.assertEqual(duplicate['coordinate_context'],context)
            self.assertEqual(client.coordinate_context,context)

    async def test_BW11_observer_homing_rechecks_actor_identity_before_capture(self):
        sid='observer-actor-fence'
        async with self.client(sid,role='observer') as client:
            self.native.actor='actor-b'
            with self.assertRaises(ConnectionError):await client.send('S1 relative',request_id=1)
        await self.disconnected(sid);self.native.actor='actor-a'
        async with self.client(sid,role='observer') as client:
            self.assertEqual(client.coordinate_context['mode'],'absolute')
            duplicate=await client.send('S1 relative',request_id=1)
            self.assertTrue(duplicate['deduplicated']);self.assertEqual(duplicate['status'],'failed')
            self.assertEqual(duplicate['diagnostics'][0]['code'],'actor_session_changed')

    async def test_BW05_connection_loss_cancels_work_never_replays_accepted_task(self):
        async with self.client() as client:
            r=await client.send('S0 async\ntest:I0',request_id=1)
            await asyncio.sleep(.1)
        await self.disconnected();starts=self.starts
        async with self.client() as client:
            duplicate=await client.send('S0 async\ntest:I0',request_id=1)
            self.assertTrue(duplicate['deduplicated']);self.assertNotEqual(duplicate['status'],'accepted')
            self.assertEqual(self.starts,starts)
    async def test_BW06_auth_certificate_hostname_and_plaintext_fail_closed(self):
        with self.assertRaises(Exception):
            async with self.client(token='b'*64):pass
        wrong=self.root/'wrong.pem';key=self.root/'wrong.key'
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-keyout',str(key),'-out',str(wrong),'-days','1','-subj','/CN=wrong.invalid'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        with self.assertRaises(Exception):
            async with self.client(cert=wrong):pass
        with self.assertRaises(Exception):
            async with connect(self.url,ssl=Bridge('a'*64,self.url,certificate=self.cert).tls_context(),server_hostname='wrong.invalid',proxy=None):pass
        with self.assertRaises(ValueError):self.client().__class__(self.url.replace('wss:','ws:'),'a'*64,self.cert,session_id='x',agent_id='a',world_id='w',player_uuid='p',actor_session='a')
        self.assertEqual(self.native.calls,[])
    async def test_BW07_bad_actor_and_unauthorized_event_cannot_bind_or_emit(self):
        with self.assertRaises(RuntimeError):
            async with self.client(player_uuid='foreign'):pass
        self.assertFalse(self.gateway.jobs.sessions)
        self.assertFalse(any(q['op']=='action' for q in self.native.calls))
    async def test_BW09_sync_waits_for_completion_without_blocking_control_messages(self):
        async with self.client() as client:
            start=time.monotonic();running=asyncio.create_task(client.send('test:I0'))
            await asyncio.sleep(.1);query_start=time.monotonic()
            query=await client.send('S0 ?')
            self.assertLess(time.monotonic()-query_start,.3);self.assertEqual(query['outputs'][0]['value'],'sync')
            result=await running;self.assertEqual(result['status'],'completed')
            self.assertGreaterEqual(time.monotonic()-start,.5)

    async def test_BW08_two_sessions_have_isolated_settings_and_subscriptions(self):
        async with self.client('a') as a,self.client('b',role='observer') as b:
            await a.send('S2 fast\nE0 player.health')
            home=await b.send('S1 relative')
            self.assertEqual(home['status'],'completed');self.assertEqual(home['coordinate_context']['home_position'],[.5,64.,.5])
            r=await b.send('S2 ?\nE2')
            self.assertEqual(r['outputs'][0]['value'],'normal');self.assertEqual(r['outputs'][1]['subscriptions'],[])
            with self.assertRaises(asyncio.TimeoutError):await asyncio.wait_for(b.events.get(),.6)
            await a.send('E3')

if __name__=='__main__':unittest.main()
