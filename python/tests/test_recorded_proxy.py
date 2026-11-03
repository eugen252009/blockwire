"""Recorded-pose region contracts on fake native snapshots, not Minecraft acceptance."""
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from blockwire import CallableBackend, Player
from blockwire.skills import SkillResult, default_registry, run_skill
from blockwire.skills.core import SkillStop
from blockwire.skills.item_actions import _recorded_proxy_preposition, _safe_partial_recorded_pose
from test_placement import World


class ProxyWorld(World):
    def __init__(self, *, visible=True, consumed=True):
        super().__init__(visible, consumed)
        self.position=[.5,64.,-.03]
        self.crouched=False
        self.after_walk=False
        self.before_nav={}
        self.after_nav={}

    def call(self,op,**q):
        if op=='navigation':
            row={'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,
                 'position':self.position[:],'health':20.,'on_fire':False,'on_ground':True,
                 'horizontal_speed':0.,'current_cell':[0,64,0],'current_center_access':True,
                 'source_recovered_from_partial_support':True,
                 'cells':[{'position':[0,64,0],'hazards':[]}],'edges':[]}
            row.update(self.after_nav if self.after_walk else self.before_nav)
            return row
        if op=='drive':
            assert q['actor_session']==self.session and q['buttons']==['sneak'] and q['ticks']==8
            self.crouched=True
            return {'text':'submitted'}
        if op=='stop':self.crouched=False
        row=super().call(op,**q)
        if op=='observe':
            row.update(position=self.position[:],eye_position=[self.position[0],64.+(1.27 if self.crouched else 1.62),self.position[2]],on_ground=True,
                target={'kind':'block','id':'minecraft:grass_block','position':[0,63,0],'face':'north'},
                sight_target={'id':'minecraft:grass_block','position':[0,63,0]},
                visible_blocks={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                    'palette':['minecraft:grass_block','minecraft:crafting_table'],
                    'runs':[[0,0,-1,0,1]]+([[1,0,-1,-1,1]] if self.used and self.visible else [])})
        return row


class RecordedProxyContracts(unittest.TestCase):
    goal={'support':[0,63,0],'face':'north','auto_position':True,
          'recorded_pose':[.5,64.,-.2995],'recorded_aim':[.5,63.8,0.],'recorded_sneak':True,'clear_plants':False}

    def perform(self,world,*,receipt_only=False,**goal):
        player=Player(CallableBackend(lambda q:world.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def walk(context,target,**kwargs):
            self.assertEqual(kwargs['expected_session'],world.session)
            self.assertEqual(target.arrival_radius,.08)
            self.assertTrue(target.sneak)
            self.assertEqual(target.movement,'sneak')
            point=[target.x,target.y,target.z]
            self.assertEqual(point[:2],[.5,64.])
            self.assertGreater(point[2],self.goal['recorded_pose'][2])
            self.assertGreater(math.dist(point,world.position),.08)
            self.assertGreaterEqual(point[2]+.3,.08)
            world.after_walk=True
            if not receipt_only:world.position=[point[0],point[1],point[2]+.005]
            return SkillResult(status='succeeded',reason='arrived',text='Simulated settled .08-radius arrival, not native acceptance.')
        with patch('blockwire.skills.walking.walk_to',side_effect=walk) as moved:
            result=run_skill(default_registry(),player,'place_block',{**self.goal,**goal},sleeper=lambda _:None)
        return result,moved

    def test_PR01_unsafe_exact_hint_refines_only_the_existing_admissible_proxy_region(self):
        world=ProxyWorld()
        self.assertFalse(_safe_partial_recorded_pose(world.call('navigation'),world.call('observe'),self.goal['recorded_pose']))
        result,moved=self.perform(world)
        self.assertEqual(result.status,'succeeded',result)
        self.assertEqual(result.reason,'block_placed')
        self.assertEqual(result.details['position'],[0,63,-1])
        moved.assert_called_once()
        self.assertEqual(world.uses,1)
        self.assertGreater(math.dist(world.position,self.goal['recorded_pose']),.1)
        self.assertLessEqual(math.dist(world.position,self.goal['recorded_pose']),.35)
        self.assertTrue(_safe_partial_recorded_pose(world.call('navigation'),world.call('observe'),world.position))

    def test_PR02_walking_receipt_without_admissible_arrival_never_submits_use(self):
        world=ProxyWorld();result,moved=self.perform(world,receipt_only=True)
        self.assertEqual(result.reason,'recorded_partial_pose_not_safely_reached')
        moved.assert_called_once();self.assertEqual(world.uses,0)

    def test_PR03_fresh_actor_guard_precedes_any_placement_use(self):
        world=ProxyWorld();world.after_nav={'actor_session':'f'*32}
        result,moved=self.perform(world)
        self.assertEqual(result.reason,'actor_session_changed')
        moved.assert_called_once();self.assertEqual(world.uses,0)

    def test_PR04_fresh_grounding_settlement_and_source_authority_are_required(self):
        for change in ({'on_ground':False},{'horizontal_speed':.00401},
                       {'source_recovered_from_partial_support':False},{'current_center_access':False},
                       {'position':[.5,64.,.5]}):
            with self.subTest(change=change):
                world=ProxyWorld();world.after_nav=change
                result,moved=self.perform(world)
                self.assertEqual(result.reason,'recorded_partial_pose_not_safely_reached')
                moved.assert_called_once();self.assertEqual(world.uses,0)

    def test_PR05_no_new_input_mode_or_unsafe_start_is_authorized(self):
        for change in ({'on_ground':False},{'horizontal_speed':.00401},
                       {'source_recovered_from_partial_support':False},{'current_center_access':False},
                       {'position':[.5,64.,.5]},
                       {'cells':[{'position':[0,64,0],'hazards':['lava']}]}, {'ready':False}):
            with self.subTest(change=change):
                world=ProxyWorld();world.before_nav=change
                result,moved=self.perform(world)
                self.assertNotEqual(result.status,'succeeded')
                moved.assert_not_called();self.assertEqual(world.uses,0)
        world=ProxyWorld();result,moved=self.perform(world,recorded_sneak=False)
        self.assertNotEqual(result.status,'succeeded');moved.assert_not_called();self.assertEqual(world.uses,0)

    def test_PR06_one_use_still_requires_exact_observation_and_one_item_consumption(self):
        for visible,consumed in ((False,True),(True,False)):
            with self.subTest(visible=visible,consumed=consumed):
                world=ProxyWorld(visible=visible,consumed=consumed);result,moved=self.perform(world)
                self.assertEqual(result.reason,'placement_not_observed')
                moved.assert_called_once();self.assertEqual(world.uses,1)

    @staticmethod
    def pure_fixture(position=None):
        point=position or [.5,64.,-.03]
        scene={'position':point[:],'on_ground':True}
        nav={'position':point[:],'on_ground':True,'ready':True,'horizontal_speed':0.,
             'current_cell':[0,64,0],'current_center_access':True,'source_recovered_from_partial_support':True,
             'cells':[{'position':[0,64,0],'hazards':[]}]}
        return scene,nav

    def test_PR07_proxy_bound_and_shared_support_axis_are_not_relaxed(self):
        context=SimpleNamespace(check=lambda:None);scene,nav=self.pure_fixture([.5,64.,.1])
        self.assertIsNone(_recorded_proxy_preposition(context,nav,scene,self.goal['recorded_pose'],{(0,64,0)},lambda p:True,lambda p:1.))
        scene,nav=self.pure_fixture([-.049,64.,-.21])
        selected=_recorded_proxy_preposition(context,nav,scene,[-.21,64.,-.049],{(0,64,0)},lambda p:True,lambda p:1.)
        self.assertIsNotNone(selected)
        def contact(p,i):return max(0.,min(p[i]+.3,1.)-max(p[i]-.3,0.))
        self.assertTrue(any(min(contact(scene['position'],i),contact(selected,i))>=.25 for i in (0,2)))

    def test_PR08_candidate_loop_checks_cancellation_and_deadline_before_movement(self):
        scene,nav=self.pure_fixture()
        for status,reason in (('cancelled','cancel_requested'),('timed_out','deadline_exceeded')):
            checks=[]
            def check():
                checks.append(True)
                if len(checks)==3:raise SkillStop(status,reason)
            with self.assertRaises(SkillStop):
                _recorded_proxy_preposition(SimpleNamespace(check=check),nav,scene,self.goal['recorded_pose'],{(0,64,0)},lambda p:True,lambda p:1.)
            self.assertEqual(len(checks),3)

    def test_PR09_reflections_and_quarter_turns_preserve_the_same_admissible_region(self):
        context=SimpleNamespace(check=lambda:None);scene,nav=self.pure_fixture()
        def usable(p):return -p[2]>.05 and math.dist((p[0],p[1]+1.27,p[2]),self.goal['recorded_aim'])<=4.5
        def clearance(p):return min(-p[2]-.05,4.5-math.dist((p[0],p[1]+1.27,p[2]),self.goal['recorded_aim']))
        original=_recorded_proxy_preposition(context,nav,scene,self.goal['recorded_pose'],{(0,64,0)},usable,clearance)
        self.assertIsNotNone(original)
        for mirror in (False,True):
            for turns in range(4):
                with self.subTest(mirror=mirror,turns=turns):
                    def transform(p):
                        x,y,z=p;z=1-z if mirror else z;dx,dz=x-7.5,z+2.5
                        for _ in range(turns):dx,dz=-dz,dx
                        return [7.5+dx,y,-2.5+dz]
                    center=transform([.5,64.,.5]);cell=(math.floor(center[0]),64,math.floor(center[2]))
                    transformed=transform(scene['position']);other_scene={'position':transformed,'on_ground':True}
                    other_nav={**nav,'position':transformed,'current_cell':list(cell),'cells':[{'position':list(cell),'hazards':[]}]}
                    aim=transform(self.goal['recorded_aim']);normal=[0.,0.,1. if mirror else -1.]
                    for _ in range(turns):normal[0],normal[2]=-normal[2],normal[0]
                    def other_usable(p):
                        eye=[p[0],p[1]+1.27,p[2]]
                        return sum((eye[i]-aim[i])*normal[i] for i in range(3))>.05 and math.dist(eye,aim)<=4.5
                    def other_clearance(p):
                        eye=[p[0],p[1]+1.27,p[2]]
                        return min(sum((eye[i]-aim[i])*normal[i] for i in range(3))-.05,4.5-math.dist(eye,aim))
                    selected=_recorded_proxy_preposition(context,other_nav,other_scene,transform(self.goal['recorded_pose']),{cell},other_usable,other_clearance)
                    self.assertIsNotNone(selected)
                    for a,b in zip(selected,transform(original)):self.assertAlmostEqual(a,b,places=12)


if __name__=='__main__':unittest.main()
