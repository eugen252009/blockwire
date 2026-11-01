"""Simulated decider/client contract; not real LLM or Minecraft evidence."""
import asyncio,copy,tempfile,unittest
from pathlib import Path
from blockwire.projects import ProjectJournal
from blockwire.project_agent import ProjectAgent
from blockwire.bcl import default_commands
from test_projects import IDENTITY,GOAL,scene_fixture,plan_fixture

class FakeClient:
    next_id=1;bind={'session_id':'s'}
    def __init__(self):self.sources=[];self.fail=False;self.hold=False;self.cancelled=False;self.built=False
    async def send(self,source,request_id=None):
        self.next_id=request_id+1;self.sources.append(source)
        if self.fail and 'I3' in source:raise ConnectionError('uncertain')
        if self.hold and 'I3' in source:return {'status':'accepted','task_id':'task'}
        ops=[]
        if 'I3' in source:self.built=True;ops.append({'command':'core:inventory.place','status':'succeeded','reason':'block_placed','evidence':{'position':[1,64,0],'block':'minecraft:dirt'}})
        if 'V0' in source:
            scene=scene_fixture()
            if not self.built:
                scene['visible_blocks']['runs']=[r for r in scene['visible_blocks']['runs'] if r[1:4]!=[1,64,0]]
                scene['navigation']['cells'].append({'position':[1,64,0],'hazards':[]})
            ops.append({'command':'core:view.observe','status':'succeeded','reason':'fresh_observation_provided','output':scene})
        if 'I0' in source:ops.append({'command':'core:inventory.inspect','status':'succeeded','output':{'inventory':{'minecraft:dirt':64}}})
        return {'status':'completed','request_id':request_id,'session_id':'s','result':{'operations':ops}}
    async def wait(self,task):await asyncio.Future()
    async def cancel(self,task):self.cancelled=True;return {'status':'cancelled'}

class Model:
    def __init__(self,decisions):self.decisions=iter(decisions)
    def decide(self,context):return next(self.decisions)

class ProjectAgentContracts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'p.sqlite'
    def journal(self):return ProjectJournal(self.path,IDENTITY,'p',GOAL)
    async def test_PA01_model_finish_is_not_truth_and_final_sweep_is_independent(self):
        decisions=[{'plan':plan_fixture(),'source':'V0','finish':True},{'source':'I3 Bminecraft:dirt P"[1,63,0]"'},{'source':'V0','finish':True}]
        with self.journal() as p:
            p.bind(scene_fixture());c=FakeClient();r=await ProjectAgent(c,p,Model(decisions),default_commands(),max_calls=3).run()
            self.assertEqual(r['status'],'OBJECTIVE_VERIFIED');self.assertEqual(p.p['counters']['placement_events'],1)
            self.assertTrue(any(e['kind']=='OBJECTIVE_INCOMPLETE' for e in p.p['history']))
    async def test_PA02_false_finish_and_no_progress_budget(self):
        decisions=[{'plan':plan_fixture(),'finish':True}]+[{'finish':True}]*8
        with self.journal() as p:
            p.bind(scene_fixture());r=await ProjectAgent(FakeClient(),p,Model(decisions),default_commands(),max_calls=8,max_stagnation=2).run()
            self.assertEqual(r['status'],'OBJECTIVE_INCOMPLETE');self.assertEqual(r['reason'],'no_relevant_progress_budget')
    async def test_PA03_uncertain_result_persists_intent_without_replay(self):
        c=FakeClient();c.fail=True
        with self.journal() as p:
            p.bind(scene_fixture())
            with self.assertRaises(ConnectionError):await ProjectAgent(c,p,Model([{'plan':plan_fixture(),'source':'I3 Bminecraft:dirt'}]),default_commands(),max_calls=1).run()
            self.assertTrue(p.p['pending']);self.assertEqual(sum('I3' in s for s in c.sources),1);self.assertNotEqual(p.summary()['status'],'OBJECTIVE_VERIFIED')
    async def test_PA07_verification_only_permissions_reject_whole_mutating_frame(self):
        import time
        from blockwire.bcl.compiler import BCLError
        with self.journal() as p:
            p.bind(scene_fixture());p.revise(plan_fixture());c=FakeClient()
            a=ProjectAgent(c,p,Model([]),default_commands(),permissions={'observe','movement','settings'});a.deadline=time.monotonic()+10
            with self.assertRaises(BCLError):await a.exchange('V0\nI4 Bminecraft:dirt P[1,64,0]',intent=True)
            self.assertFalse(c.sources);self.assertIsNone(p.p['pending'])

    async def test_PA06_followup_observation_does_not_hide_failed_action(self):
        class FailedClient(FakeClient):
            async def send(self,source,request_id=None):
                r=await super().send(source,request_id)
                if 'I3' in source:r.update(status='blocked',result={'operations':[{'command':'core:inventory.place','status':'blocked','reason':'exact_support_top_not_acquired','evidence':{'actual_target':{'face':'west'}}}]})
                return r
        class InspectModel(Model):
            contexts=[]
            def decide(self,context):self.contexts.append(context);return super().decide(context)
        m=InspectModel([{'plan':plan_fixture(),'source':'I3 Bminecraft:dirt'},{'finish':True}])
        with self.journal() as p:
            p.bind(scene_fixture());await ProjectAgent(FailedClient(),p,m,default_commands(),max_calls=2).run()
            self.assertEqual(m.contexts[1]['latest_result']['status'],'completed')
            self.assertEqual(m.contexts[1]['last_action_result']['status'],'blocked')
            self.assertEqual(m.contexts[1]['last_action_result']['operations'][0]['evidence']['actual_target']['face'],'west')

    async def test_PA05_material_request_budget_precedes_native_send(self):
        import time
        with self.journal() as p:
            p.bind(scene_fixture());p.revise(plan_fixture());p.p['counters']['gather_requests']=512
            c=FakeClient();a=ProjectAgent(c,p,Model([]),default_commands());a.deadline=time.monotonic()+10
            with self.assertRaises(ValueError):await a.exchange('C2 Bground_soil N1',intent=True)
            self.assertFalse(c.sources);self.assertIsNone(p.p['pending'])

    async def test_PA08_compiler_diagnostics_reach_model_and_effect_free_audit(self):
        class InspectModel(Model):
            def __init__(self,decisions):super().__init__(decisions);self.contexts=[]
            def decide(self,context):self.contexts.append(context);return super().decide(context)
        m=InspectModel([{'plan':plan_fixture(),'source':'M999'},{'finish':True}]);audit=[];c=FakeClient()
        with self.journal() as p:
            p.bind(scene_fixture());await ProjectAgent(c,p,m,default_commands(),max_calls=2,audit=audit.append).run()
            self.assertNotIn('M999',c.sources);self.assertIsNone(p.p['pending'])
            self.assertEqual(len(m.contexts[1]['last_action_result']['diagnostics']),1)
            diag=m.contexts[1]['last_action_result']['diagnostics'][0]
            self.assertEqual(diag['code'],'UNKNOWN_COMMAND');self.assertEqual(diag['phase'],'compile')
            rejected=next(x for x in audit if x['source']=='M999')
            self.assertFalse(rejected['response']['effects_started'])

    async def test_PA09_malformed_model_json_is_feedback_not_host_failure(self):
        class MalformedThenValid:
            def __init__(self):self.calls=0;self.contexts=[]
            def decide(self,context):
                self.calls+=1;self.contexts.append(context)
                if self.calls==1:raise ValueError('invalid model JSON escape')
                return {'plan':plan_fixture(),'finish':True}
        m=MalformedThenValid();c=FakeClient()
        with self.journal() as p:
            p.bind(scene_fixture());r=await ProjectAgent(c,p,m,default_commands(),max_calls=2).run()
            self.assertEqual(m.calls,2);self.assertEqual(r['status'],'OBJECTIVE_INCOMPLETE')
            self.assertEqual(m.contexts[1]['last_action_result']['status'],'rejected')
            self.assertIn('invalid model JSON escape',m.contexts[1]['last_action_result']['reason'])
            self.assertTrue(any(e['kind']=='plan_or_program_rejected' for e in p.p['history']))
    async def test_PA10_model_action_preserves_mandatory_followup_budget(self):
        class AtLimit:
            def decide(_,context):
                p.p['counters']['operations']=508
                return {'source':'M0 X0.5 Y64 Z0.5'}
        with self.journal() as p:
            p.bind(scene_fixture());p.revise(plan_fixture());c=FakeClient();a=ProjectAgent(c,p,AtLimit(),default_commands(),max_calls=1)
            r=await a.run()
            self.assertEqual(r['status'],'OBJECTIVE_INCOMPLETE');self.assertEqual(p.p['counters']['operations'],510)
            self.assertFalse(any(source.startswith('M0 ') for source in c.sources))
            self.assertTrue(any(e['kind']=='plan_or_program_rejected' for e in p.p['history']))
            await a.exchange('V0\nI0');self.assertEqual(p.p['counters']['operations'],512)
    async def test_PA12_plan_baseline_preserves_mandatory_followup_budget(self):
        class PlanAtLimit:
            def decide(_,context):
                p.p['counters']['operations']=508
                return {'plan':plan_fixture()}
        with self.journal() as p:
            p.bind(scene_fixture());c=FakeClient();a=ProjectAgent(c,p,PlanAtLimit(),default_commands(),max_calls=1)
            r=await a.run()
            self.assertEqual(r['status'],'OBJECTIVE_INCOMPLETE');self.assertEqual(p.p['counters']['operations'],510)
            self.assertEqual(c.sources.count('V0\nI0'),1)
            self.assertTrue(any(e['kind']=='plan_or_program_rejected' for e in p.p['history']))
            await a.exchange('V0\nI0');self.assertEqual(p.p['counters']['operations'],512)
    async def test_PA11_inspection_reserves_one_final_model_action(self):
        from unittest.mock import patch
        captured=[]
        class NearLimit:
            def decide(_,context):
                p.p['counters']['operations']=500
                return {'begin_verification':True}
        async def inspect(journal,exchange,*,max_operations,check):
            captured.append(max_operations);return {'verified':False,'reason':'bounded_test','operations':0,'origin_restored':True}
        with self.journal() as p:
            p.bind(scene_fixture());p.revise(plan_fixture())
            with patch('blockwire.project_inspection.inspect_project',inspect):
                await ProjectAgent(FakeClient(),p,NearLimit(),default_commands(),max_calls=1).run()
            self.assertEqual(captured,[5])
    async def test_PA14_successful_terminal_V0_I0_is_not_duplicated(self):
        with self.journal() as p:
            p.bind(scene_fixture());c=FakeClient()
            r=await ProjectAgent(c,p,Model([{'source':'V0\nI0'}]),default_commands(),max_calls=1).run()
            self.assertEqual(r['status'],'OBJECTIVE_INCOMPLETE');self.assertEqual(p.p['counters']['operations'],7)
            self.assertEqual(c.sources.count('V0\nI0'),1)
    async def test_PA13_runtime_stops_before_consuming_final_audit_reserve(self):
        class TwoDecisions:
            def __init__(self):self.calls=0
            def decide(self,context):
                self.calls+=1
                if self.calls==1:p.p['counters']['operations']=508
                return {}
        m=TwoDecisions()
        with self.journal() as p:
            p.bind(scene_fixture());a=ProjectAgent(FakeClient(),p,m,default_commands(),max_calls=2)
            r=await a.run()
            self.assertEqual(m.calls,1);self.assertEqual(r['reason'],'project_operation_budget')
            self.assertEqual(p.p['counters']['operations'],510)
            await a.exchange('V0\nI0');self.assertEqual(p.p['counters']['operations'],512)
    async def test_PA04_active_cancellation_uses_existing_gateway_cancel(self):
        c=FakeClient();c.hold=True
        with self.journal() as p:
            p.bind(scene_fixture());a=ProjectAgent(c,p,Model([{'plan':plan_fixture(),'source':'I3 Bminecraft:dirt'}]),default_commands(),max_calls=1)
            task=asyncio.create_task(a.run())
            for _ in range(100):
                if a.active:break
                await asyncio.sleep(.005)
            self.assertTrue(a.active);a.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertTrue(c.cancelled);self.assertTrue(p.p['pending'])

if __name__=='__main__':unittest.main()
