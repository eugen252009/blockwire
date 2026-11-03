"""Operation-scoped stance handoff; fake controls are not Minecraft acceptance."""
import threading
import unittest
from unittest.mock import patch
from blockwire import BridgeError, CallableBackend, Player
from blockwire.skills import SkillResult, default_registry, run_skill
from blockwire.skills.core import SkillContext, SkillStop
from blockwire.skills.motion import FlatMotion
from blockwire.skills.walking import WalkTo, walk_to
from test_skills import FlatPlayer
from test_placement import World


class PoseHandoffContracts(unittest.TestCase):
    def context(self,player):
        return SkillContext(player,threading.Event(),30.,lambda _:None,player.clock,player.sleep)

    def pulse(self,*,handoff):
        player=FlatPlayer();player.position=[3.015,64.,.52];player.cells={(3,64,0)};player.yaw=90.
        context=self.context(player);motor=FlatMotion()
        result=motor.pulse(context,player.navigation(),(2.7004,64.,.52),'sneak',view=(90.,0.),
            continuous=True,precision_sneak=False,arrival_radius=.3,preserve_edge_sneak=handoff)
        self.assertIsNone(result)
        return player,motor,context

    def test_PH01_navigation_uses_the_qualified_single_tick_and_release_without_extra_pulses(self):
        player,motor,context=self.pulse(handoff=False)
        drives=[r for r in player.calls if r[0]=='drive']
        self.assertEqual(drives,[('drive',['forward','sneak'],1)])
        self.assertFalse(motor.sneak_stance)
        self.assertEqual(player.calls[-1],('stop',))

    def test_PH02_interaction_handoff_keeps_preparation_and_independent_stance(self):
        player,motor,context=self.pulse(handoff=True)
        drives=[r for r in player.calls if r[0]=='drive']
        self.assertEqual(len(drives),3)
        self.assertEqual(drives[0][1],['sneak'])
        self.assertEqual(drives[1][1],['forward','sneak'])
        self.assertEqual(drives[1][2:],(8,{'forward':1,'sneak':8}))
        self.assertEqual(drives[2][1],['sneak'])
        self.assertTrue(motor.sneak_stance)
        motor.halt(context);self.assertFalse(motor.sneak_stance)
        self.assertEqual(player.calls[-1],('stop',))

    def test_PH03_only_precision_or_an_explicit_interaction_requests_stance_handoff(self):
        for handoff,radius,wanted in ((False,.3,False),(True,.3,True),(False,.15,True),(False,.08,True)):
            player=FlatPlayer();seen=[]
            def probe(motor,context,state,target,movement,**kwargs):
                seen.append(kwargs['pose_handoff'])
                self.assertTrue(kwargs['preserve_edge_sneak'])
                self.assertEqual(kwargs['pose_handoff'],wanted)
                self.assertEqual(kwargs['arrival_radius'],radius)
                raise SkillStop('blocked','single_feedback_probe')
            with patch('blockwire.skills.motion.FlatMotion.pulse',new=probe):
                with self.assertRaises(SkillStop):
                    walk_to(self.context(player),WalkTo(x=3.5,y=64.,z=.5,arrival_radius=radius),pose_handoff=handoff)
            self.assertEqual(seen,[wanted])
        with self.assertRaises(ValueError):
            walk_to(self.context(player),WalkTo(x=3.5,y=64.,z=.5),pose_handoff='not a policy')
        with self.assertRaises(ValueError):
            run_skill(default_registry(),player,'walk_to',{'x':3.5,'y':64.,'z':.5,'pose_handoff':True})

    def test_PH04_actor_loss_releases_retained_stance_before_any_new_direction(self):
        player,motor,context=self.pulse(handoff=True)
        before=sum(r[0]=='drive' and 'forward' in r[1] for r in player.calls)
        state={**player.navigation(),'actor_session':'replacement'}
        result=motor.pulse(context,state,(2.7004,64.,.52),'sneak',view=(90.,0.))
        self.assertEqual(result.reason,'actor_session_changed')
        self.assertFalse(motor.sneak_stance)
        self.assertEqual(sum(r[0]=='drive' and 'forward' in r[1] for r in player.calls),before)
        self.assertEqual(player.calls[-1],('stop',))

    def test_PH05_cancel_and_deadline_precede_new_input(self):
        for cancelled in (True,False):
            player=FlatPlayer();event=threading.Event()
            if cancelled:event.set()
            context=SkillContext(player,event,30. if cancelled else 0.,lambda _:None,player.clock,player.sleep)
            with self.assertRaises(SkillStop):
                FlatMotion().pulse(context,player.navigation(),(2.7004,64.,.52),'sneak',view=(90.,0.),preserve_edge_sneak=True)
            self.assertFalse(any(r[0]=='drive' for r in player.calls))

    def test_PH06_transport_loss_is_terminal_without_replaying_the_direction(self):
        class Broken(FlatPlayer):
            attempts=0
            def drive(self,buttons,ticks,**kwargs):
                if 'forward' in buttons:
                    self.attempts+=1;raise BridgeError('transport unavailable')
                return super().drive(buttons,ticks,**kwargs)
        player=Broken();player.position=[3.015,64.,.52];player.cells={(3,64,0)};player.yaw=90.
        result=run_skill(default_registry(),player,'walk_to',{'x':2.7004,'y':64.,'z':.52,'movement':'sneak','arrival_radius':.08},
            clock=player.clock,sleeper=player.sleep)
        self.assertEqual(result.status,'failed');self.assertEqual(result.reason,'transport_error')
        self.assertEqual(player.attempts,1)
        self.assertEqual(player.calls[-1],('stop',))

    def test_PH07_placement_explicitly_requests_handoff_with_the_same_observed_postcondition(self):
        class AutoWorld(World):
            moved=False;position=[.5,64.,.5]
            def call(self,op,**q):
                if op=='navigation':
                    return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,
                        'position':self.position[:],'health':20.,'on_fire':False,'on_ground':True,
                        'current_cell':[2,64,2] if self.moved else [0,64,0],'current_center_access':True,
                        'cells':[{'position':[0,64,0],'hazards':[]},{'position':[2,64,2],'hazards':[]}],'edges':[[0,1]]}
                row=super().call(op,**q)
                if op=='observe':
                    row.update(position=self.position[:],eye_position=[self.position[0],65.62,self.position[2]])
                    row['target'].update(position=[2,64,0],face='south');row['sight_target']['position']=[2,64,0]
                    row['visible_blocks']['runs']=[[0,2,0,0,1]]+([[1,2,0,1,1]] if self.used else [])
                return row
        world=AutoWorld(True,True)
        player=Player(CallableBackend(lambda q:world.call(q['op'],**{k:v for k,v in q.items() if k!='op'})))
        def move(context,goal,**kwargs):
            self.assertTrue(kwargs['pose_handoff']);self.assertEqual(kwargs['expected_session'],world.session)
            self.assertEqual(goal.arrival_radius,.15)
            world.position=[goal.x,goal.y,goal.z];world.moved=True
            return SkillResult(status='succeeded',reason='arrived',text='Simulated pose only; placement still requires native-style observation.')
        with patch('blockwire.skills.walking.walk_to',side_effect=move) as moved:
            result=run_skill(default_registry(),player,'place_block',{'support':[2,64,0],'face':'south','auto_position':True},sleeper=lambda _:None)
        self.assertEqual(result.status,'succeeded',result);moved.assert_called_once();self.assertEqual(world.uses,1)
        self.assertEqual(result.details['position'],[2,64,1])

    def test_PH08_full_support_precision_observes_stance_before_the_first_direction(self):
        player=FlatPlayer();motor=FlatMotion();context=self.context(player)
        result=motor.pulse(context,player.navigation(),(1.5,64.,.5),'sneak',view=(-90.,0.),pose_handoff=True)
        self.assertIsNone(result);self.assertEqual(motor.mode,'pose_preparation')
        self.assertFalse(any(r[0]=='drive' and 'forward' in r[1] for r in player.calls))
        self.assertTrue(player.navigation()['sneaking'])
        result=motor.pulse(context,player.navigation(),(1.5,64.,.5),'sneak',view=(-90.,0.),pose_handoff=True)
        self.assertIsNone(result)
        directions=[r for r in player.calls if r[0]=='drive' and 'forward' in r[1]]
        self.assertEqual(len(directions),1);self.assertEqual(directions[0][2:],(8,{'forward':1,'sneak':8}))
        self.assertTrue(motor.sneak_stance)

    def test_PH09_unobserved_stance_is_bounded_and_never_authorizes_a_direction(self):
        player=FlatPlayer();motor=FlatMotion();context=self.context(player);result=None
        for _ in range(8):
            state={**player.navigation(),'sneaking':False,'eye_position':[player.position[0],65.62,player.position[2]]}
            result=motor.pulse(context,state,(1.5,64.,.5),'sneak',view=(-90.,0.),pose_handoff=True)
            if result is not None:break
        self.assertIsNotNone(result)
        self.assertEqual(result.reason,'pose_stance_not_observed')
        self.assertFalse(any(r[0]=='drive' and 'forward' in r[1] for r in player.calls))
        self.assertFalse(motor.sneak_stance);self.assertEqual(player.calls[-1],('stop',))

    def test_PH10_preparation_observation_preserves_actor_cancel_and_deadline_fences(self):
        for fault,status,reason in (('actor','blocked','actor_session_changed'),('cancel','cancelled','cancel_requested'),('deadline','timed_out','deadline_exceeded')):
            event=threading.Event()
            class Interrupted(FlatPlayer):
                def sleep(self,seconds):
                    super().sleep(seconds)
                    if self.sneaking:
                        if fault=='actor':self.session='replacement'
                        elif fault=='cancel':event.set()
                        else:self.now+=31.
            player=Interrupted()
            result=run_skill(default_registry(),player,'walk_to',{'x':1.5,'y':64.,'z':.5,'movement':'sneak','arrival_radius':.08},
                clock=player.clock,sleeper=player.sleep,cancel_event=event)
            self.assertEqual((result.status,result.reason),(status,reason))
            self.assertFalse(any(r[0]=='drive' and 'forward' in r[1] for r in player.calls))
            self.assertEqual(player.calls[-1],('stop',))

    def test_PH11_ordinary_coarse_edge_motion_keeps_independent_fall_protection(self):
        player=FlatPlayer();player.position=[.12,64.,.5];player.cells={(0,64,0)}
        result=walk_to(self.context(player),WalkTo(x=-.219,y=64.,z=.5,movement='sneak'))
        self.assertEqual(result.status,'succeeded',result)
        directions=[r for r in player.calls if r[0]=='drive' and 'forward' in r[1]]
        self.assertTrue(directions)
        for row in directions:self.assertEqual(row[2:],(8,{'forward':1,'sneak':8}))

    def test_PH12_ordinary_full_support_navigation_does_not_request_stance_preparation(self):
        player=FlatPlayer()
        result=walk_to(self.context(player),WalkTo(x=1.5,y=64.,z=.5,movement='sneak'))
        self.assertEqual(result.status,'succeeded',result)
        self.assertFalse(any(r[0]=='drive' and r[1]==['sneak'] for r in player.calls))


if __name__=='__main__':unittest.main()
