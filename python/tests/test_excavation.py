"""Composition/uncertainty fixtures, not native excavation acceptance."""
import unittest
from unittest.mock import patch
from blockwire.skills import default_registry,run_skill,SkillResult


class ExcavationPlayer:
    def __init__(self):
        self.session='a';self.position=[.5,64.,.5];self.yaw=self.pitch=self.now=0.
        self.cleared=False;self.floor=True;self.block='minecraft:dirt';self.stops=0;self.looks=[]
    def navigation(self,*,terrain=False):
        assert terrain
        cells=[{'position':[0,64,0],'hazards':[]}]
        if self.cleared and self.floor:cells.append({'position':[0,63,-1],'hazards':[]})
        return {'profile':'stepped_full_blocks_v1','ready':True,'actor_session':self.session,'health':20.,
                'position':self.position[:],'current_cell':[0,63,-1] if self.position[1]==63 else [0,64,0],
                'current_center_access':True,'cells':cells,'edges':[[0,1]] if len(cells)>1 else []}
    def observe(self):
        hit=None if self.cleared else {'id':self.block,'position':[0,63,-1]}
        return {'alive':True,'actor_session':self.session,'visibility':{'profile':'sampled_surfaces_v1'},
                'position':self.position[:],'eye_position':[self.position[0],self.position[1]+1.62,self.position[2]],
                'yaw':self.yaw,'pitch':self.pitch,'sight_target':hit,'holding':{'empty':True}}
    def look(self,yaw,pitch,*,actor_session,**kwargs):assert actor_session==self.session;self.yaw,self.pitch=yaw,pitch;self.looks.append((yaw,pitch))
    def stop(self):self.stops+=1
    def clock(self):return self.now
    def sleep(self,n):self.now+=n


class ExcavationContracts(unittest.TestCase):
    def perform(self,p,change_actor=False):
        def mine(*args,**kwargs):p.cleared=True;p.session='b' if change_actor else 'a';return True
        def walk(ctx,goal,**kw):
            self.assertEqual(kw['expected_session'],'a')
            self.assertEqual((goal.x,goal.y,goal.z),(.5,63.,-.5))
            p.position=[.5,63.,-.5]
            return SkillResult(status='succeeded',reason='arrived',text='fixture')
        with patch('blockwire.skills.excavating.mine_observed_target',side_effect=mine) as mining,patch('blockwire.skills.excavating.walk_to',side_effect=walk) as walking:
            result=run_skill(default_registry(),p,'dig_step',{'direction':'north'},clock=p.clock,sleeper=p.sleep)
            return result,mining.call_count,walking.call_count
    def test_EX01_clearance_is_not_success_until_observed_supported_movement(self):
        for floor in (True,False):
            p=ExcavationPlayer();p.floor=floor;r,mines,walks=self.perform(p)
            self.assertEqual(mines,1)
            self.assertEqual(walks,1 if floor else 0)
            self.assertEqual(r.status,'succeeded' if floor else 'blocked',r)
            self.assertEqual(r.cleanup,'released')
            if floor:self.assertFalse(r.details['collection_claimed'])
            else:self.assertEqual(r.reason,'no_verified_step_destination')
    def test_EX02_unsupported_falling_block_or_missing_pick_never_mined(self):
        for block,reason in [('minecraft:gravel','unsupported_clearance_block'),('minecraft:stone','appropriate_equipped_tool_required')]:
            p=ExcavationPlayer();p.block=block;r,mines,walks=self.perform(p)
            self.assertEqual(r.reason,reason)
            self.assertEqual((mines,walks),(0,0))
    def test_EX04_reverse_jump_clearance_is_inspected_top_down(self):
        p=ExcavationPlayer();r,_,_=self.perform(p)
        self.assertEqual(r.status,'succeeded')
        self.assertLess(p.looks[0][1],0.,'Inspect upper clearance before removing adjacent floor')

    def test_EX03_replaced_actor_cannot_receive_descent(self):
        p=ExcavationPlayer();r,mines,walks=self.perform(p,True)
        self.assertEqual(r.reason,'actor_session_changed')
        self.assertEqual(walks,0)
        self.assertEqual(r.cleanup,'released')


if __name__=='__main__':unittest.main()
