"""Mechanical proof acquisition contracts on simulated snapshots, NOT gameplay."""
import tempfile,unittest
from pathlib import Path
from blockwire.projects import ProjectJournal
from blockwire.project_inspection import inspect_project
from test_projects import IDENTITY,GOAL,scene_fixture,plan_fixture

class InspectionContracts(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,*,budget=16,wrong=False):
        with tempfile.TemporaryDirectory() as temp:
            with ProjectJournal(Path(temp)/'p.sqlite',IDENTITY,'p',GOAL) as p:
                p.bind(scene_fixture());p.revise(plan_fixture());p.p['observed_unfulfilled']={'-1,64,-1':'minecraft:dirt'}
                sources=[];visible=[False]
                async def exchange(source):
                    sources.append(source)
                    self.assertTrue(all(line.split()[0] in {'V0','V2','M0'} for line in source.splitlines()))
                    if 'V2 X0.5 Y66.0 Z0.5' in source:visible[0]=True
                    s=scene_fixture();s['eye_position']=[.5,65.62,.5]
                    if wrong:s['visible_blocks']['palette']=['minecraft:stone']
                    elif not visible[0]:s['visible_blocks']['runs']=[r for r in s['visible_blocks']['runs'] if r[1:4]!=[0,66,0]]
                    p.observe(s)
                    return {'status':'completed','result':{'operations':[{'command':'core:view.observe','output':s}]}}
                result=await inspect_project(p,exchange,max_operations=budget)
                return result,sources,p.summary()
    async def test_IN01_face_centre_acquisition_not_cube_centre_assumption(self):
        result,sources,summary=await self.exercise()
        self.assertTrue(result['verified']);self.assertEqual(result['operations'],3)
        self.assertIn('V2 X0.5 Y66.0 Z0.5\nV0',sources);self.assertEqual(summary['status'],'OBJECTIVE_VERIFIED')
    async def test_IN02_real_mismatch_returns_to_external_planner_without_actions(self):
        result,sources,_=await self.exercise(wrong=True)
        self.assertFalse(result['verified']);self.assertEqual(result['reason'],'observed_project_mismatch');self.assertEqual(sources,['V0'])
    async def test_IN03_inspection_cannot_exceed_native_operation_budget(self):
        result,sources,_=await self.exercise(budget=1)
        self.assertFalse(result['verified']);self.assertEqual(result['operations'],1);self.assertEqual(sources,['V0'])
    async def test_IN04_bounded_followup_preserves_active_sweep_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            with ProjectJournal(Path(temp)/'p.sqlite',IDENTITY,'p',GOAL) as p:
                p.bind(scene_fixture());p.revise(plan_fixture());p.p['observed_unfulfilled']={'-1,64,-1':'minecraft:dirt'}
                target=[0,66,0];partial=scene_fixture()
                partial['visible_blocks']['runs']=[r for r in partial['visible_blocks']['runs'] if r[1:4]!=target]
                p.begin_verification();p.observe(partial)
                self.assertTrue(p.p['final_sweep']);self.assertEqual(sum(r['status']=='correct' for r in p.p['progress'].values()),22)
                async def exchange(source):
                    self.assertEqual(source,'V0')
                    scene=scene_fixture();scene['visible_blocks']['runs']=[r for r in scene['visible_blocks']['runs'] if r[1:4]==target]
                    p.observe(scene)
                    return {'status':'completed','result':{'operations':[{'command':'core:view.observe','output':scene}]}}
                result=await inspect_project(p,exchange,max_operations=1)
                self.assertTrue(result['verified']);self.assertEqual(result['operations'],1)
                self.assertEqual(p.summary()['status'],'OBJECTIVE_VERIFIED')
    async def test_IN05_successful_sweep_restores_model_chosen_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            with ProjectJournal(Path(temp)/'p.sqlite',IDENTITY,'p',GOAL) as p:
                p.bind(scene_fixture());p.revise(plan_fixture());p.p['observed_unfulfilled']={'-1,64,-1':'minecraft:dirt'}
                target=[0,66,0];sources=[];state=['origin']
                async def exchange(source):
                    sources.append(source)
                    if source.startswith('M0 X0.5 Y64.0 Z-0.5'):state[0]='proof'
                    elif source.startswith('M0 X2.5 Y64.0 Z0.5'):state[0]='waypoint'
                    elif source.startswith('M0 X0.5 Y64.0 Z0.5'):
                        if state[0]=='proof':return {'status':'blocked','result':{'operations':[{'command':'core:movement.walk','status':'blocked','reason':'no_known_safe_route'}]}}
                        state[0]='origin'
                    scene=scene_fixture();scene['eye_position']=[.5,65.62,.5]
                    if state[0]=='proof':
                        scene['position']=[.5,64.,-.5];scene['navigation']['current_cell']=[0,64,-1]
                        scene['navigation']['cells']=[{'position':[0,64,-1],'hazards':[]},{'position':[2,64,0],'hazards':[]}];scene['navigation']['edges']=[[0,1]]
                    elif state[0]=='waypoint':
                        scene['position']=[2.5,64.,.5];scene['navigation']['current_cell']=[2,64,0]
                        scene['navigation']['cells']=[{'position':[2,64,0],'hazards':[]},{'position':[0,64,0],'hazards':[]}];scene['navigation']['edges']=[[0,1]]
                    else:scene['visible_blocks']['runs']=[r for r in scene['visible_blocks']['runs'] if r[1:4]!=target]
                    p.observe(scene)
                    return {'status':'completed','result':{'operations':[{'command':'core:view.observe','output':scene}]}}
                result=await inspect_project(p,exchange,max_operations=16)
                self.assertTrue(result['verified']);self.assertTrue(result['origin_restored'])
                self.assertEqual(sources[-2:],["M0 X2.5 Y64.0 Z0.5\nV0","M0 X0.5 Y64.0 Z0.5\nV0"])
                self.assertEqual(p.p['navigation']['value']['current_cell'],[0,64,0])

if __name__=='__main__':unittest.main()
