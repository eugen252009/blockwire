"""Placement outcome contracts on fake snapshots, not native collision tests."""
import math
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
                if op=='navigation':
                    point=(self.position_override or [2.5,64.,2.5]) if self.moved else [.5,64.,.5]
                    return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':'0'*32 if self.bad_nav else self.session,
                    'position':point,'health':20.,'on_fire':False,'on_ground':True,
                    'current_cell':[2,64,2] if self.moved else [0,64,0],'current_center_access':True,
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
        grounded=AutoWorld(True,True);p=Player(CallableBackend(lambda q:grounded.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def transient_grounded(*args,**kwargs):
            self.assertEqual(args[1].arrival_radius,.08)
            grounded.moved=True
            return SkillResult(status='blocked',reason='not_grounded',text='fixture transient')
        with patch('blockwire.skills.walking.walk_to',side_effect=transient_grounded) as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,64,0],'face':'south','auto_position':True,'recorded_pose':[2.5,64.,2.5]},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);move.assert_called_once();self.assertEqual(grounded.uses,1)
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

        class PartialWorld(World):
            recovered=True;position=[2.8,64.,.5]
            def call(self,op,**q):
                if op=='navigation':
                    return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,
                            'position':self.position[:],'health':20.,'on_fire':False,'on_ground':True,
                            'current_cell':[3,64,0],'current_center_access':True,
                            'source_recovered_from_partial_support':self.recovered,
                            'cells':[{'position':[3,64,0],'hazards':[]}],'edges':[]}
                value=super().call(op,**q)
                if op=='observe':
                    value.update(position=self.position[:],eye_position=[self.position[0],self.position[1]+1.62,self.position[2]])
                    value['target'].update(position=[3,63,0],face='west');value['sight_target']['position']=[3,63,0]
                    value['visible_blocks']['runs']=[[0,3,-1,0,1]]+([[1,2,-1,0,1]] if self.used else [])
                return value
        partial=PartialWorld(True,True);p=Player(CallableBackend(lambda q:partial.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        with patch('blockwire.skills.walking.walk_to') as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[3,63,0],'face':'west','auto_position':True,'recorded_pose':[2.8,64.,.5]},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);move.assert_not_called();self.assertEqual(partial.uses,1)
        inward=PartialWorld(True,True);inward.position=[2.82,64.,.5];p=Player(CallableBackend(lambda q:inward.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        with patch('blockwire.skills.walking.walk_to') as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[3,63,0],'face':'west','auto_position':True,'recorded_pose':[2.7,64.,.5]},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);move.assert_not_called();self.assertEqual(inward.uses,1)

        partial=PartialWorld(True,True);partial.recovered=False;p=Player(CallableBackend(lambda q:partial.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'support':[3,63,0],'face':'west','auto_position':True,'recorded_pose':[2.7,64.,.5]},sleeper=lambda _:None)
        self.assertEqual(result.reason,'recorded_partial_pose_not_safely_reached');self.assertEqual(partial.uses,0)
        outside=PartialWorld(True,True);outside.position=[3.4,64.,.5];p=Player(CallableBackend(lambda q:outside.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        with patch('blockwire.skills.walking.walk_to') as move:
            result=run_skill(default_registry(),p,'place_block',{'support':[3,63,0],'face':'west','auto_position':True,'recorded_pose':[2.7,64.,.5]},sleeper=lambda _:None)
        self.assertEqual(result.reason,'recorded_partial_pose_not_safely_reached');move.assert_not_called();self.assertEqual(outside.uses,0)

    def test_PL09_explicit_jump_place_uses_one_fenced_jump_and_lands_on_verified_block(self):
        class JumpWorld(World):
            def __init__(self, visible=True, consumed=True, rises=True, lands=True):
                super().__init__(visible, consumed);self.items={0:('minecraft:cobblestone',3)}
                self.position=[.5,64.,.5];self.airborne=False;self.rises=rises;self.lands=lands;self.drives=0
            def call(self,op,**q):
                if op=='drive':
                    assert q['actor_session']==self.session and q['buttons']==['jump'] and 1<=q['ticks']<=8
                    self.drives+=1
                    if self.rises:self.airborne=True;self.position=[.5,65.15,.5]
                    return {'text':'submitted'}
                if op=='action':
                    assert q['actor_session']==self.session and q['name']=='use'
                    self.uses+=1
                    if self.visible:self.used=True
                    if self.consumed:self.items[0]=('minecraft:cobblestone',2)
                    if self.lands:self.airborne=False;self.position=[.5,65.,.5]
                    return {'text':'submitted'}
                value=super().call(op,**q)
                if op=='observe':
                    value.update(position=self.position[:],eye_position=[self.position[0],self.position[1]+1.62,self.position[2]],
                        on_ground=not self.airborne,yaw=self.yaw,pitch=self.pitch,
                        target={'id':'minecraft:grass_block','position':[0,63,0],'face':'up','kind':'block'},
                        sight_target={'id':'minecraft:grass_block','position':[0,63,0]},
                        visible_blocks={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                            'palette':['minecraft:grass_block','minecraft:cobblestone'],
                            'runs':[[0,0,-1,0,1]]+([[1,0,0,0,1]] if self.used and self.visible else [])})
                return value
        n=JumpWorld();p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'block':'minecraft:cobblestone','support':[0,63,0],
            'face':'up','auto_position':True,'jump_place':True,'clear_plants':False},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);self.assertEqual(result.reason,'block_placed')
        self.assertTrue(result.details['jump_place']);self.assertEqual(n.drives,1);self.assertEqual(n.uses,1)
        self.assertEqual(n.position,[.5,65.,.5])

        n=JumpWorld(visible=False,consumed=True);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'block':'minecraft:cobblestone','support':[0,63,0],
            'face':'up','auto_position':True,'jump_place':True,'clear_plants':False},sleeper=lambda _:None)
        self.assertEqual(result.reason,'placement_not_observed');self.assertEqual(n.drives,1);self.assertEqual(n.uses,1)

        n=JumpWorld(visible=True,consumed=False);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'block':'minecraft:cobblestone','support':[0,63,0],
            'face':'up','auto_position':True,'jump_place':True,'clear_plants':False},sleeper=lambda _:None)
        self.assertEqual(result.reason,'placement_not_observed');self.assertEqual(n.drives,1);self.assertEqual(n.uses,1)

        n=JumpWorld(lands=False);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'block':'minecraft:cobblestone','support':[0,63,0],
            'face':'up','auto_position':True,'jump_place':True,'clear_plants':False},sleeper=lambda _:None)
        self.assertEqual(result.reason,'jump_place_landing_not_observed');self.assertEqual(n.uses,1)

        n=JumpWorld(rises=False);p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'block':'minecraft:cobblestone','support':[0,63,0],
            'face':'up','auto_position':True,'jump_place':True,'clear_plants':False},sleeper=lambda _:None)
        self.assertEqual(result.reason,'jump_height_not_observed');self.assertEqual(n.drives,1);self.assertEqual(n.uses,0)

        n=JumpWorld();p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'block':'minecraft:cobblestone','support':[0,63,0],
            'face':'south','auto_position':True,'jump_place':True,'clear_plants':False},sleeper=lambda _:None)
        self.assertEqual(result.reason,'jump_place_requires_up_face_and_auto_position');self.assertEqual(n.drives,0);self.assertEqual(n.uses,0)

    def test_PL11_occluded_support_allows_only_robust_recorded_edge_preposition(self):
        from unittest.mock import patch
        from blockwire.skills import SkillResult
        class OccludedWorld(World):
            def __init__(self):
                super().__init__(True,True);self.position=[1.72,64.,.5];self.moved=False;self.crouched=False
            def call(self,op,**q):
                if op=='navigation':
                    return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,
                            'position':self.position[:],'health':20.,'on_fire':False,'on_ground':True,
                            'current_cell':[1,64,0],'current_center_access':True,
                            'source_recovered_from_partial_support':self.moved,
                            'cells':[{'position':[1,64,0],'hazards':[]}],'edges':[]}
                if op=='drive':
                    assert q['actor_session']==self.session and q['buttons']==['sneak']
                    self.crouched=True;return {'text':'submitted'}
                if op=='stop':self.crouched=False
                value=super().call(op,**q)
                if op=='observe':
                    eye=[self.position[0],self.position[1]+(1.27 if self.crouched else 1.62),self.position[2]]
                    value.update(position=self.position[:],eye_position=eye,on_ground=True)
                    if self.moved:
                        value['target']={'id':'minecraft:grass_block','position':[2,60,0],'face':'up','kind':'block'}
                        value['sight_target']={'id':'minecraft:grass_block','position':[2,60,0]}
                    else:
                        value['target']={'id':'minecraft:cobblestone','position':[1,63,0],'face':'up','kind':'block'}
                        value['sight_target']={'id':'minecraft:cobblestone','position':[1,63,0]}
                    runs=[[0,1,-1,0,1]]+([[1,2,-4,0,1]] if self.moved else [])
                    if self.used:runs.append([2,2,-3,0,1])
                    value['visible_blocks']={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                        'palette':['minecraft:cobblestone','minecraft:grass_block','minecraft:crafting_table'], 'runs':runs}
                return value
        n=OccludedWorld();p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def move(*args,**kwargs):
            self.assertEqual((args[1].x,args[1].y,args[1].z),(2.01,64.,.5));self.assertEqual(args[1].arrival_radius,.08)
            n.position=[1.95,64.,.5];n.moved=True
            return SkillResult(status='succeeded',reason='fixture_arrived',text='fixture')
        with patch('blockwire.skills.walking.walk_to',side_effect=move) as movement:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,60,0],'face':'up','auto_position':True,
                'recorded_pose':[2.01,64.,.5],'recorded_sneak':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);movement.assert_called_once();self.assertEqual(n.uses,1)

        n=OccludedWorld();n.position=[1.74,64.,.5];p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        with patch('blockwire.skills.walking.walk_to') as movement:
            result=run_skill(default_registry(),p,'place_block',{'support':[2,60,0],'face':'up','auto_position':True,
                'recorded_pose':[2.23,64.,.5],'recorded_sneak':True},sleeper=lambda _:None)
        self.assertEqual(result.reason,'support_not_observed');movement.assert_not_called();self.assertEqual(n.uses,0)

    def test_PL12_exact_face_occlusion_repositions_once_before_any_use(self):
        from unittest.mock import patch
        from blockwire.skills import SkillResult
        class FaceWorld(World):
            def __init__(self):
                super().__init__(True,True);self.position=[.5,64.,1.25];self.moved=False;self.crouched=False
            def call(self,op,**q):
                if op=='navigation':
                    return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,
                            'position':self.position[:],'health':20.,'on_fire':False,'on_ground':True,
                            'current_cell':[0,64,1],'current_center_access':True,
                            'source_recovered_from_partial_support':False,
                            'cells':[{'position':[0,64,1],'hazards':[]}],'edges':[]}
                if op=='drive':self.crouched=True;return {'text':'submitted'}
                if op=='stop':self.crouched=False
                value=super().call(op,**q)
                if op=='observe':
                    value.update(position=self.position[:],eye_position=[self.position[0],self.position[1]+(1.27 if self.crouched else 1.62),self.position[2]],on_ground=True)
                    target=({'id':'minecraft:grass_block','position':[0,60,0],'face':'up','kind':'block'} if self.moved
                            else {'id':'minecraft:cobblestone','position':[0,62,1],'face':'up','kind':'block'})
                    value['target']=target;value['sight_target']={'id':target['id'],'position':target['position']}
                    value['visible_blocks']={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                        'palette':['minecraft:grass_block','minecraft:cobblestone','minecraft:crafting_table'],
                        'runs':[[0,0,-4,0,1],[1,0,-2,1,1]]+([[2,0,-3,0,1]] if self.used else [])}
                return value
        n=FaceWorld();p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def move(*args,**kwargs):
            self.assertEqual((args[1].x,args[1].z),(.5,1.01));n.position=[.5,64.,1.01];n.moved=True
            return SkillResult(status='succeeded',reason='fixture_arrived',text='fixture')
        with patch('blockwire.skills.walking.walk_to',side_effect=move) as movement:
            result=run_skill(default_registry(),p,'place_block',{'support':[0,60,0],'face':'up','auto_position':True,
                'recorded_pose':[.5,64.,1.01],'recorded_sneak':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);movement.assert_called_once();self.assertEqual(n.uses,1)

    def test_PL10_recorded_crouch_uses_actor_fenced_lease_and_observed_long_reach(self):
        class CrouchWorld(World):
            def __init__(self):super().__init__(True,True);self.crouched=False;self.drives=0;self.position=[.5,64.,.5];self.last_was_drive=False;self.crouched_at_use=False;self.post_use_drives=0;self.stops=0
            def call(self,op,**q):
                if op=='drive':
                    assert q['actor_session']==self.session and q['buttons']==['sneak'] and 1<=q['ticks']<=8
                    self.crouched=True;self.drives+=1;self.last_was_drive=True;self.post_use_drives+=int(self.used);return {'text':'submitted'}
                if op=='stop':
                    self.crouched=False;self.last_was_drive=False;self.stops+=1
                if op=='observe':self.last_was_drive=False
                if op=='action':self.crouched_at_use=self.last_was_drive
                if op=='navigation':
                    return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,
                            'position':self.position[:],'health':20.,'on_fire':False,'on_ground':True,
                            'current_cell':[math.floor(self.position[0]),64,math.floor(self.position[2])],'current_center_access':True,
                            'source_recovered_from_partial_support':False,
                            'cells':[{'position':[0,64,0],'hazards':[]}],'edges':[]}
                value=super().call(op,**q)
                if op=='observe':
                    eye=[self.position[0],self.position[1]+(1.27 if self.crouched else 1.62),self.position[2]]
                    value.update(position=self.position[:],eye_position=eye,on_ground=True,
                        target={'id':'minecraft:grass_block','position':[0,60,0],'face':'up','kind':'block'},
                        sight_target={'id':'minecraft:grass_block','position':[0,60,0]},
                        visible_blocks={'encoding':'palette_x_runs_v1','origin':[0,64,0],
                            'palette':['minecraft:grass_block','minecraft:crafting_table'],
                            'runs':[[0,0,-4,0,1]]+([[1,0,-3,0,1]] if self.used else [])})
                return value
        n=CrouchWorld();p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'support':[0,60,0],'face':'up','auto_position':True,
            'recorded_pose':[.5,64.,.5],'recorded_sneak':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);self.assertEqual(n.uses,1);self.assertGreaterEqual(n.drives,2);self.assertTrue(n.crouched_at_use)
        self.assertFalse(n.crouched);self.assertEqual(result.cleanup,'released')

        import threading
        from blockwire.skills.core import SkillContext
        from blockwire.skills.item_actions import PlaceBlock,place_block
        n=CrouchWorld();p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        context=SkillContext(p,threading.Event(),100.,lambda _:None,lambda:0.,lambda _:None)
        preserved=place_block(context,PlaceBlock(support=[0,60,0],face='up',auto_position=True,
            recorded_pose=[.5,64.,.5],recorded_sneak=True),expected_session=n.session,preserve_recorded_sneak=True)
        self.assertEqual(preserved.status,'succeeded');self.assertTrue(n.crouched);self.assertGreaterEqual(n.post_use_drives,3);self.assertEqual(n.stops,0)
        p.stop();self.assertFalse(n.crouched)

        n=CrouchWorld();n.position=[.05,64.,.5];p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'support':[0,60,0],'face':'up','auto_position':True,
            'recorded_pose':[-.234,64.,.5],'recorded_sneak':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);self.assertEqual(n.uses,1)

        n=CrouchWorld();n.position=[.765,64.,.841];p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'support':[0,60,0],'face':'up','auto_position':True,
            'recorded_pose':[.690,64.,1.089],'recorded_sneak':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);self.assertEqual(n.uses,1)

        n=CrouchWorld();p=Player(CallableBackend(lambda q:n.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        result=run_skill(default_registry(),p,'place_block',{'support':[0,60,0],'face':'up','auto_position':True,
            'recorded_pose':[.5,64.,.5]},sleeper=lambda _:None)
        self.assertEqual(result.status,'blocked');self.assertEqual(n.uses,0);self.assertEqual(n.drives,0)

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
