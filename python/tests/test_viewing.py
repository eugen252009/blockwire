import unittest
from blockwire.skills import default_registry,run_skill
from test_skills import FlatPlayer

class ViewPlayer(FlatPlayer):
    def observe(self):
        return {**super().observe(),'actor_session':self.session,'eye_position':[self.position[0],self.position[1]+1.62,self.position[2]]}

class ViewingContracts(unittest.TestCase):
    def test_VW01_observed_orientation_not_submission_and_no_movement(self):
        p=ViewPlayer();r=run_skill(default_registry(),p,'aim_at',{'x':3.5,'y':64.5,'z':.5},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.status,'succeeded');self.assertEqual(r.reason,'view_observed')
        self.assertFalse(any(row[0]=='drive' for row in p.calls));self.assertEqual(r.cleanup,'released')
    def test_VW02_replacement_during_turn_stops_before_new_actor_input(self):
        class Replaced(ViewPlayer):
            def look(self,*args,**kwargs):super().look(*args,**kwargs);self.session='new'
        p=Replaced();p.yaw=0.;r=run_skill(default_registry(),p,'aim_at',{'x':3.5,'y':64.5,'z':.5},clock=p.clock,sleeper=p.sleep)
        self.assertEqual(r.reason,'actor_session_changed');self.assertEqual(sum(row[0]=='look' for row in p.calls),1)
