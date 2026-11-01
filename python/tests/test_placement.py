"""Placement outcome contracts on fake snapshots, not native collision tests."""
import unittest
from blockwire import CallableBackend, Player
from blockwire.skills import default_registry, run_skill
from test_crafting import CraftNative


class World(CraftNative):
    def __init__(self, visible, consumed):
        super().__init__({0:('minecraft:crafting_table',1)})
        self.visible, self.consumed, self.used = visible, consumed, False
        self.yaw, self.pitch, self.uses = -90., 0., 0
    def call(self, op, **q):
        if op == 'look':
            assert q['actor_session'] == self.session
            self.yaw,self.pitch=q['yaw'],q['pitch'];return {}
        if op == 'action':
            assert q['actor_session'] == self.session and q['name']=='use'
            self.used=True;self.uses+=1
            if self.consumed:self.items.clear()
            return {'text':'submitted'}
        value=super().call(op,**q)
        if op=='observe':
            value.update(position=[.5,64.,.5],eye_position=[.5,65.62,.5],yaw=self.yaw,pitch=self.pitch,
                visibility={'profile':'sampled_surfaces_v1'},
                target={'id':'minecraft:grass_block','position':[2,63,0],'face':'up','kind':'block'},
                sight_target={'id':'minecraft:grass_block','position':[2,63,0]},
                visible_blocks={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                    'palette':['minecraft:grass_block','minecraft:crafting_table'],
                    'runs':[[0,2,-1,0,1]]+([[1,2,0,0,1]] if self.used and self.visible else [])})
        return value


class PlacementContracts(unittest.TestCase):
    def test_PL08_pose_interval_not_only_centre_respects_native_reach(self):
        import math
        from unittest.mock import patch
        from blockwire.skills import SkillResult
        class RangeWorld(World):
            pose=[2.6269,64.,2.5503]
            def call(self,op,**q):
                if op=='navigation':return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,
                    'current_cell':[2,64,2],'current_center_access':True,'cells':[{'position':[2,64,2],'hazards':[]}],'edges':[]}
                v=super().call(op,**q)
                if op=='observe':
                    v.update(position=self.pose[:],eye_position=[self.pose[0],65.62,self.pose[2]])
                    v['target'].update(id='minecraft:cobblestone',position=[0,64,0],face='up');v['sight_target'].update(id='minecraft:cobblestone',position=[0,64,0])
                    v['visible_blocks'].update(palette=['minecraft:cobblestone','minecraft:crafting_table'],runs=[[0,0,0,0,1]]+([[1,0,1,0,1]] if self.used else []))
                return v
        n=RangeWorld(True,True);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def walk(context,goal,**kwargs):
            self.assertLessEqual(math.dist((goal.x,65.62,goal.z),(.5,65.,.5)),2.8)
            dx,dz=goal.x-.5,goal.z-.5;length=math.hypot(dx,dz)
            n.pose=[goal.x+.15*dx/length,64.,goal.z+.15*dz/length]
            return SkillResult(status='succeeded',reason='fixture_arrived',text='simulated arrival interval')
        with patch('blockwire.skills.walking.walk_to',side_effect=walk):
            r=run_skill(default_registry(),p,'place_block',{'support':[0,64,0],'auto_position':True},sleeper=lambda _:None)
        self.assertEqual(r.status,'succeeded',r);self.assertEqual(n.uses,1)

    def test_PL07_small_flower_clearance_requires_observed_ground_before_use(self):
        class FlowerWorld(World):
            cleared=False;attacks=0
            def call(self,op,**q):
                if op=='action' and q['name']=='attack':
                    self.assert_actor=q['actor_session'];self.attacks+=1;self.cleared=self.visible;return {'text':'submitted'}
                v=super().call(op,**q)
                if op=='observe' and not self.cleared:
                    v['target']={'kind':'block','id':'minecraft:lily_of_the_valley','position':[2,64,0],'face':'south'}
                    v['sight_target']={'id':'minecraft:lily_of_the_valley','position':[2,64,0]}
                return v
        for clears in (True,False):
            n=FlowerWorld(clears,True);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
            r=run_skill(default_registry(),p,'place_block',{'support':[2,63,0]},sleeper=lambda _:None)
            self.assertEqual(r.status,'succeeded' if clears else 'blocked',r);self.assertEqual(n.attacks,1);self.assertEqual(n.uses,1 if clears else 0)
            self.assertEqual(n.assert_actor,n.session)

    def test_PL06_full_cube_planks_use_the_same_verified_native_path(self):
        class PlankWorld(World):
            def call(self,op,**q):
                v=super().call(op,**q)
                if op=='observe':v['visible_blocks']['palette'][1]='minecraft:oak_planks'
                return v
        n=PlankWorld(True,True);n.items={0:('minecraft:oak_planks',1)}
        p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        r=run_skill(default_registry(),p,'place_block',{'block':'minecraft:oak_planks','support':[2,63,0]},sleeper=lambda _:None)
        self.assertEqual(r.status,'succeeded',r);self.assertEqual(n.uses,1)

    def test_PL05_fresh_existing_destination_is_idempotent_without_item_or_use(self):
        n=World(True,True);n.used=True;n.items.clear()
        p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        r=run_skill(default_registry(),p,'place_block',{'support':[2,63,0]},sleeper=lambda _:None)
        self.assertEqual(r.status,'succeeded',r);self.assertEqual(r.reason,'desired_block_already_observed');self.assertEqual(n.uses,0)
        self.assertEqual(r.details['consumed'],0)

    def test_PL02_replaceable_plant_still_needs_exact_destination_and_outcome(self):
        class PlantWorld(World):
            def call(self,op,**q):
                v=super().call(op,**q)
                if op=='observe' and not (self.used and self.visible):
                    v['target']={'kind':'block','id':'minecraft:leaf_litter','position':[2,64,0],'face':'north'}
                    v['sight_target']={'id':'minecraft:leaf_litter','position':[2,64,0]}
                return v
        for visible in (True,False):
            n=PlantWorld(visible,True)
            p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
            r=run_skill(default_registry(),p,'place_block',{'support':[2,63,0]},sleeper=lambda _:None)
            self.assertEqual(r.status,'succeeded' if visible else 'blocked',r)
            self.assertEqual(n.uses,1)

    def test_PL03_face_destination_and_exact_face_are_required(self):
        offsets={'up':(0,1,0),'down':(0,-1,0),'north':(0,0,-1),'south':(0,0,1),'east':(1,0,0),'west':(-1,0,0)}
        for face,offset in offsets.items():
            class FaceWorld(World):
                def call(self,op,**q):
                    v=super().call(op,**q)
                    if op=='observe':
                        v['target'].update(position=[2,64,0],face=face);v['sight_target']['position']=[2,64,0]
                        v['visible_blocks']['runs']=[[0,2,0,0,1]]+([[1,2+offset[0],offset[1],offset[2],1]] if self.used else [])
                    return v
            n=FaceWorld(True,True);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
            result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':face},sleeper=lambda _:None)
            self.assertEqual(result.status,'succeeded',result)
            self.assertEqual(result.details['position'],[2+offset[0],64+offset[1],offset[2]])
            self.assertEqual(n.uses,1)

    def test_PL04_optional_pose_uses_known_geometry_and_same_postcondition(self):
        from unittest.mock import patch
        from blockwire.skills import SkillResult
        class AutoWorld(World):
            moved=False;bad_nav=False;no_edge=False;position_override=None
            def call(self,op,**q):
                if op=='navigation':return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':'0'*32 if self.bad_nav else self.session,'current_cell':[2,64,2] if self.moved else [0,64,0],'current_center_access':True,
                    'cells':[{'position':[0,64,0],'hazards':[]},{'position':[2,64,2],'hazards':[]}],'edges':[] if self.no_edge else [[0,1]]}
                v=super().call(op,**q)
                if op=='observe':
                    if self.moved:
                        point=self.position_override or [2.5,64.,2.5]
                        v.update(position=point,eye_position=[point[0],65.62,point[2]])
                    v['target'].update(position=[2,64,0],face='south');v['sight_target']['position']=[2,64,0]
                    v['visible_blocks']['runs']=[[0,2,0,0,1]]+([[1,2,0,1,1]] if self.used else [])
                return v
        n=AutoWorld(True,True);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def walk(*args,**kwargs):
            self.assertEqual(kwargs['expected_session'],n.session)
            self.assertEqual(args[1].arrival_radius,.15)
            n.moved=True
            return SkillResult(status='succeeded',reason='fixture_arrived',text='fixture')
        with patch('blockwire.skills.walking.walk_to',side_effect=walk) as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':'south','auto_position':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);self.assertEqual(result.details['position'],[2,64,1]);self.assertEqual(n.uses,1)
        self.assertTrue(move.called)
        valid=AutoWorld(True,True);valid.moved=True;p=Player(CallableBackend(lambda q:valid.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        with patch('blockwire.skills.walking.walk_to') as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':'south','auto_position':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);move.assert_not_called()
        offcenter=AutoWorld(True,True);offcenter.moved=True;offcenter.position_override=[2.5,64.,2.62]
        p=Player(CallableBackend(lambda q:offcenter.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        points=[]
        def recenter(*args,**kwargs):
            points.append((args[1].x,args[1].z));offcenter.position_override=None
            return SkillResult(status='succeeded',reason='fixture_arrived',text='fixture')
        with patch('blockwire.skills.walking.walk_to',side_effect=recenter) as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':'south','auto_position':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);move.assert_called_once();self.assertEqual(points,[(2.5,2.62)])
        biased=AutoWorld(True,True);biased.moved=True;biased.position_override=[2.62,64.,2.38]
        p=Player(CallableBackend(lambda q:biased.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        points=[]
        def prefer_center(*args,**kwargs):
            points.append((args[1].x,args[1].z));biased.position_override=None
            return SkillResult(status='succeeded',reason='fixture_arrived',text='fixture')
        with patch('blockwire.skills.walking.walk_to',side_effect=prefer_center) as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':'south','auto_position':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);move.assert_called_once();self.assertEqual(points,[(2.5,2.62)])
        stale=AutoWorld(True,True);stale.bad_nav=True;p=Player(CallableBackend(lambda q:stale.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        with patch('blockwire.skills.walking.walk_to') as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':'south','auto_position':True},sleeper=lambda _:None)
        self.assertEqual(result.reason,'actor_session_changed');move.assert_not_called();self.assertEqual(stale.uses,0)
        disconnected=AutoWorld(True,True);disconnected.no_edge=True;p=Player(CallableBackend(lambda q:disconnected.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':'south','auto_position':True},sleeper=lambda _:None)
        self.assertEqual(result.reason,'no_known_placement_pose');self.assertEqual(result.details['known_placement_poses'],[[2.5,64,2.5]]);self.assertEqual(disconnected.uses,0)

    def test_PL01_one_use_requires_observed_block_and_item_consumption(self):
        for visible,consumed in [(False,False),(True,False),(False,True),(True,True)]:
            with self.subTest(visible=visible,consumed=consumed):
                n=World(visible,consumed)
                p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
                result=run_skill(default_registry(),p,'place_block',{'support':[2,63,0]},sleeper=lambda _:None)
                self.assertEqual(result.status,'succeeded' if visible and consumed else 'blocked',result)
                self.assertEqual(n.uses,1)
                self.assertEqual(result.cleanup,'released')


if __name__=='__main__':unittest.main()
