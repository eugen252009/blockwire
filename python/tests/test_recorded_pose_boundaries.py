"""Fail-closed contracts exposed by native H04 recovery diagnostics.

Synthetic geometry only: these tests preserve the existing placement boundary;
passing them does NOT mean that the recorded replay has been recovered.
"""
import math
import unittest
from unittest.mock import patch

from blockwire import CallableBackend, Player
from blockwire.skills import SkillResult, default_registry, run_skill
from blockwire.skills.item_actions import _safe_partial_recorded_pose
from test_placement import World


class BoundaryWorld(World):
    def __init__(self,kind,*,admissible=False):
        super().__init__(True,True)
        self.kind=kind;self.crouched=False;self.recovered=True;self.bad_actor=False
        self.position=([.5,64.,-.06 if admissible else -.04] if kind=='face'
                       else [1.10 if admissible else 1.04,64.,.5])
        self.support=[0,63,0] if kind=='face' else [2,60,0]
        self.face='north' if kind=='face' else 'up'
        self.destination=[0,63,-1] if kind=='face' else [2,61,0]
        self.hint=[.5,64.,-.2995] if kind=='face' else [1.2995,64.,.5]
        self.aim=[.5,63.8,0.] if kind=='face' else [2.5,61.,.5]

    def call(self,op,**q):
        if op=='navigation':
            return {'profile':'stepped_full_blocks_v1','ready':True,
                'actor_session':'f'*32 if self.bad_actor else self.session,
                'position':self.position[:],'health':20.,'on_fire':False,'on_ground':True,
                'horizontal_speed':0.,'current_cell':[0,64,0],'current_center_access':True,
                'source_recovered_from_partial_support':self.recovered,
                'cells':[{'position':[0,64,0],'hazards':[]}],'edges':[]}
        if op=='drive':
            assert q['actor_session']==self.session and q['buttons']==['sneak']
            self.crouched=True;return {'text':'submitted'}
        if op=='stop':self.crouched=False
        row=super().call(op,**q)
        if op=='observe':
            runs=[[0,self.support[0],self.support[1]-64,self.support[2],1]]
            if self.used:runs.append([1,self.destination[0],self.destination[1]-64,self.destination[2],1])
            row.update(position=self.position[:],eye_position=[self.position[0],64.+(1.27 if self.crouched else 1.62),self.position[2]],on_ground=True,
                target={'kind':'block','id':'minecraft:grass_block','position':self.support[:],'face':self.face},
                sight_target={'id':'minecraft:grass_block','position':self.support[:]},
                visible_blocks={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                    'palette':['minecraft:grass_block','minecraft:crafting_table'],'runs':runs})
        return row


class RecordedPoseBoundaryContracts(unittest.TestCase):
    def perform(self,world,*,allow_safe_preposition=False):
        player=Player(CallableBackend(lambda q:world.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def no_native_progress(context,goal,**kwargs):
            # A future legitimate refinement may choose a safe local pose; it
            # still cannot use without actual progress. Do not lock in the bug.
            self.assertEqual(kwargs['expected_session'],world.session)
            self.assertEqual(goal.arrival_radius,.08)
            p=(goal.x,goal.y,goal.z)
            contacts=[max(0.,min(p[i]+.3,1.)-max(p[i]-.3,0.)) for i in (0,2)]
            self.assertGreaterEqual(min(contacts),.08);self.assertGreaterEqual(max(contacts),.25)
            eye=(p[0],p[1]+1.27,p[2])
            self.assertLessEqual(math.dist(eye,world.aim),4.5)
            self.assertGreater(-p[2] if world.kind=='face' else eye[1]-world.aim[1],.05)
            return SkillResult(status='blocked',reason='fixture_no_safe_progress',text='No simulated/native progress; no placement authorization.')
        with patch('blockwire.skills.walking.walk_to',side_effect=no_native_progress) as moved:
            result=run_skill(default_registry(),player,'place_block',{
                'support':world.support,'face':world.face,'auto_position':True,'clear_plants':False,
                'recorded_pose':world.hint,'recorded_aim':world.aim,'recorded_sneak':True},sleeper=lambda _:None)
        if allow_safe_preposition:self.assertLessEqual(moved.call_count,1)
        else:moved.assert_not_called()
        return result

    def test_BR01_coarse_arrival_does_not_authorize_an_unsafe_placement(self):
        for kind in ('face','reach'):
            with self.subTest(kind=kind):
                world=BoundaryWorld(kind)
                self.assertLess(math.dist(world.position,world.hint),.3)
                self.assertFalse(_safe_partial_recorded_pose(world.call('navigation'),world.call('observe'),world.hint))
                result=self.perform(world,allow_safe_preposition=True)
                self.assertEqual(result.status,'blocked',result)
                self.assertIn(result.reason,('recorded_partial_pose_not_safely_reached','fixture_no_safe_progress'))
                self.assertEqual(world.uses,0)

    def test_BR02_existing_admissible_proxy_keeps_the_same_hint_and_one_verified_use(self):
        for kind in ('face','reach'):
            with self.subTest(kind=kind):
                world=BoundaryWorld(kind,admissible=True)
                self.assertFalse(_safe_partial_recorded_pose(world.call('navigation'),world.call('observe'),world.hint))
                result=self.perform(world)
                self.assertEqual(result.status,'succeeded',result)
                self.assertEqual(result.reason,'block_placed')
                self.assertEqual(result.details['position'],world.destination)
                self.assertEqual(world.uses,1)

    def test_BR03_face_and_reach_bounds_are_not_rounded_up_to_recover_replay(self):
        face=BoundaryWorld('face');face.position[2]=-.05
        self.assertIn(self.perform(face,allow_safe_preposition=True).reason,('recorded_partial_pose_not_safely_reached','fixture_no_safe_progress'))
        self.assertEqual(face.uses,0)
        reach=BoundaryWorld('reach')
        reach.position[0]=2.5-math.sqrt(4.5**2-4.27**2)-.001
        self.assertGreater(math.dist([reach.position[0],65.27,.5],reach.aim),4.5)
        self.assertIn(self.perform(reach,allow_safe_preposition=True).reason,('recorded_partial_pose_not_safely_reached','fixture_no_safe_progress'))
        self.assertEqual(reach.uses,0)

    def test_BR04_a_partial_proxy_still_requires_native_source_authority_and_actor_fencing(self):
        for bad_actor,reason in ((False,'recorded_partial_pose_not_safely_reached'),(True,'actor_session_changed')):
            world=BoundaryWorld('face',admissible=True)
            world.bad_actor=bad_actor;world.recovered=False
            self.assertEqual(self.perform(world).reason,reason)
            self.assertEqual(world.uses,0)


if __name__=='__main__':unittest.main()
