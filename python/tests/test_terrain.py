"""Stepped mesh/motor contracts, NOT Minecraft movement acceptance."""
import threading
import unittest
from blockwire.skills import default_registry, run_skill
from blockwire.skills.walking import route
from blockwire.skills.woodcutting import _standing, _support_safe


class StepPlayer:
    def __init__(self):
        self.now=0.;self.position=[.5,64.,.5];self.session='a';self.drives=[];self.stops=0
        self.stage=0;self.stuck=False;self.event=None;self.change=False;self.health=20.
    def navigation(self, *, terrain=False):
        assert terrain
        if self.change and self.stage:self.session='b'
        ready=self.stage in (0,3) or self.stuck
        return {'profile':'stepped_full_blocks_v1','actor_session':self.session,'ready':ready,
                'reason':None if ready else 'not_grounded','alive':True,'health':self.health,
                'position':self.position[:],'eye_position':[self.position[0],self.position[1]+1.62,.5],
                'current_cell':[0,64,0] if self.stage<3 else [1,65,0], 'current_center_access':True,
                'cells':[{'position':[0,64,0],'hazards':[]},{'position':[1,65,0],'hazards':[]}], 'edges':[[0,1]]}
    def observe(self):return {'in_world':True,'alive':True,'actor_session':self.session,'yaw':-90.,'pitch':0.}
    def look(self,yaw,pitch,*,actor_session,**kwargs):assert actor_session==self.session
    def drive(self,buttons,ticks,*,wait,actor_session):
        assert actor_session==self.session and ticks<=2
        self.drives.append(buttons[:])
        if self.event:self.event.set()
        if not self.stuck:
            self.stage=min(3,self.stage+1)
            self.position=([.7,64.42,.5] if self.stage==1 else [1.15,65.1,.5] if self.stage==2 else [1.35,65.,.5])
    def stop(self):self.stops+=1
    def clock(self):return self.now
    def sleep(self,n):self.now+=n


class GapPlayer(StepPlayer):
    def navigation(self,*,terrain=False):
        assert terrain
        if self.change and self.stage:self.session='b'
        ready=self.stage in (0,3) or self.stuck
        base={'profile':'stepped_full_blocks_v1','actor_session':self.session,'ready':ready,
              'reason':None if ready else 'not_grounded','alive':True,'health':self.health,'on_fire':False,'nearby_hostiles':[],
              'position':self.position[:],'velocity':[.1,.2 if not ready else 0.,0.],'horizontal_speed':0. if self.stage==3 else .1,
              'current_center_access':True}
        if ready:base.update(current_cell=[0,64,0] if self.stage<3 else [2,64,0],
            cells=[{'position':[0,64,0],'hazards':[]},{'position':[2,64,0],'hazards':[]}],edges=[[0,1]],
            transitions=[{'a':0,'b':1,'kind':'gap_jump'}])
        return base
    def drive(self,buttons,ticks,*,wait,actor_session):
        assert actor_session==self.session and 1<=ticks<=8;self.drives.append(buttons[:])
        if self.event:self.event.set()
        if self.stuck:return
        if self.stage==0 and 'jump' in buttons:self.stage=1;self.position=[.8,64.35,.5]
        elif self.stage==1:self.stage=2;self.position=[1.5,64.7,.5]
        elif self.stage==2:self.stage=3;self.position=[2.35,64.,.5]


class RunupGapPlayer(StepPlayer):
    def __init__(self,adjacent_landing=False):
        super().__init__();self.position=[.5,64.,.5];self.yaw=-45.;self.drives=[];self.adjacent_landing=adjacent_landing
    def observe(self):return {'in_world':True,'alive':True,'actor_session':self.session,'yaw':self.yaw,'pitch':0.}
    def look(self,yaw,pitch,*,actor_session,**kwargs):assert actor_session==self.session;self.yaw=yaw
    def navigation(self,*,terrain=False):
        assert terrain
        ready=self.stage in (0,2,4)
        current=((0,64,0) if self.stage==0 else (1,64,1) if self.stage==2 else
                 ((3,64,2) if self.adjacent_landing else (3,64,3)) if self.stage==4 else None)
        state={'profile':'stepped_full_blocks_v1','actor_session':self.session,'ready':ready,
               'reason':None if ready else 'not_grounded','alive':True,'health':self.health,'on_fire':False,
               'nearby_hostiles':[],'position':self.position[:],'velocity':[.1,-.3 if self.stage==3 else .2,.1],
               'horizontal_speed':0. if self.stage==4 else .14,'current_center_access':True}
        if ready:
            state.update(current_cell=list(current),cells=[{'position':[0,64,0],'hazards':[]},
                {'position':[1,64,1],'hazards':[]},{'position':[3,64,3],'hazards':[]},
                {'position':[3,64,2],'hazards':[]}],edges=[[0,1],[1,2]],
                transitions=[{'a':0,'b':1,'kind':'diagonal'},{'a':1,'b':2,'kind':'gap_jump'}])
        return state
    def drive(self,buttons,ticks,*,wait,actor_session):
        assert actor_session==self.session and not wait and 1<=ticks<=8;self.drives.append(buttons[:])
        if self.stage==0:self.stage=1;self.position=[1.2,64.5,1.2]
        elif self.stage==1:self.stage=2;self.position=[1.5,64.,1.5]
        elif self.stage==2:self.stage=3;self.position=[2.7,64.5,2.7]
        elif self.stage==3:
            self.stage=4;self.position=[3.3,64.,2.8] if self.adjacent_landing else [3.3,64.,3.3]


class TerrainContracts(unittest.TestCase):
    def run_walk(self,p,event=None):
        return run_skill(default_registry(),p,'walk_to',{'x':1.5,'y':65.,'z':.5,'terrain':True},
                         clock=p.clock,sleeper=p.sleep,cancel_event=event)
    def test_TR01_route_uses_target_y_and_never_invents_gap_edges(self):
        m=StepPlayer().navigation(terrain=True)
        self.assertEqual(route(m,(1.5,65.,.5),True),[(0,64,0),(1,65,0)])
        m['edges']=[];self.assertIsNone(route(m,(1.5,65.,.5),True))
        m['edges']=[[0,1]];m['cells'][1]['hazards']=['fire']
        self.assertIsNone(route(m,(1.5,65.,.5),True))
    def test_TR02_step_jumps_once_and_observes_native_landing(self):
        p=StepPlayer();r=self.run_walk(p)
        self.assertEqual(r.status,'succeeded',r)
        self.assertEqual(sum('jump' in b for b in p.drives),1)
        self.assertEqual(r.cleanup,'released')
    def test_TR03_stuck_step_actor_replacement_and_cancel_are_bounded(self):
        for case in ('stuck','change','cancel'):
            p=StepPlayer();e=threading.Event()
            if case=='stuck':p.stuck=True
            if case=='change':p.change=True
            if case=='cancel':p.event=e
            r=self.run_walk(p,e)
            self.assertNotEqual(r.status,'succeeded',r)
            self.assertLessEqual(len(p.drives),28)
            if case=='change':
                self.assertEqual(len(p.drives),1)
                self.assertEqual(r.reason,'actor_session_changed')
            if case=='cancel':self.assertEqual(r.status,'cancelled')
            self.assertEqual(r.cleanup,'released')
    def test_TR08_observed_short_gap_uses_one_bounded_native_jump(self):
        p=GapPlayer();r=run_skill(default_registry(),p,'walk_to',{'x':2.5,'y':64.,'z':.5,'terrain':True},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.status,'succeeded',r);self.assertTrue(any('jump' in b for b in p.drives))
        self.assertLessEqual(len(p.drives),4);self.assertEqual(r.cleanup,'released')

    def test_TR12_gap_lateral_envelope_stops_native_input(self):
        class Drift(GapPlayer):
            def drive(self,*args,**kwargs):
                super().drive(*args,**kwargs)
                if self.stage==1:self.position[2]=1.5
        p=Drift();r=run_skill(default_registry(),p,'walk_to',{'x':2.5,'y':64.,'z':.5,'terrain':True},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.reason,'gap_left_verified_envelope');self.assertEqual(len(p.drives),1);self.assertGreaterEqual(p.stops,1)

    def test_TR13_observed_adjacent_broad_gap_landing_can_replan(self):
        from blockwire.skills.core import SkillContext
        from blockwire.skills.motion import FlatMotion
        p=RunupGapPlayer(adjacent_landing=True);m=FlatMotion()
        c=SkillContext(p,threading.Event(),30.,lambda _:None,p.clock,p.sleep)
        self.assertIsNone(m.gap(c,p.navigation(terrain=True),(3,64,3),(-45.,0.),'walk',True,takeoff=(1,64,1)))
        self.assertEqual(p.stage,4);self.assertGreaterEqual(p.stops,1)

    def test_TR11_gap_actor_replacement_and_cancel_stop_before_renewal(self):
        p=GapPlayer();p.change=True;r=run_skill(default_registry(),p,'walk_to',{'x':2.5,'y':64.,'z':.5,'terrain':True},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.reason,'actor_session_changed');self.assertGreaterEqual(p.stops,1)
        p=GapPlayer();p.event=threading.Event();r=run_skill(default_registry(),p,'walk_to',{'x':2.5,'y':64.,'z':.5,'terrain':True},
            clock=p.clock,sleeper=p.sleep,cancel_event=p.event)
        self.assertEqual(r.status,'cancelled');self.assertEqual(len(p.drives),1);self.assertGreaterEqual(p.stops,1)

    def test_TR10_diagonal_gap_uses_proven_runup_and_releases_jump_before_landing(self):
        p=RunupGapPlayer();r=run_skill(default_registry(),p,'walk_to',{'x':3.5,'y':64.,'z':3.5,'terrain':True},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.status,'succeeded',r);self.assertGreaterEqual(sum('jump' in b for b in p.drives),2)
        self.assertTrue(any('forward' in b and 'jump' not in b for b in p.drives));self.assertFalse(any('sprint' in b for b in p.drives))

    def test_TR09_unannotated_long_edge_is_never_walked_as_flat_ground(self):
        class Unknown(GapPlayer):
            def navigation(self,**kw):
                state=super().navigation(**kw);state.pop('transitions',None);return state
        p=Unknown();r=run_skill(default_registry(),p,'walk_to',{'x':2.5,'y':64.,'z':.5,'terrain':True},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.reason,'unsupported_route_edge');self.assertEqual(p.drives,[])

    def test_TR06_changed_clearance_edge_is_rejected_before_jump(self):
        class Changed(StepPlayer):
            samples=0
            def navigation(self,**kw):
                m=super().navigation(**kw);self.samples+=1
                if self.samples>=2:m['edges']=[]
                return m
        p=Changed();r=self.run_walk(p)
        self.assertEqual(r.reason,'step_edge_changed')
        self.assertEqual(p.drives,[])

    def test_TR07_native_feedback_brakes_before_landing_not_after_overshoot(self):
        class Momentum(StepPlayer):
            def drive(self,buttons,ticks,**kw):
                super().drive(buttons,ticks,**kw)
                if self.stage==3 and 'forward' in buttons:self.position=[2.3,65.,.5]
        p=Momentum();r=self.run_walk(p)
        self.assertEqual(r.status,'succeeded',r)
        self.assertEqual(p.drives[-1],[])

    def test_TR05_excavation_retains_own_support_and_rejects_overlap_depth_gaps(self):
        m=StepPlayer().navigation(terrain=True)
        side=('minecraft:dirt',(1,63,0))
        self.assertFalse(_support_safe(m,side,False))
        self.assertTrue(_support_safe(m,side,True))
        self.assertFalse(_support_safe(m,('minecraft:dirt',(0,63,0)),True))
        self.assertFalse(_support_safe(m,('minecraft:dirt',(1,62,0)),True))
        self.assertFalse(_support_safe(m,('minecraft:dirt',(1,63,1)),True))
        m['position'][0]=.8
        self.assertFalse(_support_safe(m,side,True))

    def test_TR04_lower_standing_cells_not_support_mining(self):
        m=StepPlayer().navigation(terrain=True)
        self.assertIsNotNone(_standing(m,('minecraft:stone',(2,65,0))))
        self.assertIsNone(_standing(m,('minecraft:stone',(2,63,0))))


if __name__=='__main__':unittest.main()
