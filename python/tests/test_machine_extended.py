"""Extended session envelopes; offline doubles are NOT Minecraft acceptance."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from blockwire import machine_agent,machine_mcp
from blockwire.bcl.machine import STATE_EVENTS

class Client:
    profile='machine-v1';bind={'actor_session':'fixture-actor'}
    def __init__(self):
        self.events=asyncio.Queue();self.tasks={};self.control_state='ready';self.reader=None
        self.entered=0;self.searches=0;self.actions=0;self.interrupts=0
    async def __aenter__(self):
        self.entered+=1;self.reader=asyncio.create_task(asyncio.sleep(86400));return self
    async def __aexit__(self,*args):
        self.reader.cancel();await asyncio.gather(self.reader,return_exceptions=True)
    async def report(self,events):
        for name in STATE_EVENTS:
            self.events.put_nowait({'type':'event','event_type':name,'data':{'actor_session':self.bind['actor_session'],'value':{'actor_session':self.bind['actor_session']}}})
        return {'status':'completed'}
    async def search(self,parameters,*,check):
        check();self.searches+=1;return {'status':'blocked','reason':'SIMULATED_target_not_seen'}
    async def action(self,name,parameters):
        await asyncio.sleep(0);self.actions+=1;key=str(self.actions)
        f=asyncio.get_running_loop().create_future();f.set_result({'status':'completed'});self.tasks[key]=f
        return {'status':'accepted','task_id':key}
    async def compose(self,actions):return await self.action('compose',actions)
    async def interrupt(self):
        self.interrupts+=1;self.events.put_nowait({'type':'event','event_type':'control.released','data':{'actor_session':self.bind['actor_session'],'generation':self.interrupts}})
        return {'status':'requested','generation':self.interrupts}

class Envelope(unittest.IsolatedAsyncioTestCase):
    async def test_extended_requires_opt_in_before_directory_or_connection(self):
        for args in ({'max_decisions':101},{'max_actions':1001},{'duration':1801},
                     {'extended_run':1},{'extended_run':'yes'},
                     {'extended_run':True,'max_decisions':1001},
                     {'extended_run':True,'max_actions':1000001},
                     {'extended_run':True,'duration':86401},
                     {'extended_run':True,'duration':float('nan')},
                     {'extended_run':True,'duration':float('inf')},
                     {'extended_run':True,'max_decisions':True},
                     {'extended_run':True,'max_actions':True},
                     {'extended_run':True,'model_timeout':61}):
            with self.subTest(args=args),tempfile.TemporaryDirectory()as root:
                client=Client();directory=Path(root)/'unused'
                with self.assertRaises(ValueError):await machine_agent.run(client,None,'fixture',directory,**args)
                self.assertEqual(client.entered,0);self.assertFalse(directory.exists())
    async def test_1000_decisions_not_old_100_limit_and_searches_do_not_exhaust_generous_operations(self):
        class Model:
            def __init__(self):self.remaining=[]
            def decide(self,context):
                self.remaining.append(context['remaining_model_calls']);return {'kind':'perception','name':'search','parameters':{}}
        with tempfile.TemporaryDirectory()as root:
            directory=Path(root)/'agent';client=Client();model=Model()
            result=await machine_agent.run(client,model,'fixture',directory,extended_run=True,duration=86400,max_decisions=1000,max_actions=1000000,model_timeout=1.)
            self.assertEqual(result['model_calls'],1000);self.assertEqual(client.searches,1000)
            self.assertEqual(model.remaining,list(range(1000,0,-1)))
            self.assertEqual(result['reserved_search_pages'],34000);self.assertEqual(result['reserved_action_operations'],0)
            self.assertEqual(result['reason'],'decision_budget_exhausted');self.assertEqual(result['cleanup'],'released');self.assertFalse(result['goal_verified'])
            self.assertEqual(json.loads((directory/'limits.json').read_text()),{'extended_run':True,'duration_seconds':86400,'max_decisions':1000,'max_operations':1000000,'model_timeout_seconds':1.})
            self.assertEqual(len(list(directory.glob('*-request.json'))),1000)
            with self.assertRaisesRegex(ValueError,'Fresh empty'):await machine_agent.run(Client(),model,'fixture',directory,extended_run=True)
    async def test_extended_still_checks_deadline_after_inference_before_action(self):
        clock=[100.]
        class Model:
            def decide(self,context):clock[0]+=86401;return {'kind':'act','skill':'press','parameters':{'action':'use'}}
        with tempfile.TemporaryDirectory()as root,patch.object(machine_agent,'time',SimpleNamespace(monotonic=lambda:clock[0])):
            client=Client();result=await machine_agent.run(client,Model(),'fixture',Path(root)/'run',extended_run=True,duration=86400,max_decisions=1000,max_actions=1000000,model_timeout=1.)
        self.assertEqual(result['model_calls'],1);self.assertEqual(client.actions,0);self.assertTrue(result['no_retry']);self.assertEqual(result['cleanup'],'released')
    async def test_extended_does_not_remove_chosen_search_budget(self):
        model=SimpleNamespace(decide=lambda context:{'kind':'perception','name':'search','parameters':{}})
        with tempfile.TemporaryDirectory()as root:
            client=Client();result=await machine_agent.run(client,model,'fixture',Path(root)/'run',extended_run=True,duration=86400,max_decisions=1000,max_actions=33,model_timeout=1.)
        self.assertEqual(client.searches,0);self.assertEqual(result['reserved_search_pages'],0);self.assertEqual(result['model_calls'],1);self.assertEqual(result['cleanup'],'released')

class MCPBound(unittest.IsolatedAsyncioTestCase):
    def test_task_limit_rejects_unbounded_or_coerced_values(self):
        for value in (0,1001,True,128.,'1000'):
            with self.assertRaises(ValueError):machine_mcp.create_machine_server(Client(),max_session_tasks=value)
    async def test_default_remains_128_and_extended_lifetime_1000_is_bounded(self):
        for limit,kwargs in [(128,{}),(1000,{'max_session_tasks':1000})]:
            client=Client();server=machine_mcp.create_machine_server(client,**kwargs);tool=server._tool_manager.get_tool('press')
            for _ in range(limit):await tool.run({'action':'use'})
            self.assertEqual(client.actions,limit)
            with self.assertRaisesRegex(Exception,'history bound'):await tool.run({'action':'use'})
            with self.assertRaisesRegex(Exception,'history bound'):await server._tool_manager.get_tool('compose').run({'actions':[{'name':'press','parameters':{'action':'use'}}]})
            self.assertEqual(client.actions,limit)
            del client.tasks['1'];missing=await server._tool_manager.get_tool('task_result').run({'task_id':'1'})
            self.assertEqual(missing['status'],'unavailable');self.assertIn('never replay',missing['reason']);self.assertEqual(client.actions,limit)
    async def test_concurrent_action_and_composition_cannot_overrun_session_bound(self):
        client=Client();server=machine_mcp.create_machine_server(client,max_session_tasks=1)
        replies=await asyncio.gather(server._tool_manager.get_tool('press').run({'action':'use'}),server._tool_manager.get_tool('compose').run({'actions':[{'name':'press','parameters':{'action':'use'}}]}),return_exceptions=True)
        self.assertEqual(client.actions,1);self.assertEqual(sum(isinstance(r,dict)for r in replies),1)
    async def test_admission_lock_never_blocks_interrupt_or_cached_status(self):
        client=Client();gate=asyncio.Event();entered=asyncio.Event();original=client.action
        async def delayed(*args):entered.set();await gate.wait();return await original(*args)
        client.action=delayed;server=machine_mcp.create_machine_server(client,max_session_tasks=1000)
        task=asyncio.create_task(server._tool_manager.get_tool('press').run({'action':'use'}))
        try:
            await asyncio.wait_for(entered.wait(),1)
            reply=await asyncio.wait_for(server._tool_manager.get_tool('interrupt').run({}),.3)
            self.assertEqual(reply['status'],'requested')
            self.assertTrue((await server._tool_manager.get_tool('events').run({}))['snapshot_is_partial'])
        finally:gate.set();await task

class CLI(unittest.TestCase):
    def arguments(self,token):return ['--url','wss://127.0.0.1:8880/v1','--certificate','unused.pem','--token-file',str(token),'--session-id','s','--agent-id','a','--world-id','w','--player-uuid','p','--actor-session','actor']
    def test_explicit_cli_flags_are_forwarded_and_defaults_unchanged(self):
        with tempfile.TemporaryDirectory()as root:
            token=Path(root)/'token';token.write_text('a'*64);token.chmod(0o600)
            for extra,expected in [([],False),(['--extended-run','--duration','86400','--max-decisions','1000','--max-actions','1000000'],True)]:
                with patch.object(machine_agent,'BCLClient'),patch.object(machine_agent,'OpenAIToolDecider'),patch.object(machine_agent,'run',new=AsyncMock(return_value={'status':'stopped'}))as run,patch('builtins.print'):
                    self.assertEqual(machine_agent.main(self.arguments(token)+['--llm-url','http://127.0.0.1/unused','--model','fixture','--goal','fixture','--state-directory',str(Path(root)/'agent')]+extra),0)
                    self.assertIs(run.call_args.kwargs['extended_run'],expected)
                    self.assertEqual(run.call_args.kwargs['max_decisions'],1000 if expected else 20)
            for extra,expected in [([],128),(['--max-session-tasks','1000'],1000)]:
                with patch.object(machine_mcp,'BCLClient'),patch.object(machine_mcp,'create_machine_server',return_value=SimpleNamespace(run=Mock()))as create:
                    machine_mcp.main(self.arguments(token)+extra);self.assertEqual(create.call_args.kwargs['max_session_tasks'],expected)

if __name__=='__main__':unittest.main()
